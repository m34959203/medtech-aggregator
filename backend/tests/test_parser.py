from app.ingestion.file_parser import parse_price, parse_csv, parse_excel
from app.ingestion import web_scraper, api_connector


def test_parse_price_formats():
    assert parse_price("12 500,00 ₸") == 12500.0
    assert parse_price("12500") == 12500.0
    assert parse_price("1 200 тг") == 1200.0
    assert parse_price("3 500,50") == 3500.5
    assert parse_price("бесплатно") is None
    assert parse_price(None) is None
    assert parse_price(0) is None


def test_parse_csv():
    csv = "Наименование услуги;Стоимость\nОбщий анализ крови;2500\nЭКГ;4000\n".encode("utf-8")
    items = parse_csv(csv)
    names = {i.raw_name for i in items}
    assert "Общий анализ крови" in names
    assert any(i.price == 4000 for i in items)


def test_parse_excel(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Услуга", "Цена, тг"])
    ws.append(["УЗИ брюшной полости", "9 500"])
    ws.append(["Приём терапевта", 6000])
    f = tmp_path / "p.xlsx"
    wb.save(f)
    items = parse_excel(f.read_bytes())
    assert len(items) == 2
    assert any("УЗИ" in i.raw_name for i in items)


def test_scrape_html_table():
    html = """
    <table>
      <tr><th>Услуга</th><th>Цена</th></tr>
      <tr><td>Общий анализ крови</td><td>2 500 ₸</td></tr>
      <tr><td>ЭКГ с расшифровкой</td><td>4000</td></tr>
    </table>
    """
    items = web_scraper.scrape_html(html)
    assert len(items) == 2
    assert any(i.price == 2500 for i in items)


def test_api_connector_json():
    payload = {"data": [
        {"name": "Общий анализ крови", "price": 2500},
        {"service": "ЭКГ", "cost": "4 000 тг"},
    ]}
    items = api_connector.items_from_json(payload)
    assert len(items) == 2
    assert any(i.price == 4000 for i in items)
