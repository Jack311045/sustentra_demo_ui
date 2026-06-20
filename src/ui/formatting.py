from __future__ import annotations


def safe_text(value) -> str:
    if value is None:
        return ""
    return str(value)
