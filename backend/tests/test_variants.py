"""Модель «база + атрибуты варианта»: группировка и теги сопоставимости."""
from app.ingestion.variants import attributes, base_key, variant_label


def test_base_key_groups_glucose_variants():
    bk = base_key("Глюкоза (в крови)")
    assert base_key("Глюкоза в моче") == bk
    assert base_key("Глюкозотолерантный тест") == bk
    assert bk == "глюкоза"


def test_base_key_groups_appointment_variants():
    bk = base_key("Приём гинеколога")
    assert base_key("Повторный приём гинеколога") == bk
    assert base_key("Онлайн-консультация гинеколога") == bk
    assert base_key("Приём детского гинеколога") == bk


def test_attributes_biomaterial():
    assert attributes("Глюкоза в моче")["biomaterial"] == "urine"
    assert "моча" in attributes("Глюкоза в моче")["tags"]
    assert attributes("Глюкоза (в крови)")["biomaterial"] == "blood"


def test_attributes_visit_type():
    assert attributes("Повторный приём кардиолога")["visit"] == "repeat"
    assert attributes("Приём кардиолога")["visit"] == "primary"
    assert "первичный" in attributes("Приём кардиолога")["tags"]


def test_attributes_tolerance_variant():
    a = attributes("Глюкозотолерантный тест")
    assert a["variant"] == "tolerance"
    assert "нагрузочный тест" in a["tags"]


def test_variant_label_human_readable():
    assert variant_label("Глюкоза в моче")  # не пусто
    assert "моча" in variant_label("Глюкоза в моче")
