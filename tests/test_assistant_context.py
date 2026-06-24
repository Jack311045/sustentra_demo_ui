from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from src.ui.assistant_context import build_assistant_context


FIXTURE_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))


def test_context_builder_is_deterministic_and_does_not_mutate_inputs(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_CONTEXT_MAX_CHARS", "60000")

    response = _load_fixture()
    audit_setup = deepcopy(response.get("audit_setup") or {})

    first_evidence_id = str((response.get("evidence_results") or [{}])[0].get("evidence_id") or "")
    first_validation_id = str((response.get("validation_results") or [{}])[0].get("validation_id") or "")
    first_calculation_id = str((response.get("calculation_results") or [{}])[0].get("calculation_id") or "")
    first_gap_id = str((response.get("gap_tickets") or [{}])[0].get("gap_ticket_id") or "")

    reviewed_fields = {
        first_evidence_id: {
            "supplier_name": {"status": "Edited", "edited_value": "Edited Supplier"},
        }
    }

    baseline_response = deepcopy(response)
    baseline_setup = deepcopy(audit_setup)
    baseline_reviewed = deepcopy(reviewed_fields)

    kwargs = {
        "analysis_response": response,
        "audit_setup": audit_setup,
        "selected_gap_ticket_id": first_gap_id,
        "reviewed_extraction_fields": reviewed_fields,
        "created_gap_ticket_ids": [first_gap_id],
        "gap_ticket_overrides": {first_gap_id: {"status": "confirmed", "action": "accept"}},
        "active_selection": {
            "selected_evidence_id": first_evidence_id,
            "selected_validation_id": first_validation_id,
            "selected_calculation_id": first_calculation_id,
            "selected_workbook_location": {"sheet_name": "Summary", "cell_or_range": "D12"},
        },
    }

    context_a = build_assistant_context(**kwargs)
    context_b = build_assistant_context(**kwargs)

    assert context_a == context_b
    assert response == baseline_response
    assert audit_setup == baseline_setup
    assert reviewed_fields == baseline_reviewed

    assert context_a.get("context_version") == "1.0"
    assert isinstance(context_a.get("included_counts"), dict)
    assert isinstance(context_a.get("truncated"), bool)


def test_context_builder_reports_truncation_when_budget_is_low(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_CONTEXT_MAX_CHARS", "10000")

    response = _load_fixture()
    context = build_assistant_context(
        analysis_response=response,
        audit_setup=response.get("audit_setup") or {},
        selected_gap_ticket_id="GT-DEMO-GAP-003",
        reviewed_extraction_fields={},
        created_gap_ticket_ids=[],
        gap_ticket_overrides={},
        active_selection={},
    )

    assert context.get("truncated") is True
    included = context.get("included_counts") if isinstance(context.get("included_counts"), dict) else {}
    assert int(included.get("context_size_chars") or 0) > 0


def test_context_builder_redacts_secret_like_values(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_CONTEXT_MAX_CHARS", "60000")

    response = _load_fixture()
    context = build_assistant_context(
        analysis_response=response,
        audit_setup=response.get("audit_setup") or {},
        selected_gap_ticket_id="GT-DEMO-GAP-003",
        reviewed_extraction_fields={},
        created_gap_ticket_ids=[],
        gap_ticket_overrides={},
        active_selection={
            "selected_workbook_location": {
                "sheet_name": "Summary",
                "cell_or_range": "A1",
                "api_key": "sk-test-secret",
                "authorization": "Bearer abc123token",
                "note": "api_key=my-secret-key",
            }
        },
    )

    payload = json.dumps(context).lower()
    assert "sk-test-secret" not in payload
    assert "abc123token" not in payload
    assert "my-secret-key" not in payload
    assert "[redacted]" in payload
