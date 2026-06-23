from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_gap_page(selected_gap_ticket_id: str | None = None) -> AppTest:
    response = _read_json("data/demo/mock_outputs/mock_analysis_response_gap_path.json")
    at = AppTest.from_file("pages/6_Gap_Analysis.py", default_timeout=45)
    at.session_state["analysis_response"] = response
    at.session_state["audit_setup"] = response.get("audit_setup") or {}
    if selected_gap_ticket_id:
        at.session_state["selected_gap_ticket_id"] = selected_gap_ticket_id
    at.run()
    return at


def test_gap_ticket_count_and_gap1_exclusion() -> None:
    tickets = _read_json("data/demo/mock_outputs/mock_gap_tickets.json")

    assert len(tickets) == 9
    ids = {str(item.get("gap_ticket_id")) for item in tickets}
    assert "GT-DEMO-GAP-001" not in ids


def test_gap_titles_are_auditor_facing() -> None:
    source = Path("pages/6_Gap_Analysis.py").read_text(encoding="utf-8")

    expected_titles = {
        "GT-DEMO-GAP-002": "Pilot-light emissions may be missing",
        "GT-DEMO-GAP-003": "October natural-gas usage does not match the source bill",
        "GT-DEMO-GAP-004": "Different combustion source types were combined",
        "GT-DEMO-GAP-005": "Biomass activity uses the wrong emission factor",
        "GT-DEMO-GAP-006": "Biomass sampling support is incomplete",
        "GT-DEMO-GAP-007": "December estimate lacks approved substitution support",
        "GT-DEMO-GAP-008": "Annual billing evidence is incomplete",
        "GT-DEMO-GAP-009": "Cross-year bill was not allocated between reporting years",
        "GT-DEMO-GAP-010": "Workbook uses the wrong GWP basis",
    }

    for ticket_id, title in expected_titles.items():
        assert ticket_id in source
        assert title in source


def test_gap_cards_have_traceability_links() -> None:
    tickets = _read_json("data/demo/mock_outputs/mock_gap_tickets.json")

    for ticket in tickets:
        assert isinstance(ticket.get("title"), str) and ticket.get("title")
        assert isinstance(ticket.get("finding_type"), str) and ticket.get("finding_type")
        assert isinstance(ticket.get("linked_evidence"), list)
        assert isinstance(ticket.get("linked_workbook_locations"), list)


def test_gap_analysis_actions_are_present() -> None:
    source = Path("pages/6_Gap_Analysis.py").read_text(encoding="utf-8")

    assert "Confirm" in source
    assert "Dismiss" in source
    assert "Request clarification" in source
    assert "Add auditor note" in source
    assert "Save note" in source
    assert "open_original_evidence" in source
    assert "open_workbook_location" in source
    assert "open_applicable_regulation" in source
    assert "ask_regulatory_assistant" in source
    assert "draft_auditor_note" in source


def test_gap_analysis_supports_selected_gap_deeplink_priority() -> None:
    source = Path("pages/6_Gap_Analysis.py").read_text(encoding="utf-8")

    assert "get_selected_gap_ticket_id" in source
    assert "Opened from Calculation & Reconciliation" in source
    assert "_ticket_sort_key" in source


def test_selected_gap_ticket_is_prioritized_in_runtime_order() -> None:
    selected_id = "GT-DEMO-GAP-003"
    at = _run_gap_page(selected_gap_ticket_id=selected_id)
    assert len(at.exception) == 0

    # First card action button should belong to the selected ticket.
    action_buttons = [button for button in at.button if str(getattr(button, "key", "")).endswith("_open_evidence")]
    assert action_buttons, "Expected at least one card action button"
    assert action_buttons[0].key.startswith(f"{selected_id}_")

    rendered = "\n".join(
        str(getattr(item, "value", "")) for item in at.caption if isinstance(getattr(item, "value", None), str)
    )
    assert "Opened from Calculation & Reconciliation" in rendered
