from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.gap_analysis import build_gap_views, sort_gap_views
from src.ui.formatting import normalize_severity


PAGE_6 = Path("pages/6_Gap_Analysis.py")
GAP_HELPER = Path("src/ui/gap_analysis.py")
FIXTURE_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_gap_page(
    response: dict,
    *,
    created_gap_ticket_ids: list[str] | None = None,
    selected_gap_ticket_id: str | None = None,
    view_mode: str | None = None,
    severity_filter: str | None = None,
    mock_auditor_actions: dict | None = None,
    audit_setup: dict | None = None,
) -> AppTest:
    at = AppTest.from_file(str(PAGE_6), default_timeout=45)
    at.session_state["analysis_response"] = response
    at.session_state["audit_setup"] = audit_setup if audit_setup is not None else (response.get("audit_setup") or {})

    if created_gap_ticket_ids is not None:
        at.session_state["created_gap_ticket_ids"] = created_gap_ticket_ids
    if selected_gap_ticket_id is not None:
        at.session_state["selected_gap_ticket_id"] = selected_gap_ticket_id
    if view_mode is not None:
        at.session_state["gap_view_mode"] = view_mode
    if severity_filter is not None:
        at.session_state["gap_filter_severity"] = severity_filter
    if mock_auditor_actions is not None:
        at.session_state["mock_auditor_actions"] = mock_auditor_actions

    at.run()
    return at


def _master_buttons(at: AppTest):
    return [button for button in at.button if str(getattr(button, "key", "")).startswith("gap_master_select_")]


def _collect_rendered_text(at: AppTest) -> str:
    parts: list[str] = []
    for group in ("markdown", "caption", "text", "success", "warning", "error", "info"):
        for item in getattr(at, group):
            value = getattr(item, "value", None)
            if isinstance(value, str) and value.strip():
                parts.append(value)
    for button in at.button:
        label = getattr(button, "label", None)
        if isinstance(label, str) and label.strip():
            parts.append(label)
    return "\n".join(parts)


def test_gap_page_source_uses_master_detail_contract() -> None:
    source = PAGE_6.read_text(encoding="utf-8-sig")
    helper_source = GAP_HELPER.read_text(encoding="utf-8-sig")

    assert "Created Findings" in helper_source
    assert "All Findings" in helper_source
    for tab_label in ("Finding", "Evidence Trace", "Workbook Trace", "Regulatory Basis", "AI Reasoning"):
        assert tab_label in source

    assert "render_gap_card" not in source
    assert "st.json(" not in source
    assert "Needs confirmation" not in source
    assert "st.set_page_config(" in source
    assert 'layout="wide"' in source
    assert "_inject_page6_layout_style" in source
    assert "[1.7, 3.3]" in source
    assert "[1.25, 2.75]" not in source
    assert "st.columns(5" not in source
    assert "word-break: break-all" not in source
    assert "white-space: nowrap" not in source
    assert "_open_regulation_dialog_event" in source
    assert "gap_regulation_dialog_ticket_id" not in source
    assert "gap_request_clarification_open_" not in source
    assert "_render_regulation_dialog" not in source
    assert "_render_selected_finding_summary_cards" in source
    assert "row_label = title" in source
    assert "caption_parts = [ticket_id, *tags]" in source
    assert ".metric(" not in source


def test_gap_page_defaults_to_created_view_when_created_findings_exist() -> None:
    response = _read_json(FIXTURE_PATH)
    created_id = "GT-DEMO-GAP-003"

    at = _run_gap_page(response, created_gap_ticket_ids=[created_id])
    assert len(at.exception) == 0

    assert at.session_state["gap_view_mode"] == "Created Findings"
    assert at.session_state["selected_gap_ticket_id"] == created_id

    master_buttons = _master_buttons(at)
    assert len(master_buttons) == 1
    assert master_buttons[0].key == f"gap_master_select_{created_id}"


def test_gap_page_all_findings_view_respects_severity_filter() -> None:
    response = _read_json(FIXTURE_PATH)
    all_views = sort_gap_views(build_gap_views(response.get("gap_tickets") or [], set(), {}))
    expected_critical_ids = {
        str(view.get("id"))
        for view in all_views
        if normalize_severity(view.get("effective_severity")) == "critical"
    }

    at = _run_gap_page(
        response,
        view_mode="All Findings",
        severity_filter="Critical",
    )
    assert len(at.exception) == 0

    button_ids = {
        str(button.key).replace("gap_master_select_", "")
        for button in _master_buttons(at)
    }
    assert button_ids == expected_critical_ids


def test_gap_page_actions_and_no_needs_confirmation_at_runtime() -> None:
    response = _read_json(FIXTURE_PATH)
    at = _run_gap_page(response, selected_gap_ticket_id="GT-DEMO-GAP-003")

    assert len(at.exception) == 0
    rendered = _collect_rendered_text(at)

    assert "Open evidence" in rendered
    assert "Open workbook location" in rendered
    assert "Show regulation" in rendered
    assert "Ask Sustentra AI Assistant" in rendered
    assert "Draft auditor note" in rendered
    assert "Confirm" in rendered
    assert "Dismiss" in rendered
    assert "Request clarification" in rendered
    assert "Save note" in rendered
    assert "Needs confirmation" not in rendered


