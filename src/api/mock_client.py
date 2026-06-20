"""
Mock API client for demo UI development before the real backend endpoint is ready.
"""

from __future__ import annotations

import json
from pathlib import Path


MOCK_ANALYSIS_RESPONSE = Path("data/demo/mock_outputs/mock_analysis_response.json")


class MockApiClient:
    def analyze(self) -> dict:
        if MOCK_ANALYSIS_RESPONSE.exists():
            try:
                return json.loads(MOCK_ANALYSIS_RESPONSE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        return {
            "run_id": "mock-run",
            "status": "not_started",
            "generated_at": None,
            "synthetic_demo_data": True,
            "engagement": {},
            "library_references": {},
            "summary": {},
            "evidence_results": [],
            "workbook_results": [],
            "gap_tickets": [],
            "chat_suggestions": [],
            "errors": [],
            "warnings": [
                "Mock analysis file is missing or invalid. Loaded empty demo response."
            ],
        }
