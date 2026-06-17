"""Генерирует демо-прайсы клиник в разных форматах для показа конвейера приёма.

Запуск: python make_samples.py  → файлы в sample_data/
Эти файлы можно грузить через POST /api/ingest/upload, чтобы показать,
как разные форматы и разнобой названий сводятся к одному справочнику.
"""
import csv
import os

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_data")
os.makedirs(SAMPLE_DIR, exist_ok=True)

# Клиника А — Excel, свои названия
EXCEL_ROWS = [
    ("Наименование услуги", "Цена, тг"),
    ("Общий анализ крови (развёрнутый)", "2 800"),
    ("Биохимический анализ крови", "9 200"),
    ("Анализ мочи общий", "1 700"),
    ("Приём врача-терапевта (первичный)", "6 500"),
    ("УЗИ органов брюшной полости", "9 800"),
    ("ЭКГ с расшифровкой", "4 200"),
    ("МРТ головного мозга", "33 000"),
]

# Клиника Б — CSV, другие названия той же сути
CSV_ROWS = [
    ("Услуга", "Стоимость (KZT)"),
    ("ОАК", "2 300"),
    ("Биохимия крови", "8 900"),
    ("Глюкоза крови", "1 500"),
    ("Консультация терапевта", "5 900"),
    ("УЗИ брюшной полости", "9 100"),
    ("Электрокардиограмма", "3 900"),
    ("Лечение кариеса", "16 000"),
]

# Клиника В — HTML (как со страницы сайта)
HTML_PRICELIST = """<!doctype html><html><head><meta charset="utf-8"><title>Прайс клиники</title></head>
<body>
<h1>Прайс-лист медицинских услуг</h1>
<table>
  <tr><th>Услуга</th><th>Цена</th></tr>
  <tr><td>Кровь — общий анализ</td><td>2 100 ₸</td></tr>
  <tr><td>Анализ крови на глюкозу</td><td>1 400 ₸</td></tr>
  <tr><td>Терапевт (консультация)</td><td>5 500 ₸</td></tr>
  <tr><td>УЗИ щитовидной железы</td><td>7 000 ₸</td></tr>
  <tr><td>Рентген грудной клетки</td><td>3 500 ₸</td></tr>
  <tr><td>Приём кардиолога</td><td>11 500 ₸</td></tr>
</table>
</body></html>"""

# Клиника Г — JSON (как из API)
JSON_PAYLOAD = {
    "clinic": "Astana Medical",
    "currency": "KZT",
    "services": [
        {"name": "Общий анализ крови развёрнутый", "price": 2700},
        {"name": "Биохимический анализ крови", "price": 10500},
        {"name": "Приём гинеколога", "price": 11000},
        {"name": "КТ грудной клетки", "price": 28000},
        {"name": "УЗИ щитовидки", "price": 7500},
        {"name": "МРТ головного мозга с контрастом", "price": 45000},
    ],
}


def main():
    import json
    import openpyxl

    # Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Прайс"
    for row in EXCEL_ROWS:
        ws.append(row)
    wb.save(os.path.join(SAMPLE_DIR, "clinic_sunkar_pricelist.xlsx"))

    # CSV
    with open(os.path.join(SAMPLE_DIR, "clinic_avicenna_pricelist.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerows(CSV_ROWS)

    # HTML
    with open(os.path.join(SAMPLE_DIR, "clinic_diagnostika_page.html"), "w", encoding="utf-8") as f:
        f.write(HTML_PRICELIST)

    # JSON
    with open(os.path.join(SAMPLE_DIR, "clinic_astana_api.json"), "w", encoding="utf-8") as f:
        json.dump(JSON_PAYLOAD, f, ensure_ascii=False, indent=2)

    # PDF (через reportlab если есть, иначе пропустить)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        path = os.path.join(SAMPLE_DIR, "clinic_zhan_pricelist.pdf")
        c = canvas.Canvas(path, pagesize=A4)
        c.setFont("Helvetica", 12)
        y = 800
        c.drawString(50, y, "Price-list (medical services)")
        y -= 30
        pdf_rows = [
            ("Common blood test", "1900"),
            ("Abdominal ultrasound", "8800"),
            ("ECG", "3800"),
            ("Chest X-ray", "2000"),
            ("Caries treatment", "15000"),
        ]
        for name, price in pdf_rows:
            c.drawString(50, y, f"{name} .......... {price}")
            y -= 22
        c.save()
        print("PDF создан.")
    except ImportError:
        print("reportlab нет — PDF пропущен (для теста PDF используйте свой файл).")

    print(f"Готово. Файлы в {SAMPLE_DIR}:")
    for f in sorted(os.listdir(SAMPLE_DIR)):
        print("  -", f)


if __name__ == "__main__":
    main()
