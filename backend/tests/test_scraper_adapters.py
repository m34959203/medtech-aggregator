"""Адаптеры источников ТЗ §2.1 (офлайн, на фикстурах вёрстки реальных сайтов)."""
from app.ingestion import web_scraper as ws

# Минимальная вёрстка прайс-карточки KDL (kdlolymp.kz/pricelist/<филиал>):
# имя — текст карточки, цена в .price, служебные блоки .about/.buy отсеиваются.
KDL_HTML = """
<div class="analyzes">
  <div class="list">
    <a class="analysis active">
      Общий анализ крови (ОАК без СОЭ)
      <div class="about"><div class="category">Гематология</div><div class="duration">1 день</div></div>
      <div class="buy"><div class="price">1&nbsp;880 ₸</div><button class="todo">В корзину</button></div>
    </a>
    <a class="analysis">
      Глюкоза в крови
      <div class="about"><div class="category">Биохимия</div><div class="duration">1 день</div></div>
      <div class="buy"><div class="price">1&nbsp;340 ₸</div><button class="todo">В корзину</button></div>
    </a>
  </div>
</div>
"""


def test_kdl_adapter_dispatch_and_parse():
    # диспетчер выбирает KDL-адаптер по домену
    assert ws._adapter_for("https://www.kdlolymp.kz/pricelist/abay") is ws._kdl
    assert ws._adapter_for("https://kdl.kz/analyzes/") is ws._kdl

    items = ws._kdl(KDL_HTML)
    names = {i.raw_name: i.price for i in items}
    assert names.get("Общий анализ крови (ОАК без СОЭ)") == 1880.0
    assert names.get("Глюкоза в крови") == 1340.0
    # служебные блоки не утекли в имя
    assert all("В корзину" not in n and "Гематология" not in n for n in names)


def test_generic_table_fallback_for_unknown_host():
    # неизвестный домен → generic-парсер таблиц
    html = "<table><tr><td>УЗИ почек</td><td>5000</td></tr></table>"
    assert ws._adapter_for("https://some-clinic.kz/price") is None
    items = ws.scrape_html(html)
    assert any(i.raw_name == "УЗИ почек" and i.price == 5000.0 for i in items)