def test_selected_gap_deeplink_remains_selected() -> None:
    response = _read_json(FIXTURE_PATH)
    selected_id = "GT-DEMO-GAP-006"

    at = _run_gap_page(response, selected_gap_ticket_id=selected_id, view_mode="All Findings")
    assert len(at.exception) == 0

    assert at.session_state["selected_gap_ticket_id"] == selected_id
    rendered = _collect_rendered_text(at)
    assert "Opened from upstream workflow context" in rendered


def test_master_list_buttons_do_not_embed_ticket_ids_in_labels() -> None:
    response = _read_json(FIXTURE_PATH)

    at = _run_gap_page(response, view_mode="All Findings")
    assert len(at.exception) == 0

    for button in _master_buttons(at):
        label = str(getattr(button, "label", "") or "")
        assert "GT-DEMO-GAP-" not in label


def test_request_clarification_prefills_dialog_fields_from_setup_and_ticket() -> None:
    response = _read_json(FIXTURE_PATH)
    ticket_id = "GT-DEMO-GAP-003"

    audit_setup = {
        "company_and_facility_profile": {
            "facility_name": "Anheuser-Busch Baldwinsville Brewery",
            "reporting_period": "2023-01-01 to 2023-12-31",
            "client_contact_name": "Dana Whitfield",
            "client_contact_email": "dana.whitfield@ab-baldwinsville.example.com",
        }
    }

    at = _run_gap_page(
        response,
        selected_gap_ticket_id=ticket_id,
        audit_setup=audit_setup,
    )
    assert len(at.exception) == 0

    at.button(key=f"gap_decision_clarify_{ticket_id}").click().run()
    assert len(at.exception) == 0

    to_key = f"gap_clarify_to::{ticket_id}"
    subject_key = f"gap_clarify_subject::{ticket_id}"
    message_key = f"gap_clarify_message::{ticket_id}"

    assert to_key in at.session_state
    assert subject_key in at.session_state
    assert message_key in at.session_state
    assert at.session_state[to_key] == "dana.whitfield@ab-baldwinsville.example.com"
    assert ticket_id in str(at.session_state[subject_key])

    message = str(at.session_state[message_key])
    assert message.startswith("Hi Dana,")
    assert "What we observed:" in message
    assert "What NY Part 253 requires:" in message
    assert "To resolve this:" in message

    button_keys = {str(getattr(button, "key", "")) for button in at.button}
    assert f"gap_clarify_send_{ticket_id}" in button_keys
    assert f"gap_clarify_cancel_{ticket_id}" in button_keys


def test_gap_010_clarification_uses_neutral_confirmation_language() -> None:
    response = _read_json(FIXTURE_PATH)
    ticket_id = "GT-DEMO-GAP-010"

    at = _run_gap_page(response, selected_gap_ticket_id=ticket_id)
    assert len(at.exception) == 0

    at.button(key=f"gap_decision_clarify_{ticket_id}").click().run()
    assert len(at.exception) == 0

    message = str(at.session_state[f"gap_clarify_message::{ticket_id}"])
    assert "What requires confirmation:" in message
    assert "What NY Part 253 requires:" not in message


def test_request_clarification_not_opened_by_unrelated_actions() -> None:
    response = _read_json(FIXTURE_PATH)
    ticket_id = "GT-DEMO-GAP-003"

    at = _run_gap_page(response, selected_gap_ticket_id=ticket_id)
    assert len(at.exception) == 0

    at.button(key=f"gap_action_draft_note_{ticket_id}").click().run()
    assert len(at.exception) == 0
    assert f"gap_clarify_to::{ticket_id}" not in at.session_state

    at.button(key=f"gap_decision_confirm_{ticket_id}").click().run()
    assert len(at.exception) == 0
    assert f"gap_clarify_to::{ticket_id}" not in at.session_state


def test_opening_clarification_dialog_preserves_existing_action_and_note() -> None:
    response = _read_json(FIXTURE_PATH)
    ticket_id = "GT-DEMO-GAP-003"

    at = _run_gap_page(
        response,
        selected_gap_ticket_id=ticket_id,
        mock_auditor_actions={
            ticket_id: {
                "action": "Dismiss",
                "note": "Keep prior note",
            }
        },
    )
    assert len(at.exception) == 0

    at.button(key=f"gap_decision_clarify_{ticket_id}").click().run()
    assert len(at.exception) == 0

    overlay = at.session_state["mock_auditor_actions"][ticket_id]
    assert overlay.get("action") == "Dismiss"
    assert overlay.get("note") == "Keep prior note"


def test_clarification_send_cancel_contract_is_present_in_source() -> None:
    source = PAGE_6.read_text(encoding="utf-8-sig")

    assert 'key=f"gap_clarify_send_{ticket_id}"' in source
    assert 'key=f"gap_clarify_cancel_{ticket_id}"' in source
    assert '"action": "Request clarification"' in source
    assert '"clarification_sent": True' in source
    assert '"clarification_to": recipient.strip()' in source
    assert '"clarification_subject": subject.strip()' in source
    assert '"clarification_message": message.strip()' in source
