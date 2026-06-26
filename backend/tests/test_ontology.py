"""Онтология услуг (Спринт-3): код/группа/ОСМС, наследование вариантами."""
from app.ingestion.ontology import groups, info


def test_info_base_services():
    oak = info("Общий анализ крови")
    assert oak["code"] == "LAB.HEM.CBC" and oak["group"] == "Гематология" and oak["osms"] is True
    mri = info("МРТ головного мозга")
    assert mri["group"] == "Лучевая диагностика" and mri["osms"] is False  # обычно по квоте


def test_variants_inherit_base_ontology():
    # «Глюкоза в моче» и «Повторный приём кардиолога» наследуют онтологию базы
    assert info("Глюкоза в моче")["code"] == info("Глюкоза (в крови)")["code"] == "LAB.BIO.GLU"
    assert info("Повторный приём кардиолога")["code"] == info("Приём кардиолога")["code"] == "CONS.CARD"
    assert info("Глюкозотолерантный тест")["code"] == "LAB.BIO.OGTT"


def test_echo_and_ecg_distinct():
    assert info("ЭхоКГ (эхокардиография)")["code"] == "FUNC.ECHO"
    assert info("ЭКГ")["code"] == "FUNC.ECG"


def test_osms_flags():
    assert info("Приём терапевта")["osms"] is True
    assert info("Витамин D")["osms"] is False
    assert info("Ферритин")["osms"] is False


def test_unknown_service_none():
    assert info("Криоконсервация эмбрионов") is None


def test_groups_listed():
    g = groups()
    assert "Биохимия" in g and "Консультации" in g and "Лучевая диагностика" in g
