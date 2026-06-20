from __future__ import annotations

from pathlib import Path


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".json"}


def is_allowed_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in ALLOWED_EXTENSIONS
