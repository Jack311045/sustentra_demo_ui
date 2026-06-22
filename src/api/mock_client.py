"""
Mock API client for demo UI development before the real backend endpoint is ready.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.api.adapters import normalize_audit_setup


MOCK_OUTPUT_DIR = Path("data/demo/mock_outputs")
MOCK_ANALYSIS_RESPONSE = MOCK_OUTPUT_DIR / "mock_analysis_response.json"

SCENARIO_FILE_MAP = {
    "gap_path": MOCK_OUTPUT_DIR / "mock_analysis_response_gap_path.json",
    "clean_path": MOCK_OUTPUT_DIR / "mock_analysis_response_clean_path.json",
}


def _load_json_file(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def _fallback_empty_response() -> dict:
    return {
        "run_id": "mock-run",
        "status": "not_started",
        "generated_at": None,
        "synthetic_demo_data": True,
        "engagement": {},
        "library_references": {},
        "summary": {},
        "audit_setup": {},
        "uploaded_demo_files": {},
        "evidence_results": [],
        "validation_results": [],
        "calculation_results": [],
        "reconciliation_summary": {},
        "workbook_results": [],
        "gap_tickets": [],
        "chat_suggestions": [],
        "errors": [],
        "warnings": [
            "Mock analysis file is missing or invalid. Loaded empty demo response.",
        ],
    }


class MockApiClient:
    def analyze(self, scenario_id: str = "gap_path") -> dict:
        candidate = SCENARIO_FILE_MAP.get(str(scenario_id), SCENARIO_FILE_MAP["gap_path"])

        payload = _load_json_file(candidate)
        if isinstance(payload, dict):
            payload["audit_setup"] = normalize_audit_setup(payload.get("audit_setup"))
            return payload

        fallback_payload = _load_json_file(MOCK_ANALYSIS_RESPONSE)
        if isinstance(fallback_payload, dict):
            fallback_payload["audit_setup"] = normalize_audit_setup(fallback_payload.get("audit_setup"))
            return fallback_payload

        return _fallback_empty_response()

    def load_audit_setup(self) -> dict:
        payload = _load_json_file(MOCK_OUTPUT_DIR / "mock_audit_setup.json")
        return normalize_audit_setup(payload if isinstance(payload, dict) else {})
