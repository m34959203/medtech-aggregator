"""Нормализация услуг к единому справочнику (★ общая воронка обоих каналов).

Сводит разнобой названий ("ОАК", "Общий анализ крови (5 параметров)",
"Анализ крови общий") к одной эталонной записи service_catalog.

Стратегия (от дешёвого к умному):
1. fuzzy-match (rapidfuzz) против canonical_name и всех синонимов;
2. при высокой уверенности — принимаем сразу, без сети;
3. при неоднозначности и наличии GROQ_API_KEY — LLM выбирает из top-k
   кандидатов либо предлагает чистое эталонное имя + категорию;
4. иначе создаём новую запись справочника (catalog растёт сам).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from .. import llm
from ..config import settings
from ..models import ServiceCatalog


@dataclass
class MatchResult:
    service: ServiceCatalog
    confidence: float
    is_new: bool


def _clean(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\([^)]*\)", " ", s)  # убрать скобочные уточнения
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Модификаторы приёма врача, меняющие сам продукт: повторный / онлайн / детский
# приём — это НЕ первичный приём, и сравнивать их под одной услугой нельзя (иначе
# «🏆 Лучшая цена» врёт). token_set_ratio даёт 100%, т.к. «приём гинеколога» —
# подмножество «вторичный приём гинеколога», поэтому фильтруем явно по словам.
_APPT_MODIFIERS = (
    (re.compile(r"повторн|вторичн|контрольн|динамическ", re.I), "repeat"),
    (re.compile(r"онлайн|дистанцион|телемед|\bonline\b", re.I), "online"),
    (re.compile(r"детск|ребёнк|ребенк|\bдетей\b|педиатр", re.I), "pediatric"),
)


def _appt_modifier(text: str) -> str | None:
    """Возвращает тип не-первичного приёма (repeat/online/pediatric) или None."""
    for rx, label in _APPT_MODIFIERS:
        if rx.search(text or ""):
            return label
    return None


def _derive_appt_name(primary_canonical: str, modifier: str) -> str:
    """«Приём гинеколога» + repeat → «Повторный приём гинеколога» и т.п."""
    spec = re.sub(r"^при[её]м\s+", "", primary_canonical.strip(), flags=re.I)
    spec = re.sub(r"^консультация\s+", "", spec, flags=re.I).strip()
    if modifier == "repeat":
        return f"Повторный приём {spec}"
    if modifier == "online":
        return f"Онлайн-консультация {spec}"
    if modifier == "pediatric":
        return f"Приём детского {spec}"
    return primary_canonical


def _analyte_variant(raw: str, canonical: str) -> str | None:
    """Биоматериал/вид анализа меняет сам аналит: «Глюкоза в моче» ≠ «Глюкоза (в крови)»,
    «глюкозотолерантный тест» ≠ обычная глюкоза. Иначе сравнение цен мешает разные тесты.
    """
    low = raw.lower()
    cl = canonical.lower()
    # Глюкозотолерантный тест — отдельный продукт (нагрузочная проба, не разовый сахар).
    if "глюкоз" in cl and re.search(r"толерант|глюкозотолер|нагрузочн|с нагрузкой", low):
        return "Глюкозотолерантный тест"
    # Моча vs кровь: сырое имя про мочу, а эталон — не мочевой аналит.
    # Имя БЕЗ скобок («Глюкоза в моче»), иначе _clean срежет «(в моче)»/«(в крови)»
    # к одному ключу «глюкоза» → коллизия в индексе нормализатора.
    if "моч" in low and "моч" not in cl:
        base = re.sub(r"\s*\([^)]*\)\s*$", "", canonical).strip()  # убрать хвост «(в крови)»
        base = re.sub(r"\s+в\s+крови$", "", base, flags=re.I).strip()
        return f"{base} в моче"
    return None


# Биоматериал по умолчанию — КРОВЬ/сыворотка (TASK 3). Если сырое имя про обычный
# аналит (без «моча/urine»), а лучший матч оказался мочевым вариантом — это ошибка
# (token_set уравнивает «Ферритин» и «Ферритин в моче»). Возвращаем имя кровяного
# варианта, чтобы перематчиться на него.
def _prefer_blood(raw: str, canonical: str) -> str | None:
    low = (raw or "").lower()
    cl = (canonical or "").lower()
    if re.search(r"моч|urine", low):
        return None  # сырое имя само про мочу — мочевой вариант верен
    if "моч" not in cl:
        return None  # матч и так не мочевой
    base = re.sub(r"\s*в\s*моче\b", "", canonical, flags=re.I)
    base = re.sub(r"\s{2,}", " ", base).strip(" ,;")
    return base or None


# Биоматериал-гард: стул (кал)/мокрота — сильный сигнал, что услуга НЕ кровяная.
# Без гарда загрязнённый синоним («Кал на скрытую кровь» как синоним ОАК) даёт
# exact-матч conf=1.0 и пачкает и привязку цен, и поиск. Слово «кровь» внутри
# «кал на скрытую кровь» — про метод, биоматериал = стул. \b чтобы не задеть
# «калий»/«кальций»/«шкала». Мочу НЕ трогаем — её ведёт _reroute_analyte/_prefer_blood.
_STOOL_RE = re.compile(
    r"\b(кал|кала|кале|калу|копрограмм\w*|копролог\w*|копроцит\w*|фекал\w*|стул)\b",
    re.I)
_SPUTUM_RE = re.compile(r"\bмокрот\w*", re.I)
_URINE_RE = re.compile(r"\bмоч[аеиоуы]\w*|\bв\s+моче\b|urin|\bуриа|\bурин", re.I)


def _biomat_class(s: str) -> str | None:
    """Грубый биоматериал строки: 'stool' / 'sputum' / 'urine' / None (кровь/прочее)."""
    low = (s or "").lower()
    if _STOOL_RE.search(low):
        return "stool"
    if _SPUTUM_RE.search(low):
        return "sputum"
    if _URINE_RE.search(low):
        return "urine"
    return None


def _biomat_conflict(raw: str, canonical: str) -> bool:
    """True при грубом конфликте биоматериала сырого имени и услуги-кандидата:
      • сырьё про стул/мокроту, а услуга — нет;
      • ОБЫЧНЫЙ (не-мочевой) аналит, а услуга — мочевой вариант («Глюкоза» → «Глюкоза
        в моче»). Обратное (мочевое сырьё → кровяная услуга) НЕ конфликт — его ведёт
        _reroute_analyte/_analyte_variant (создаёт мочевой вариант)."""
    rb, cb = _biomat_class(raw), _biomat_class(canonical)
    if rb in ("stool", "sputum") and rb != cb:
        return True
    if cb == "urine" and rb != "urine":
        # Конфликт лишь когда raw — ТОТ ЖЕ аналит, что мочевой каноним, т.е. канон =
        # «<база> в моче», а raw ≈ <база> («Глюкоза» → «Глюкоза в моче» → дефолт-кровь).
        # Аббревиатуры с собственным мочевым смыслом («ОАМ» → «Общий анализ мочи»)
        # базой не совпадают — это НЕ конфликт, услуга верна.
        base = re.sub(r"\s+", " ", _URINE_RE.sub(" ", canonical.lower())).strip()
        return bool(base) and fuzz.token_set_ratio(_clean(raw), _clean(base)) >= 75
    return False


class Normalizer:
    def __init__(self, db: Session):
        self.db = db
        self.threshold = settings.match_confidence_threshold
        self._reload()

    def _reload(self):
        self.catalog: list[ServiceCatalog] = self.db.query(ServiceCatalog).all()
        # индекс: ключ для fuzzy -> service
        self.index: dict[str, ServiceCatalog] = {}
        # индекс по коду тарификатора (MedArchive): код -> [услуги] (код не уникален)
        self.code_index: dict[str, list[ServiceCatalog]] = {}
        for svc in self.catalog:
            self.index[_clean(svc.canonical_name)] = svc
            for syn in (svc.synonyms or []):
                self.index[_clean(str(syn))] = svc
            code = getattr(svc, "tarificator_code", None)
            if code:
                self.code_index.setdefault(code, []).append(svc)

    def match_archive(self, raw_name: str, code: str | None = None) -> tuple[ServiceCatalog | None, float]:
        """READ-ONLY сопоставление позиции архива с ЦЕЛЕВЫМ справочником (он фиксирован).

        СНАЧАЛА по коду тарификатора (точно, conf=1.0), иначе fuzzy. Ниже порога →
        (None, conf): позиция уходит в очередь unmatched, БЕЗ создания новых услуг и
        синонимов — официальный справочник 1286 услуг не загрязняется и приём быстр.
        """
        if code:
            cands = self.code_index.get(code)
            if cands:
                if len(cands) == 1:
                    return cands[0], 1.0
                key = _clean(raw_name)  # один код у нескольких услуг — доуточняем по имени
                return max(cands, key=lambda s: fuzz.token_set_ratio(key, _clean(s.canonical_name))), 1.0
        svc, conf = self._fuzzy(raw_name)
        if svc and conf >= self.threshold:
            return svc, conf
        return None, conf

    def _fuzzy(self, raw: str) -> tuple[ServiceCatalog | None, float]:
        if not self.index:
            return None, 0.0
        key = _clean(raw)
        match = process.extractOne(key, list(self.index.keys()), scorer=fuzz.token_set_ratio)
        if not match:
            return None, 0.0
        matched_key, score, _ = match
        return self.index[matched_key], score / 100.0

    def _fuzzy_guarded(self, raw: str) -> tuple[ServiceCatalog | None, float]:
        """Лучший fuzzy-кандидат БЕЗ конфликта биоматериала (стул/мокрота/мочевой
        вариант для обычного аналита). Перешагивает загрязнённый топ-хит и берёт
        корректный ниже (напр. «Глюкоза» → «Глюкоза (в крови)», не «...в моче»)."""
        if not self.index:
            return None, 0.0
        key = _clean(raw)
        ranked = process.extract(key, list(self.index.keys()),
                                 scorer=fuzz.token_set_ratio, limit=12)
        good = [(mk, self.index[mk], sc) for mk, sc, _ in ranked
                if not _biomat_conflict(raw, self.index[mk].canonical_name)]
        if not good:
            return None, 0.0  # все топ-кандидаты конфликтуют → в очередь, не ложно
        # token_set_ratio уравнивает короткое сырьё со всеми услугами-надмножествами
        # («ТТГ» = 100% и «ТТГ (тиреотропный гормон)», и «Антитела к рецепторам ТТГ»).
        # Среди почти равных по token_set выбираем по двум сигналам:
        #   1) совпадение биоматериала (кровь/моча — иначе «Глюкоза»→«…в моче»);
        #   2) длино-чувствительный ratio (короткий ключ ближе к атомарной услуге,
        #      «ттг»↔«ттг тиреотропный гормон», чем к длинному «антитела…ттг»).
        rb = _biomat_class(raw)
        top = good[0][2]
        near = [g for g in good if g[2] >= top - 2]
        best = max(near, key=lambda g: (_biomat_class(g[1].canonical_name) == rb,
                                        fuzz.ratio(key, g[0])))
        return best[1], best[2] / 100.0

    def match(self, raw: str) -> tuple[ServiceCatalog | None, float]:
        """Read-only подбор услуги под сырое имя (fuzzy → семантика) — для корзины-рецепта."""
        # биоматериал-гард встроен: стул/мокрота/мочевой вариант для обычного
        # аналита не матчатся, берётся корректный кандидат ниже по рангу.
        svc, conf = self._fuzzy_guarded(raw)
        if svc is not None and conf >= self.threshold:
            return svc, conf
        from . import semantic
        if semantic.available():
            sid, score = semantic.match(self.db, raw)
            if sid and score >= settings.semantic_threshold and score > conf:
                cand = self.db.get(ServiceCatalog, sid)
                if cand and not _biomat_conflict(raw, cand.canonical_name):
                    return cand, score
        return svc, conf

    def _semantic_match(self, raw_name: str) -> "MatchResult | None":
        """Тир семантики: ближайшая по смыслу услуга, с теми же гардами вариантов."""
        from . import semantic
        if not semantic.available():
            return None
        sid, score = semantic.match(self.db, raw_name)
        if not sid or score < settings.semantic_threshold:
            return None
        svc = self.db.get(ServiceCatalog, sid)
        if not svc:
            return None
        if _biomat_conflict(raw_name, svc.canonical_name):
            return None  # стул/мокрота ≠ кровяная услуга — не привязываем
        rerouted = self._reroute_appointment(raw_name, svc, score) or self._reroute_analyte(raw_name, svc, score)
        if rerouted:
            return rerouted
        self._add_synonym(svc, raw_name)
        return MatchResult(svc, score, False)

    def _llm_decide(self, raw: str, candidates: list[ServiceCatalog]) -> dict | None:
        """Дизамбигуация через LLM (AlemLLM/Groq). None, если ключа нет/ошибка."""
        cand_text = "\n".join(f"- {c.canonical_name} (категория: {c.category})" for c in candidates)
        prompt = (
            "Ты нормализуешь названия медицинских услуг к единому справочнику.\n"
            f'Сырое название из прайса клиники: "{raw}"\n\n'
            f"Кандидаты из справочника:\n{cand_text or '(пусто)'}\n\n"
            "Если сырое название означает ту же услугу, что один из кандидатов — верни его.\n"
            "Если это новая услуга — предложи короткое эталонное название и категорию.\n"
            "Категории: Анализы, Приём врача, УЗИ, МРТ/КТ, Рентген, Процедуры, Стоматология, Прочее.\n"
            'Ответь строго JSON: {"match": "<точное имя кандидата или null>", '
            '"canonical": "<эталонное имя>", "category": "<категория>", "confidence": <0..1>}'
        )
        return llm.json_completion(prompt)

    def _find_or_create(self, canonical: str, category: str, synonym: str, conf: float, is_new: bool) -> MatchResult:
        ckey = _clean(canonical)
        existing = self.index.get(ckey)
        if existing:
            self._add_synonym(existing, synonym)
            return MatchResult(existing, conf, False)
        svc = ServiceCatalog(canonical_name=canonical, category=category or "Прочее", synonyms=[synonym])
        self.db.add(svc)
        self.db.flush()
        self.index[ckey] = svc
        self.index[_clean(synonym)] = svc
        self.catalog.append(svc)
        return MatchResult(svc, conf, True)

    def _add_synonym(self, svc: ServiceCatalog, raw: str):
        key = _clean(raw)
        syns = list(svc.synonyms or [])
        if raw not in syns and key != _clean(svc.canonical_name):
            syns.append(raw)
            svc.synonyms = syns
            self.index[key] = svc

    def _reroute_appointment(self, raw_name: str, svc: ServiceCatalog, conf: float) -> MatchResult | None:
        """Не сливать повторный/онлайн/детский приём с первичным — отдельная услуга."""
        if not svc or svc.category != "Приём врача":
            return None
        mod = _appt_modifier(raw_name)
        if not mod or _appt_modifier(svc.canonical_name):
            return None  # модификатора нет, либо целевая услуга сама не-первичная
        derived = _derive_appt_name(svc.canonical_name, mod)
        return self._find_or_create(derived, svc.category, raw_name, conf, is_new=False)

    def _reroute_analyte(self, raw_name: str, svc: ServiceCatalog, conf: float) -> MatchResult | None:
        """Не сливать мочу с кровью и глюкозотолерантный тест с обычной глюкозой."""
        if not svc or svc.category != "Анализы":
            return None
        derived = _analyte_variant(raw_name, svc.canonical_name)
        # сравнение буквальное: _clean срезает скобки и «(в моче)» совпало бы с эталоном
        if not derived or derived.strip().lower() == svc.canonical_name.strip().lower():
            return None
        return self._find_or_create(derived, "Анализы", raw_name, conf, is_new=False)

    def normalize(self, raw_name: str) -> MatchResult:
        # биоматериал-гард встроен в _fuzzy_guarded (стул/мокрота/мочевой вариант
        # для обычного аналита перешагиваются, берётся корректный кандидат).
        svc, conf = self._fuzzy_guarded(raw_name)

        # 0. гард: повторный приём ≠ первичный, моча ≠ кровь — отводим в свою услугу
        if svc and conf >= self.threshold:
            rerouted = self._reroute_appointment(raw_name, svc, conf) or self._reroute_analyte(raw_name, svc, conf)
            if rerouted:
                return rerouted

        # 1. уверенный fuzzy — принимаем без LLM
        if svc and conf >= self.threshold:
            self._add_synonym(svc, raw_name)
            return MatchResult(svc, conf, False)

        # 1.5 семантика (смысл, offline) — до LLM: ловит «кровь на сахар»→«Глюкоза»
        sem = self._semantic_match(raw_name)
        if sem:
            return sem

        # 2. зона неоднозначности — спрашиваем LLM (если доступен)
        top_candidates = self._top_candidates(raw_name, k=5)
        decision = self._llm_decide(raw_name, top_candidates)
        if decision:
            match_name = decision.get("match")
            llm_conf = float(decision.get("confidence") or 0.85)
            if match_name:
                target = self.index.get(_clean(match_name))
                # биоматериал-гард и на LLM-таргет: индекс может быть загрязнён
                # (синоним «Копрограмма»→ЭКГ), тогда даже верный вердикт LLM
                # резолвится в чужую услугу. Конфликт → создаём новую, не привязываем.
                if target and not _biomat_conflict(raw_name, target.canonical_name):
                    self._add_synonym(target, raw_name)
                    return MatchResult(target, max(conf, llm_conf), False)
            canonical = (decision.get("canonical") or raw_name).strip()
            category = decision.get("category") or "Прочее"
            return self._find_or_create(canonical, category, raw_name, llm_conf, is_new=True)

        # 3. без LLM: слабый fuzzy (0.6..порог) принимаем как привязку, но НЕ
        # добавляем синонимом — иначе слабый/ошибочный матч становится вечным
        # exact-хитом 1.0 и растит услуги-магниты (корень хвоста загрязнения).
        if svc and conf >= 0.6:
            return MatchResult(svc, conf, False)

        # 4. новая услуга
        return self._find_or_create(raw_name.strip(), "Прочее", raw_name, conf, is_new=True)

    def preview(self, raw_name: str) -> dict:
        """Сухой прогон нормализации БЕЗ записи в БД — для live-демо движка.

        Возвращает решение и КАК оно принято (fuzzy / LLM / новая услуга),
        с уверенностью и top-кандидатами. Ничего не мутирует.
        """
        svc, conf = self._fuzzy(raw_name)
        candidates = [c.canonical_name for c in self._top_candidates(raw_name, k=5)]

        # 0. гард: повторный приём / моча отводятся в отдельную услугу
        if svc and conf >= self.threshold:
            derived = None
            if svc.category == "Приём врача":
                mod = _appt_modifier(raw_name)
                if mod and not _appt_modifier(svc.canonical_name):
                    derived = _derive_appt_name(svc.canonical_name, mod)
            elif svc.category == "Анализы":
                cand = _analyte_variant(raw_name, svc.canonical_name)
                if cand and cand.strip().lower() != svc.canonical_name.strip().lower():
                    derived = cand
            if derived:
                return {
                    "raw": raw_name, "canonical": derived, "category": svc.category,
                    "confidence": round(conf, 3), "method": "fuzzy", "is_new": _clean(derived) not in self.index,
                    "candidates": candidates,
                }

        # 1. уверенный fuzzy — без сети
        if svc and conf >= self.threshold:
            return {
                "raw": raw_name, "canonical": svc.canonical_name, "category": svc.category,
                "confidence": round(conf, 3), "method": "fuzzy", "is_new": False,
                "candidates": candidates,
            }

        # 1.5 семантика (смысл, offline) — до LLM
        from . import semantic
        if semantic.available():
            sid, score = semantic.match(self.db, raw_name)
            if sid and score >= settings.semantic_threshold:
                tgt = self.db.get(ServiceCatalog, sid)
                if tgt:
                    return {
                        "raw": raw_name, "canonical": tgt.canonical_name, "category": tgt.category,
                        "confidence": round(score, 3), "method": "semantic", "is_new": False,
                        "candidates": candidates,
                    }

        # 2. зона неоднозначности — LLM
        decision = self._llm_decide(raw_name, self._top_candidates(raw_name, k=5))
        if decision:
            llm_conf = float(decision.get("confidence") or 0.85)
            match_name = decision.get("match")
            target = self.index.get(_clean(match_name)) if match_name else None
            if target:
                return {
                    "raw": raw_name, "canonical": target.canonical_name, "category": target.category,
                    "confidence": round(max(conf, llm_conf), 3), "method": "llm", "is_new": False,
                    "candidates": candidates,
                }
            return {
                "raw": raw_name,
                "canonical": (decision.get("canonical") or raw_name).strip(),
                "category": decision.get("category") or "Прочее",
                "confidence": round(llm_conf, 3), "method": "llm", "is_new": True,
                "candidates": candidates,
            }

        # 3. слабый fuzzy без LLM
        if svc and conf >= 0.6:
            return {
                "raw": raw_name, "canonical": svc.canonical_name, "category": svc.category,
                "confidence": round(conf, 3), "method": "fuzzy-weak", "is_new": False,
                "candidates": candidates,
            }

        # 4. новая услуга
        return {
            "raw": raw_name, "canonical": raw_name.strip(), "category": "Прочее",
            "confidence": round(conf, 3), "method": "new", "is_new": True,
            "candidates": candidates,
        }

    def _top_candidates(self, raw: str, k: int) -> list[ServiceCatalog]:
        if not self.index:
            return []
        key = _clean(raw)
        ranked = process.extract(key, list(self.index.keys()), scorer=fuzz.token_set_ratio, limit=k)
        seen, out = set(), []
        for matched_key, _score, _ in ranked:
            svc = self.index[matched_key]
            if svc.id not in seen:
                seen.add(svc.id)
                out.append(svc)
        return out

    # ---- Строгий разбор строки (gate + декомпозиция + порог отказа) — TASK 1-4 ----
    def match_one(self, raw: str, floor: float | None = None,
                  sem_floor: float | None = None) -> dict:
        """READ-ONLY строгий матч ОДНОЙ атомарной строки. Ниже reject_floor —
        status=unmatched (не тянем мусорный «лучший» с фиктивными 100%, TASK 2).
        Гарды: моча/кровь по умолчанию кровь, повторный/онлайн приём отдельно.

        floor/sem_floor — пороги отказа для fuzzy и семантики (по умолчанию из
        settings). Пользовательский путь «по рецепту» передаёт более строгие
        значения: ложное «узнавание» мусора («HemoglobinX», «Test 123») вводит
        пациента в заблуждение сильнее, чем честное «не распознано»."""
        floor = settings.reject_floor if floor is None else floor
        sem_floor = settings.semantic_threshold if sem_floor is None else sem_floor
        # Биоматериал-гард: тот же отбор кандидатов, что и в match()/normalize().
        # _fuzzy брал топ token_set-хит вслепую («Глюкоза»→«Глюкоза в моче», т.к.
        # «глюкоза» — подстрока обоих), а _prefer_blood лишь резал «в моче» в
        # несуществующую строку «Глюкоза». _fuzzy_guarded сразу даёт реальную
        # кровяную услугу «Глюкоза (в крови)» и держит дефолт-кровь.
        svc, conf = self._fuzzy_guarded(raw)
        if svc and conf >= floor:
            canonical, category = svc.canonical_name, svc.category
            service_id = svc.id  # точная привязка: потребитель не переразрешает по
            # имени (`_clean` схлопывает «Глюкоза (в крови)» и «Глюкоза в моче» в один
            # ключ «глюкоза» → коллизия индекса возвращала мочевой вариант).
            # guard: мочевой/толерантный/приёмный вариант
            if svc.category == "Анализы":
                av = _analyte_variant(raw, svc.canonical_name)
                if av and av.strip().lower() != svc.canonical_name.strip().lower():
                    canonical, service_id = av, None  # дериватив-вариант ищется по имени
            elif svc.category == "Приём врача":
                mod = _appt_modifier(raw)
                if mod and not _appt_modifier(svc.canonical_name):
                    canonical, service_id = _derive_appt_name(svc.canonical_name, mod), None
            return {"canonical": canonical, "category": category, "service_id": service_id,
                    "confidence": round(conf, 3), "method": "fuzzy", "status": "matched"}
        # семантика (смысл) — тоже под порогом отказа
        from . import semantic
        if semantic.available():
            sid, score = semantic.match(self.db, raw)
            if sid and score >= max(sem_floor, floor):
                tgt = self.db.get(ServiceCatalog, sid)
                if tgt:
                    return {"canonical": tgt.canonical_name, "category": tgt.category,
                            "service_id": tgt.id, "confidence": round(score, 3),
                            "method": "semantic", "status": "matched"}
        # ниже порога — честный отказ, НЕ принудительная привязка
        return {"canonical": "—", "category": None, "service_id": None,
                "confidence": round(conf, 3), "method": "none", "status": "unmatched"}

    def analyze(self, raw: str, floor: float | None = None,
                sem_floor: float | None = None) -> dict:
        """Полный разбор строки направления/прайса: gate (шум) → декомпозиция панелей
        → строгий матч каждой части. Возвращает {raw, kind, reason, items[]}.
        floor/sem_floor пробрасываются в match_one (рецепт — строже, см. там)."""
        from . import line_gate, panels
        kind, reason = line_gate.classify_line(raw)
        if kind == "noise":
            return {"raw": raw, "kind": "noise", "reason": reason, "items": []}
        parts = panels.decompose(raw)
        if parts:
            # панель/составное — источник истины разбиения; части как услуги
            items = [{"canonical": p, "category": "Анализы", "confidence": 1.0,
                      "method": "panel", "status": "matched"} for p in parts]
            return {"raw": raw, "kind": "service", "reason": "", "items": items}
        listed = self._split_list(raw, floor, sem_floor)
        if listed is not None:
            return {"raw": raw, "kind": "service", "reason": "", "items": listed}
        return {"raw": raw, "kind": "service", "reason": "",
                "items": [self.match_one(raw, floor=floor, sem_floor=sem_floor)]}

    def _split_list(self, raw: str, floor: float | None,
                    sem_floor: float | None) -> list[dict] | None:
        """Список услуг через запятую («ОАК, ОАМ по м/ж» → ОАК + ОАМ).

        panels.decompose дробит только явные «Панель: a, b, c», а голый список —
        нет (generic split «+»/«,» опасен: «ОАК + лейкоформула» — ОДНА услуга).
        Поэтому дробим по запятой и принимаем разбиение ТОЛЬКО если ≥2 сегмента
        дали РАЗНЫЕ распознанные услуги — иначе «ОАК, 5 diff» / «ОАК, парацетамол»
        остаются цельной строкой. «/» НЕ режем (ломает «м/ж», «Na/K/Cl»)."""
        if "," not in raw:
            return None
        segs = [s.strip(" .;:–—") for s in raw.split(",")]
        segs = [s for s in segs if len(s) >= 2 and re.search(r"[A-Za-zА-Яа-яЁё]{2,}", s)]
        if len(segs) < 2:
            return None
        items: list[dict] = []
        distinct: set = set()
        for s in segs:
            for it in self.analyze(s, floor=floor, sem_floor=sem_floor)["items"]:
                items.append(it)
                if it.get("status") == "matched":
                    distinct.add(it.get("service_id") or _clean(it.get("canonical") or ""))
        return items if len(distinct) >= 2 else None


def sanitize_synonyms(db: Session) -> int:
    """Чистка загрязнённых синонимов (последствие прошлых слабых матчей: у «Са+»
    синоним «АЛТ», у «Витамин D» — «Ферритин» и т.п.). Удаляем синоним S из услуги X, если:
      • S дублирует canonical X; ИЛИ
      • S совпадает с canonical ДРУГОЙ услуги (кросс-привязка); ИЛИ
      • S — короткая аббревиатура, НЕ являющаяся инициалами X и не похожая на X.
    Возвращает число удалённых синонимов."""
    # ТОЧЕЧНОЕ правило (высокая точность): удаляем синоним, только если он дублирует
    # собственное имя ИЛИ ТОЧНО совпадает с именем ДРУГОЙ услуги (однозначный мис-файл,
    # напр. «Ферритин» в синонимах «Витамин D»). Эвристику «короткая аббревиатура» НЕ
    # применяем — на боевом наборе она снесла сотни легитимных синонимов-сырых-имён.
    cats = db.query(ServiceCatalog).all()
    by_canon: dict[str, ServiceCatalog] = {_clean(c.canonical_name): c for c in cats}
    removed = 0
    for x in cats:
        kept, changed = [], False
        xck = _clean(x.canonical_name)
        for syn in (x.synonyms or []):
            s = str(syn)
            cs = _clean(s)
            if not cs or cs == xck:
                removed += 1; changed = True; continue
            other = by_canon.get(cs)
            if other is not None and other.id != x.id:
                removed += 1; changed = True; continue  # синоним = имя другой услуги
            kept.append(s)
        if changed:
            x.synonyms = kept
    if removed:
        db.commit()
    return removed
