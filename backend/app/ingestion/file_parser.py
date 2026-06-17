"""Парсер файлов-прайсов (канал ① push).

Извлекает из сырого файла список позиций {raw_name, price} независимо от того,
как именно клиника назвала колонки. Поддержка: Excel (.xlsx/.xls), CSV, PDF.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class RawItem:
    raw_name: str
    price: float


# Возможные названия колонок с услугой и ценой (в т.ч. русские/казахские/англ.)
NAME_HINTS = [
    "наименование", "услуга", "услуги", "название", "name", "service",
    "атауы", "қызмет", "процедура", "анализ", "исследование",
]
PRICE_HINTS = [
    "цена", "стоимость", "тариф", "price", "cost", "руб", "тенге", "тг",
    "бағасы", "құны", "сом", "kzt",
]

_PRICE_RE = re.compile(r"[\d][\d\s .,]*")


def parse_price(value) -> float | None:
    """Приводит '12 500,00 ₸' / '12500' / '12.500' к float."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value > 0 else None
    s = str(value)
    m = _PRICE_RE.search(s)
    if not m:
        return None
    token = m.group(0).strip().replace(" ", "").replace(" ", "")
    # Если есть и точка и запятая — запятая десятичная (рус), точка — разряды.
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        # запятая как десятичный разделитель только если 1-2 знака после
        if re.search(r",\d{1,2}$", token):
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
    try:
        val = float(token)
    except ValueError:
        return None
    return val if val > 0 else None


def _score_header(cell: str, hints: list[str]) -> int:
    cell = str(cell).strip().lower()
    return sum(1 for h in hints if h in cell)


def _pick_columns(df: pd.DataFrame) -> tuple[int, int] | None:
    """Возвращает индексы (name_col, price_col), угадывая по заголовкам и данным."""
    name_col = price_col = None
    name_best = price_best = 0
    for i, col in enumerate(df.columns):
        ns = _score_header(col, NAME_HINTS)
        ps = _score_header(col, PRICE_HINTS)
        if ns > name_best:
            name_best, name_col = ns, i
        if ps > price_best:
            price_best, price_col = ps, i

    # Фоллбэк по содержимому: колонка цены — где больше всего парсится чисел.
    if price_col is None:
        best_ratio = 0.0
        for i in range(df.shape[1]):
            vals = df.iloc[:, i].tolist()
            ok = sum(1 for v in vals if parse_price(v) is not None)
            ratio = ok / max(len(vals), 1)
            if ratio > best_ratio and ratio > 0.3:
                best_ratio, price_col = ratio, i
    if name_col is None:
        # колонка имени — самая «текстовая», не совпадающая с ценовой
        best_len = 0
        for i in range(df.shape[1]):
            if i == price_col:
                continue
            vals = df.iloc[:, i].astype(str).tolist()
            avg_len = sum(len(v) for v in vals) / max(len(vals), 1)
            non_numeric = sum(1 for v in vals if parse_price(v) is None)
            if avg_len > best_len and non_numeric > len(vals) * 0.5:
                best_len, name_col = avg_len, i
    if name_col is None or price_col is None:
        return None
    return name_col, price_col


def _items_from_df(df: pd.DataFrame) -> list[RawItem]:
    cols = _pick_columns(df)
    if not cols:
        return []
    name_col, price_col = cols
    items: list[RawItem] = []
    for _, row in df.iterrows():
        name = str(row.iloc[name_col]).strip()
        price = parse_price(row.iloc[price_col])
        if not name or name.lower() in ("nan", "none", "") or price is None:
            continue
        if len(name) < 2:
            continue
        items.append(RawItem(raw_name=name, price=price))
    return items


def parse_excel(content: bytes) -> list[RawItem]:
    xls = pd.ExcelFile(io.BytesIO(content))
    items: list[RawItem] = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet, header=0, dtype=object)
        got = _items_from_df(df)
        if not got:  # вдруг заголовок не в первой строке
            df2 = xls.parse(sheet, header=None, dtype=object)
            got = _items_from_df(df2)
        items.extend(got)
    return items


def parse_csv(content: bytes) -> list[RawItem]:
    # Пробуем все разделители и берём давший БОЛЬШЕ всего позиций, а не первый
    # успешный: автодетект (sep=None) путает запятую в тексте (";"-файл с
    # "Тариф, тенге" в шапке) с настоящим разделителем и теряет строки.
    best: list[RawItem] = []
    best_key = (0, 0)  # (число позиций, число колонок)
    for sep in (";", ",", "\t", None):
        try:
            df = pd.read_csv(io.BytesIO(content), sep=sep, engine="python", dtype=object)
        except Exception:
            continue
        got = _items_from_df(df)
        # тай-брейк по колонкам: верный делимитер делит строку на ≥2 колонки,
        # ошибочный (";"-файл, прочитанный как один столбец) слепляет имя с ценой
        key = (len(got), df.shape[1])
        if got and key > best_key:
            best, best_key = got, key
    return best


def parse_pdf(content: bytes) -> list[RawItem]:
    import pdfplumber

    items: list[RawItem] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                if not table or len(table) < 2:
                    continue
                df = pd.DataFrame(table[1:], columns=range(len(table[0])))
                items.extend(_items_from_df(df))
            if not tables:
                # текстовый фоллбэк: строки вида "Услуга .... 12 500"
                text = page.extract_text() or ""
                for line in text.splitlines():
                    m = re.search(r"^(.*?)[\s.]{2,}([\d\s .,]+)$", line.strip())
                    if m:
                        price = parse_price(m.group(2))
                        name = m.group(1).strip()
                        if price and len(name) > 2:
                            items.append(RawItem(raw_name=name, price=price))
    return items


def detect_and_parse(filename: str, content: bytes) -> tuple[str, list[RawItem]]:
    """Определяет формат по расширению и парсит. Возвращает (format, items)."""
    fn = filename.lower()
    if fn.endswith((".xlsx", ".xls")):
        return "xlsx", parse_excel(content)
    if fn.endswith(".csv"):
        return "csv", parse_csv(content)
    if fn.endswith(".pdf"):
        return "pdf", parse_pdf(content)
    # попытка угадать по содержимому
    if content[:4] == b"%PDF":
        return "pdf", parse_pdf(content)
    if content[:2] == b"PK":
        return "xlsx", parse_excel(content)
    return "csv", parse_csv(content)
