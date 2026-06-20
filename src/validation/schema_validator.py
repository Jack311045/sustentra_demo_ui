from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_json(data: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [error.message for error in validator.iter_errors(data)]
