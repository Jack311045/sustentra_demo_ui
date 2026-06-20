"""
Adapters convert raw backend or mock API responses into internal UI-facing models.
Streamlit pages should depend on adapted data, not raw API payloads.
"""

from __future__ import annotations


def adapt_analysis_response(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    adapted = dict(raw)
    adapted.setdefault("summary", {})
    adapted.setdefault("evidence_results", [])
    adapted.setdefault("workbook_results", [])
    adapted.setdefault("gap_tickets", [])
    adapted.setdefault("chat_suggestions", [])
    adapted.setdefault("errors", [])
    adapted.setdefault("warnings", [])
    return adapted
