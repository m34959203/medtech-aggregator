"""§2.1/§5 MedArchive: сохранение ОРИГИНАЛОВ загруженных прайс-файлов.

Исходники не удаляются — лежат на диске для повторной обработки и аудита.
Раскладка: <archive_storage_dir>/<run_id>/<санитизированное_имя>.
"""
from __future__ import annotations

import os
import re

from ..config import settings

_SAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def _safe_name(filename: str) -> str:
    base = os.path.basename(filename or "file").strip() or "file"
    base = _SAFE.sub("_", base)
    return base[:180] or "file"


def store_original(run_id: int, filename: str, content: bytes) -> str:
    """Кладёт оригинал в <storage>/<run_id>/<имя>. → относительный путь (в БД)."""
    root = settings.archive_storage_dir
    rel_dir = os.path.join(root, str(run_id))
    os.makedirs(rel_dir, exist_ok=True)
    rel_path = os.path.join(rel_dir, _safe_name(filename))
    with open(rel_path, "wb") as f:
        f.write(content)
    return rel_path


def read_original(file_path: str) -> bytes:
    """Читает сохранённый оригинал для повторной обработки. FileNotFoundError если нет."""
    with open(file_path, "rb") as f:
        return f.read()
