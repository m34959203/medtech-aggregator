"""Источник INVITRO (invitro.kz) — офлайн-парсинг каталога анализов.

Тест НЕ ходит в сеть и НЕ поднимает браузер: проверяем `parse_invitro_catalog`
на фикстуре реальной вёрстки `.analyzes-item` (Bitrix SSR — цена/срок в HTML).
"""
from app.ingestion import invitro_scraper as inv

# Фрагмент каталога /analizes/for-doctors/ (классы/структура — как на боевом сайте):
# имя в .analyzes-item__title a, цена в .analyzes-item__total--price,
# срок — в .analyzes-item__add--list-item span.
INVITRO_HTML = """
<div class="analyzes-list">
  <div class="analyzes-item ">
    <div class="analyzes-item__container">
      <div class="analyzes-item__base">
        <div class="analyzes-item__title">
          <a href="/analizes/for-doctors/156/2852/">Анализ крови. Общий анализ крови (без лейкоцитарной формулы и СОЭ) (CBC)</a>
        </div>
      </div>
      <div class="analyzes-item__add"><div class="analyzes-item__add--list">
        <div class="analyzes-item__add--list-item"><span>1 календарный день</span></div>
        <div class="analyzes-item__add--list-item"><span>Доступно с выездом на дом</span></div>
      </div></div>
      <div class="analyzes-item__total"><div class="analyzes-item__total--price">
        <div class="analyzes-item__total--sum">520 &#8378;</div></div></div>
    </div>
  </div>
  <div class="analyzes-item ">
    <div class="analyzes-item__title"><a href="/analizes/for-doctors/1854/21411/">Коронавирус SARS-CoV-2, определение РНК</a></div>
    <div class="analyzes-item__add--list-item"><span>До 3 рабочих дней</span></div>
    <div class="analyzes-item__total--price"><div class="analyzes-item__total--sum">8 400 &#8378;</div></div>
  </div>
  <!-- карточка без цены (например «уточняйте») — должна быть отброшена -->
  <div class="analyzes-item ">
    <div class="analyzes-item__title"><a href="/analizes/for-doctors/999/">Без цены</a></div>
  </div>
  <!-- дубликат первой карточки (на странице один анализ встречается в нескольких блоках) -->
  <div class="analyzes-item ">
    <div class="analyzes-item__title"><a href="#">Анализ крови. Общий анализ крови (без лейкоцитарной формулы и СОЭ) (CBC)</a></div>
    <div class="analyzes-item__total--price"><div class="analyzes-item__total--sum">520 &#8378;</div></div>
  </div>
</div>
"""


def test_parse_catalog_name_price_duration():
    items = inv.parse_invitro_catalog(INVITRO_HTML)
    by_name = {i.raw_name: i for i in items}

    # имя + цена + срок сняты корректно
    cbc = by_name["Анализ крови. Общий анализ крови (без лейкоцитарной формулы и СОЭ) (CBC)"]
    assert cbc.price == 520.0
    assert cbc.duration_days == 1
    assert cbc.currency == "KZT"

    cov = by_name["Коронавирус SARS-CoV-2, определение РНК"]
    assert cov.price == 8400.0
    assert cov.duration_days == 3  # «До 3 рабочих дней»

    # карточка без цены отброшена, дубликат схлопнут
    assert "Без цены" not in by_name
    assert len(items) == 2


def test_parse_catalog_respects_limit():
    items = inv.parse_invitro_catalog(INVITRO_HTML, limit=1)
    assert len(items) == 1


def test_catalog_url_city_routing():
    # default-город — базовый путь без slug; иначе slug в ПУТИ (не ?-параметр)
    assert inv.catalog_url("almaty").endswith("/analizes/for-doctors/")
    assert inv.catalog_url("astana").endswith("/analizes/for-doctors/astana/")
    # русское название → slug
    assert inv.catalog_url("Астана").endswith("/analizes/for-doctors/astana/")
    # путь не содержит query-параметров (важно: /*? запрещён robots.txt)
    assert "?" not in inv.catalog_url("shymkent")
