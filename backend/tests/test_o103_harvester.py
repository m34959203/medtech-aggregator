"""Харвестер 103.kz — офлайн (без сети/браузера).

Проверяем три кирпича, на которых стоит harvest():
  • _extract_slugs   — выделение slug'ов клиник из листинга/sitemap + отсев инфры;
  • _localbusiness_meta — имя/город/телефон из JSON-LD LocalBusiness страницы /pricing/;
  • web_scraper._103kz — разбор реальных карточек прайса (интеграция, что и тянет harvest).
"""
from app.ingestion import o103_harvester as h
from app.ingestion import web_scraper as ws

# Фрагмент карточек прайса 103.kz (реальная вёрстка gemotest.103.kz/pricing/).
PRICING_HTML = """
<div class="PersonalOffersCategoryList">
  <div class="PersonalCardOfferItem">
    <div class="PersonalCardOfferItem__content">
      <div class="PersonalCardOfferItem__title">CHECK-UP №1 до старта гиполипидемической терапии</div>
    </div>
    <div class="PersonalCardOfferItem__footer"><div class="PersonalCardOfferItem__priceWrapper">
      <span class="PersonalCardOfferItem__price">10 030 тенге</span></div></div>
  </div>
  <div class="PersonalCardOfferItem">
    <div class="PersonalCardOfferItem__title">Общий анализ крови (CBC)</div>
    <div class="PersonalCardOfferItem__footer"><div class="PersonalCardOfferItem__priceWrapper">
      <span class="PersonalCardOfferItem__price">от 2 500 тенге</span></div></div>
  </div>
  <div class="PersonalCardOfferItem">
    <div class="PersonalCardOfferItem__title">Услуга без цены</div>
    <span class="PersonalCardOfferItem__price">уточняйте</span>
  </div>
</div>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"LocalBusiness","name":"Гемотест",
 "address":{"@type":"PostalAddress","addressLocality":"Алматы","addressCountry":"РК","streetAddress":"пр-т Сейфуллина, 565"},
 "telephone":"+7  800 070-13-13, 87012223344"}
</script>
"""

# Фрагмент листинга/sitemap: ссылки на субдомены клиник + инфраструктурные хосты.
LISTING_HTML = """
<a href="https://smart-med.103.kz/">Smart Med</a>
<a href="https://aqmed-1.103.kz/pricing/">AqMed</a>
<img src="https://ms1.103.kz/img/logo.png">
<a href="https://www.103.kz/list/analizy/almaty/">listing</a>
<a href="https://smart-med.103.kz/contacts/">дубль</a>
<a href="https://apteka.103.kz/">аптека</a>
"""


def test_extract_slugs_filters_infra_and_dedups():
    slugs = h._extract_slugs(LISTING_HTML)
    assert slugs == ["smart-med", "aqmed-1"]  # порядок сохранён, дубль схлопнут
    # инфраструктурные субдомены отсеяны
    assert "ms1" not in slugs and "www" not in slugs and "apteka" not in slugs


def test_localbusiness_meta_name_city_phone():
    meta = h._localbusiness_meta(PRICING_HTML)
    assert meta["name"] == "Гемотест"
    assert meta["city"] == "Алматы"
    assert meta["address"] == "пр-т Сейфуллина, 565"
    # телефон — первый номер из списка, схлопнутые пробелы
    assert meta["phone"].startswith("+7 800 070-13-13")


def test_103kz_adapter_parses_real_cards():
    items = ws._103kz(PRICING_HTML)
    by_name = {i.raw_name: i.price for i in items}
    assert by_name["CHECK-UP №1 до старта гиполипидемической терапии"] == 10030.0
    assert by_name["Общий анализ крови (CBC)"] == 2500.0   # «от 2 500» → нижняя граница
    assert "Услуга без цены" not in by_name                # «уточняйте» отброшено


def test_city_alias_mapping():
    assert h._city_slug("Алматы") == "almaty"
    assert h._city_slug("Усть-Каменогорск") == "uk"
    assert h._city_slug("astana") == "astana"  # уже slug — без изменений


def test_known_slugs_present():
    for must in ("gemotest", "invitro", "kdlolymp", "rahat"):
        assert must in h.KNOWN_SLUGS
