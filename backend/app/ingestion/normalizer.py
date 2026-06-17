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

import json
import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

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


class Normalizer:
    def __init__(self, db: Session):
        self.db = db
        self.threshold = settings.match_confidence_threshold
        self._reload()
        self._llm = self._init_llm()

    def _reload(self):
        self.catalog: list[ServiceCatalog] = self.db.query(ServiceCatalog).all()
        # индекс: ключ для fuzzy -> service
        self.index: dict[str, ServiceCatalog] = {}
        for svc in self.catalog:
            self.index[_clean(svc.canonical_name)] = svc
            for syn in (svc.synonyms or []):
                self.index[_clean(str(syn))] = svc

    def _init_llm(self):
        if not settings.groq_api_key:
            return None
        try:
            from groq import Groq

            return Groq(api_key=settings.groq_api_key)
        except Exception:
            return None

    def _fuzzy(self, raw: str) -> tuple[ServiceCatalog | None, float]:
        if not self.index:
            return None, 0.0
        key = _clean(raw)
        match = process.extractOne(key, list(self.index.keys()), scorer=fuzz.token_set_ratio)
        if not match:
            return None, 0.0
        matched_key, score, _ = match
        return self.index[matched_key], score / 100.0

    def _llm_decide(self, raw: str, candidates: list[ServiceCatalog]) -> dict | None:
        if not self._llm:
            return None
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
        try:
            resp = self._llm.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception:
            return None

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

    def normalize(self, raw_name: str) -> MatchResult:
        svc, conf = self._fuzzy(raw_name)

        # 1. уверенный fuzzy — принимаем без LLM
        if svc and conf >= self.threshold:
            self._add_synonym(svc, raw_name)
            return MatchResult(svc, conf, False)

        # 2. зона неоднозначности — спрашиваем LLM (если доступен)
        top_candidates = self._top_candidates(raw_name, k=5)
        decision = self._llm_decide(raw_name, top_candidates)
        if decision:
            match_name = decision.get("match")
            llm_conf = float(decision.get("confidence") or 0.85)
            if match_name:
                target = self.index.get(_clean(match_name))
                if target:
                    self._add_synonym(target, raw_name)
                    return MatchResult(target, max(conf, llm_conf), False)
            canonical = (decision.get("canonical") or raw_name).strip()
            category = decision.get("category") or "Прочее"
            return self._find_or_create(canonical, category, raw_name, llm_conf, is_new=True)

        # 3. без LLM: слабый fuzzy всё равно лучше, чем дубль-справочник
        if svc and conf >= 0.6:
            self._add_synonym(svc, raw_name)
            return MatchResult(svc, conf, False)

        # 4. новая услуга
        return self._find_or_create(raw_name.strip(), "Прочее", raw_name, conf, is_new=True)

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
