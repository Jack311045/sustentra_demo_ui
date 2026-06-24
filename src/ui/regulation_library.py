from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LIBRARY_PATH = Path("data/demo/reference/regulation_library.json")
PENDING_REVIEW_TEXT = "Verified regulation text is pending review."


def build_regulation_key(authority: Any, citation: Any) -> str:
    return f"{str(authority or '').strip()}|{str(citation or '').strip()}"


@lru_cache(maxsize=8)
def _load_cached(path_value: str, modified_ns: int) -> dict[str, dict]:
    path = Path(path_value)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    cleaned: dict[str, dict] = {}
    for raw_key, raw_entry in payload.items():
        key = str(raw_key or "").strip()
        if not key or not isinstance(raw_entry, dict):
            continue
        cleaned[key] = {
            "title": str(raw_entry.get("title") or "").strip(),
            "text": str(raw_entry.get("text") or "").strip(),
            "source_url": str(raw_entry.get("source_url") or "").strip(),
        }
    return cleaned


def load_regulation_library(path: str | Path | None = None) -> dict[str, dict]:
    target = Path(path) if path else DEFAULT_LIBRARY_PATH
    try:
        modified_ns = target.stat().st_mtime_ns
    except OSError:
        modified_ns = -1

    cached = _load_cached(str(target), int(modified_ns))
    return deepcopy(cached)


def lookup_regulation_entry(
    authority: Any,
    citation: Any,
    *,
    library: dict[str, dict] | None = None,
) -> dict | None:
    source = library if isinstance(library, dict) else load_regulation_library()
    key = build_regulation_key(authority, citation)
    entry = source.get(key)
    if not isinstance(entry, dict):
        return None
    return deepcopy(entry)


def resolve_regulation_display(
    authority: Any,
    citation: Any,
    *,
    applicability_explanation: Any = None,
    library: dict[str, dict] | None = None,
) -> dict:
    entry = lookup_regulation_entry(authority, citation, library=library)
    title = str((entry or {}).get("title") or "").strip()
    text = str((entry or {}).get("text") or "").strip()
    source_url = str((entry or {}).get("source_url") or "").strip()

    return {
        "key": build_regulation_key(authority, citation),
        "authority": str(authority or "").strip(),
        "citation": str(citation or "").strip(),
        "title": title,
        "text": text,
        "source_url": source_url,
        "applicability_explanation": str(applicability_explanation or "").strip(),
        "has_verified_text": bool(text),
        "pending_text": PENDING_REVIEW_TEXT if not text else "",
    }
