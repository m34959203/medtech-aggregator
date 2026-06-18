"""Онтология услуг (Спринт-3): стандартный код + группа + покрытие ОСМС.

Превращает справочник из «списка строк» в структурированный актив: каждая услуга
привязана к коду и клинической группе, помечено покрытие обязательной страховки
(ОСМС). Это и фундамент для семантического слоя (pgvector — отдельный инфра-шаг),
и дифференциатор для РК («входит ли в страховку» рядом с ценой).

Источник истины — курируемая карта по базовому ключу услуги (варианты «в моче» /
«повторный приём» наследуют онтологию базовой услуги). Считается на чтении, схему
БД не трогаем.

ВНИМАНИЕ: флаг ОСМС — справочный ориентир, не юридическое заключение; реальное
покрытие зависит от показаний и направления.
"""
from __future__ import annotations

import re

# Клинические группы
_HEM, _BIO, _HORM, _IMM, _CLIN = "Гематология", "Биохимия", "Гормоны", "Иммунология", "Общеклинические"
_CONS, _UZI, _FUNC, _RAD = "Консультации", "УЗИ", "Функциональная диагностика", "Лучевая диагностика"

# базовый ключ услуги → (code, group, osms)
ONTOLOGY: dict[str, tuple[str, str, bool]] = {
    "общий анализ крови": ("LAB.HEM.CBC", _HEM, True),
    "общий анализ мочи": ("LAB.CLIN.UA", _CLIN, True),
    "глюкоза": ("LAB.BIO.GLU", _BIO, True),
    "глюкозотолерантный тест": ("LAB.BIO.OGTT", _BIO, True),
    "гликированный гемоглобин": ("LAB.BIO.HBA1C", _BIO, False),
    "креатинин": ("LAB.BIO.CREA", _BIO, True),
    "билирубин общий": ("LAB.BIO.TBIL", _BIO, True),
    "холестерин общий": ("LAB.BIO.CHOL", _BIO, True),
    "биохимический анализ крови": ("LAB.BIO.PANEL", _BIO, True),
    "с-реактивный белок": ("LAB.IMM.CRP", _IMM, False),
    "ферритин": ("LAB.IMM.FERR", _IMM, False),
    "витамин d": ("LAB.IMM.VITD", _IMM, False),
    "ттг": ("LAB.HORM.TSH", _HORM, False),
    "приём терапевта": ("CONS.GP", _CONS, True),
    "приём кардиолога": ("CONS.CARD", _CONS, True),
    "приём невролога": ("CONS.NEUR", _CONS, True),
    "приём гинеколога": ("CONS.GYN", _CONS, True),
    "приём уролога": ("CONS.URO", _CONS, True),
    "приём эндокринолога": ("CONS.ENDO", _CONS, True),
    "приём офтальмолога": ("CONS.OPHT", _CONS, True),
    "приём дерматолога": ("CONS.DERM", _CONS, True),
    "приём лор-врача": ("CONS.ENT", _CONS, True),
    "узи брюшной полости": ("IMG.US.ABD", _UZI, True),
    "узи почек": ("IMG.US.KID", _UZI, True),
    "узи щитовидной железы": ("IMG.US.THY", _UZI, True),
    "узи органов малого таза": ("IMG.US.PEL", _UZI, True),
    "узи молочных желёз": ("IMG.US.BRE", _UZI, True),
    "экг": ("FUNC.ECG", _FUNC, True),
    "эхокг": ("FUNC.ECHO", _FUNC, True),
    "мрт головного мозга": ("IMG.MRI.BRAIN", _RAD, False),
    "кт головного мозга": ("IMG.CT.BRAIN", _RAD, False),
}


def _okey(canonical: str) -> str:
    """Базовый ключ услуги: варианты сводятся к базовой записи онтологии."""
    k = (canonical or "").lower().strip()
    k = re.sub(r"^повторный при[её]м\s+", "приём ", k)
    k = re.sub(r"^онлайн-консультация\s+", "приём ", k)
    k = re.sub(r"^при[её]м детского\s+", "приём ", k)
    k = re.sub(r"\s+в моче$", "", k)
    k = re.sub(r"глюкозотолерантный тест", "глюкозотолерантный тест", k)  # сохраняем как есть
    if "глюкозотолерантный" not in k:
        k = re.sub(r"\s*\([^)]*\)", "", k)  # убрать скобочные уточнения, кроме ГТТ
    k = re.sub(r"\s+", " ", k).strip()
    if k.startswith("эхокардиограф") or k == "эхокардиография":
        k = "эхокг"
    return k


def info(canonical: str) -> dict | None:
    """Онтология услуги: {code, group, osms} или None, если не размечена."""
    hit = ONTOLOGY.get(_okey(canonical))
    if not hit:
        return None
    code, group, osms = hit
    return {"code": code, "group": group, "osms": osms}


def groups() -> list[str]:
    """Уникальные клинические группы (для навигации по онтологии)."""
    seen = []
    for _, group, _osms in ONTOLOGY.values():
        if group not in seen:
            seen.append(group)
    return sorted(seen)
