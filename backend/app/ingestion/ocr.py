"""OCR прайсов-сканов и фото (Спринт-3): tesseract (рус/каз/англ).

Картинка/скан → текст → дальше тот же парсер строк, что и для текстового PDF.
Зависит от системного tesseract (ставится в Docker-образ). Если бинарь/пакет
отсутствует — `ocr_available()` вернёт False, а приём деградирует понятной ошибкой.
"""
from __future__ import annotations

import io
import shutil


def ocr_available() -> bool:
    """Установлен ли pytesseract и системный бинарь tesseract."""
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return shutil.which("tesseract") is not None


def _langs() -> str:
    """Доступные из нужных языков (рус/каз/англ), с деградацией."""
    try:
        import pytesseract
        have = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    want = [lang for lang in ("rus", "kaz", "eng") if lang in have]
    return "+".join(want) or "eng"


def image_to_text(content: bytes) -> str:
    """OCR одного изображения (png/jpg/tiff/...)."""
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(content))
    return pytesseract.image_to_string(img, lang=_langs())


def pdf_to_text_ocr(content: bytes, max_pages: int = 15, dpi: int = 200) -> str:
    """OCR сканированного PDF: рендерим страницы (PyMuPDF) и распознаём."""
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    out: list[str] = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img, lang=_langs()))
    return "\n".join(out)
