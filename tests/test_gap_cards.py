from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
