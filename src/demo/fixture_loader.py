from __future__ import annotations

import json
from pathlib import Path


def load_demo_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
