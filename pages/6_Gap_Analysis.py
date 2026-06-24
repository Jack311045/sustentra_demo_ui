from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui.components import render_audit_setup_context
from src.ui.gap_analysis import (
    NOT_AVAILABLE_FALLBACK,
    VIEW_MODE_ALL,
    VIEW_MODE_CREATED,
    apply_gap_filters,
    build_gap_views,
    derive_summary_counts,
    ensure_selected_gap_id,
    find_gap_view,
    gap_filter_options,
    sort_gap_views,
)
from src.ui.regulation_library import load_regulation_library, resolve_regulation_display
from src.ui.state import (
    ask_regulatory_assistant,
    get_audit_setup,
    get_analysis_response,
    get_created_gap_ticket_ids,
    get_gap_ticket_overrides,
    get_selected_gap_ticket_id,
    init_session_state,
    open_original_evidence,
    open_workbook_location,
    set_selected_gap_ticket_id,
    update_mock_auditor_action,
)
from src.ui.traceability import (
    render_ai_reasoning,
    render_evidence_trace,
    render_reasoning_trail,
    render_regulatory_basis,
    summarize_workbook_trace,
)
from src.ui.workflow import render_prepared_demo_disclosure


VIEW_MODE_KEY = "gap_view_mode"
SEVERITY_FILTER_KEY = "gap_filter_severity"
STATUS_FILTER_KEY = "gap_filter_status"
CATEGORY_FILTER_KEY = "gap_filter_category"
ASSERTION_FILTER_KEY = "gap_filter_assertion"
ACTION_FEEDBACK_KEY = "gap_action_feedback_by_ticket"
NOTE_FEEDBACK_KEY = "gap_note_feedback_by_ticket"


def _dialog_decorator():
    return getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)


def _note_widget_key(ticket_id: str) -> str:
    return f"gap_note_widget::{ticket_id}"


def _clarify_message_key(ticket_id: str) -> str:
    return f"gap_clarify_message::{ticket_id}"


def _clarify_to_key(ticket_id: str) -> str:
    return f"gap_clarify_to::{ticket_id}"


def _clarify_subject_key(ticket_id: str) -> str:
    return f"gap_clarify_subject::{ticket_id}"


def _inject_page6_layout_style() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stAppViewContainer"]
        div[data-testid="stMainBlockContainer"] {
            width: 100% !important;
            max-width: none !important;
            box-sizing: border-box !important;
            padding-left: clamp(0.8rem, 1.3vw, 1.6rem) !important;
            padding-right: clamp(0.8rem, 1.3vw, 1.6rem) !important;
            padding-top: 1rem !important;
        }

        section.main .block-container {
            width: 100% !important;
            max-width: none !important;
            box-sizing: border-box !important;
            padding-left: clamp(0.8rem, 1.3vw, 1.6rem) !important;
            padding-right: clamp(0.8rem, 1.3vw, 1.6rem) !important;
        }

        div[data-testid="column"] {
            min-width: 0 !important;
        }

        div[data-testid="stButton"] > button {
            white-space: normal !important;
            word-break: normal !important;
            overflow-wrap: break-word !important;
            line-height: 1.25 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


CLARIFICATION_DRAFTS = {
    "GT-DEMO-GAP-002": (
        "What we observed: the equipment inventory and workbook exclude pilot "
        "light sources, citing 40 CFR 98.30(d).\n"
        "What NY Part 253 requires: pilot light emissions must be included in "
        "the emissions data report (NY Part 253 253-2.7(j)); the federal "
        "exemption does not carry over to the NY basis.\n"
        "To resolve this: please provide either the pilot light sources added "
        "to the inventory, or an engineering / common-fuel-source aggregation "
        "that supports their inclusion, so we can recalculate the affected "
        "Scope 1 emissions."
    ),
    "GT-DEMO-GAP-003": (
        "What we observed: the Natural Gas worksheet records October usage as "
        "281,000 MMBtu, while the October utility bill shows 28,100 MMBtu - a "
        "10x difference.\n"
        "What NY Part 253 requires: individual fuel volumes must be traceable "
        "to billing or meter evidence for the same service period "
        "(NY Part 253 253-2.7(h)).\n"
        "To resolve this: please confirm the correct October quantity and "
        "provide the supporting utility bill or meter read, so we can "
        "reconcile the workbook entry (Natural Gas!D12) and reperform the "
        "monthly and annual totals."
    ),
    "GT-DEMO-GAP-004": (
        "What we observed: the Emissions Summary combines the natural gas "
        "boilers and the diesel emergency generator into a single CO2e line.\n"
        "What NY Part 253 requires: aggregation must preserve source-type and "
        "unit-type distinctions so each calculation method can be verified "
        "(NY Part 253 253-2.7(i)).\n"
        "To resolve this: please provide a breakdown that separates the boiler "
        "and generator activity data and emission factors, so each source "
        "category can be independently traced."
    ),
    "GT-DEMO-GAP-005": (
        "What we observed: the Biomass Boiler worksheet identifies August and "
        "September fuel as solid biomass residue but applies the natural gas "
        "CO2 factor of 53.06 kg CO2/MMBtu.\n"
        "What NY Part 253 requires: the emission factor and method must match "
        "the actual fuel type, with fossil and biogenic CO2 treated separately "
        "(NY Part 253 253-2.7(a) and 253-2.7(e)).\n"
        "To resolve this: please confirm the August and September fuel type and "
        "provide the biomass calculation basis, so we can apply the correct "
        "factor and biogenic treatment."
    ),
    "GT-DEMO-GAP-006": (
        "What we observed: the evidence pack contains a single end-of-period "
        "biomass fuel lab report, but no weekly sample logs, composite "
        "preparation record, or sampling protocol.\n"
        "What NY Part 253 requires: partially biogenic fuel fractions must be "
        "supported by a weekly sampling chain and documented monthly composite "
        "preparation (NY Part 253 253-2.7(e)).\n"
        "To resolve this: please provide the weekly biomass sample logs, the "
        "composite preparation record, and the sampling protocol for the "
        "month(s) with biomass combustion."
    ),
    "GT-DEMO-GAP-007": (
        "What we observed: the Natural Gas worksheet uses an estimated "
        "December volume without a documented Part 253 3.1 substitution "
        "method.\n"
        "What NY Part 253 requires: missing-data substitutions must follow and "
        "document the applicable 3.1 method and rationale "
        "(NY Part 253 253-3.1).\n"
        "To resolve this: please provide either the December billing evidence "
        "to replace the estimate, or the substitution method and rationale "
        "used."
    ),
    "GT-DEMO-GAP-008": (
        "What we observed: only January through March natural gas billing is "
        "provided to support a full-year calculation.\n"
        "What NY Part 253 requires: annual natural gas volumes must be "
        "traceable to account-level billing or equivalent records for the full "
        "reporting year (NY Part 253 253-2.7(l)).\n"
        "To resolve this: please provide the billing statements or meter "
        "records for April through December, or a complete annual supplier "
        "summary with account-level support."
    ),
    "GT-DEMO-GAP-009": (
        "What we observed: the December bill covers Dec 16, 2023 to Jan 15, "
        "2024, but the workbook treats the full quantity as December 1-31, "
        "2023 with no allocation support.\n"
        "What NY Part 253 requires: a cross-year service period must be "
        "prorated or allocated between reporting years with documented support "
        "(NY Part 253 253-1.5(d)).\n"
        "To resolve this: please confirm how the Dec 16 to Jan 15 quantity "
        "should be split between 2023 and 2024, with the allocation basis."
    ),
    "GT-DEMO-GAP-010": (
        "What we observed: the workbook uses a 100-year GWP basis for the "
        "CO2e columns.\n"
        "What requires confirmation: the applicable NY GWP basis remains under "
        "regulatory review in the current engagement.\n"
        "To resolve this: please confirm the intended GWP basis and provide the "
        "governing source used for the workbook calculation."
    ),
}


def _clarification_core(view: dict) -> str:
    ticket_id = str(view.get("id") or "").strip()

    if ticket_id in CLARIFICATION_DRAFTS:
        return CLARIFICATION_DRAFTS[ticket_id]

    ticket = (
        view.get("ticket")
        if isinstance(view.get("ticket"), dict)
        else {}
    )
    citations = _extract_citations(ticket)

    basis = ""
    if citations:
        first = citations[0]
        basis = " ".join(
            value
            for value in [
                str(first.get("authority") or "").strip(),
                str(first.get("citation") or "").strip(),
            ]
            if value
        )

    expected = _fallback_text(view.get("expected"))
    if basis:
        expected = f"{expected} ({basis})"

    return (
        f"What we observed: {_fallback_text(view.get('observed'))}\n"
        f"What the requirement expects: {expected}\n"
        f"To resolve this: {_fallback_text(view.get('action'))}"
    )


def _build_clarification_draft(
    view: dict,
    audit_setup: dict,
) -> str:
    profile = (
        audit_setup.get("company_and_facility_profile")
        if isinstance(
            audit_setup.get("company_and_facility_profile"),
            dict,
        )
        else {}
    )

    facility = _fallback_text(profile.get("facility_name"))
    period = _fallback_text(profile.get("reporting_period"))
    contact_name = str(
        profile.get("client_contact_name") or ""
    ).strip()

    first_name = contact_name.split()[0] if contact_name else ""
    greeting = f"Hi {first_name}," if first_name else "Hi,"

    return (
        f"{greeting}\n\n"
        f"During verification of {facility} for the {period} reporting period, "
        f"we identified an item ({view.get('id')}: {view.get('title')}) that "
        f"needs your clarification before we can close it.\n\n"
        f"{_clarification_core(view)}\n\n"
        "Please reply with the supporting documentation or your explanation "
        "within 10 business days. You can reply to this email or upload "
        "directly to the engagement workspace.\n\n"
        "Thank you,\n"
        "Sustentra verification team"
    )


def _open_clarification_dialog_event(
    view: dict,
    audit_setup: dict,
) -> None:
    ticket_id = str(view.get("id") or "").strip()
    if not ticket_id:
        return

    profile = (
        audit_setup.get("company_and_facility_profile")
        if isinstance(
            audit_setup.get("company_and_facility_profile"),
            dict,
        )
        else {}
    )

    to_key = _clarify_to_key(ticket_id)
    subject_key = _clarify_subject_key(ticket_id)
    message_key = _clarify_message_key(ticket_id)

    if to_key not in st.session_state:
        st.session_state[to_key] = str(
            profile.get("client_contact_email") or ""
        ).strip()

    if subject_key not in st.session_state:
        st.session_state[subject_key] = (
            f"Clarification request - {ticket_id}: "
            f"{view.get('title')}"
        )

    if message_key not in st.session_state:
        st.session_state[message_key] = _build_clarification_draft(
            view,
            audit_setup,
        )

    def _dialog_body() -> None:
        st.caption(
            f"Preview and record a clarification request for {ticket_id}."
        )

        recipient = st.text_input("To", key=to_key)
        subject = st.text_input("Subject", key=subject_key)
        message = st.text_area(
            "Message",
            key=message_key,
            height=320,
        )

        send_col, cancel_col = st.columns(2)

        if send_col.button(
            "Send to client",
            key=f"gap_clarify_send_{ticket_id}",
            type="primary",
            use_container_width=True,
        ):
            if not recipient.strip():
                st.warning("Enter a client contact email before sending.")
                return

            if not subject.strip() or not message.strip():
                st.warning(
                    "Subject and message are required before sending."
                )
                return

            update_mock_auditor_action(
                ticket_id,
                {
                    "action": "Request clarification",
                    "clarification_sent": True,
                    "clarification_to": recipient.strip(),
                    "clarification_subject": subject.strip(),
                    "clarification_message": message.strip(),
                },
            )

            _set_ticket_feedback(
                ACTION_FEEDBACK_KEY,
                ticket_id,
                (
                    f"Clarification recorded for {ticket_id} "
                    f"to {recipient.strip()}."
                ),
            )

            st.rerun()

        if cancel_col.button(
            "Cancel",
            key=f"gap_clarify_cancel_{ticket_id}",
            use_container_width=True,
        ):
            st.rerun()

    decorator = _dialog_decorator()

    if callable(decorator):
        @decorator(f"Request clarification: {ticket_id}")
        def _show() -> None:
            _dialog_body()

        _show()
    else:
        with st.container(border=True):
            _dialog_body()


def _set_ticket_feedback(state_key: str, ticket_id: str, message: str) -> None:
    current = st.session_state.get(state_key)
    if not isinstance(current, dict):
        current = {}
    current[ticket_id] = message
    st.session_state[state_key] = current


def _consume_ticket_feedback(state_key: str, ticket_id: str) -> str:
    current = st.session_state.get(state_key)
    if not isinstance(current, dict):
        return ""
    message = str(current.pop(ticket_id, "") or "").strip()
    st.session_state[state_key] = current
    return message


def _fallback_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else NOT_AVAILABLE_FALLBACK


def _render_summary_chips(summary_counts: dict[str, int]) -> None:
    cols = st.columns(6)

    if cols[0].button(f"Total {summary_counts.get('total', 0)}", key="gap_chip_total", use_container_width=True):
        st.session_state[SEVERITY_FILTER_KEY] = "All"
        st.rerun()
    if cols[1].button(
        f"Critical {summary_counts.get('critical', 0)}",
        key="gap_chip_critical",
        use_container_width=True,
    ):
        st.session_state[VIEW_MODE_KEY] = VIEW_MODE_ALL
        st.session_state[SEVERITY_FILTER_KEY] = "Critical"
        st.rerun()
    if cols[2].button(f"High {summary_counts.get('high', 0)}", key="gap_chip_high", use_container_width=True):
        st.session_state[VIEW_MODE_KEY] = VIEW_MODE_ALL
        st.session_state[SEVERITY_FILTER_KEY] = "High"
        st.rerun()
    if cols[3].button(
        f"Medium {summary_counts.get('medium', 0)}",
        key="gap_chip_medium",
        use_container_width=True,
    ):
        st.session_state[VIEW_MODE_KEY] = VIEW_MODE_ALL
        st.session_state[SEVERITY_FILTER_KEY] = "Medium"
        st.rerun()
    if cols[4].button(f"Low {summary_counts.get('low', 0)}", key="gap_chip_low", use_container_width=True):
        st.session_state[VIEW_MODE_KEY] = VIEW_MODE_ALL
        st.session_state[SEVERITY_FILTER_KEY] = "Low"
        st.rerun()
    if cols[5].button(
        f"Created {summary_counts.get('created', 0)}",
        key="gap_chip_created",
        use_container_width=True,
    ):
        st.session_state[VIEW_MODE_KEY] = VIEW_MODE_CREATED
        st.session_state[SEVERITY_FILTER_KEY] = "All"
        st.rerun()


def _sync_filter_state(options: dict[str, list[str]]) -> None:
    defaults = {
        SEVERITY_FILTER_KEY: "All",
        STATUS_FILTER_KEY: "All",
        CATEGORY_FILTER_KEY: "All",
        ASSERTION_FILTER_KEY: "All",
    }
    key_map = {
        SEVERITY_FILTER_KEY: options.get("severity", ["All"]),
        STATUS_FILTER_KEY: options.get("status", ["All"]),
        CATEGORY_FILTER_KEY: options.get("category", ["All"]),
        ASSERTION_FILTER_KEY: options.get("audit_objective", ["All"]),
    }

    for key, available in key_map.items():
        if key not in st.session_state:
            st.session_state[key] = defaults[key]
        if st.session_state.get(key) not in available:
            st.session_state[key] = defaults[key]


def _extract_primary_evidence_id(ticket: dict) -> str | None:
    linked = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    for entry in linked:
        if not isinstance(entry, dict):
            continue
        evidence_id = str(entry.get("evidence_id") or "").strip()
        if evidence_id:
            return evidence_id
    return None


def _extract_primary_workbook_location(ticket: dict) -> dict | None:
    linked = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )
    for entry in linked:
        if isinstance(entry, dict):
            return entry
    return None


def _extract_citations(ticket: dict) -> list[dict]:
    basis = ticket.get("basis") if isinstance(ticket.get("basis"), dict) else {}
    citations = basis.get("regulatory_citations") if isinstance(basis.get("regulatory_citations"), list) else []
    return [item for item in citations if isinstance(item, dict)]


def _render_master_list(gap_views: list[dict], selected_id: str | None) -> None:
    st.markdown("#### Findings")
    if not gap_views:
        st.info("No findings match the current view.")
        return

    for view in gap_views:
        ticket_id = str(view.get("id") or "")
        title = str(view.get("title") or "Untitled finding")
        row_label = title
        is_selected = ticket_id == (selected_id or "")
        button_type = "primary" if is_selected else "secondary"

        if st.button(
            row_label,
            key=f"gap_master_select_{ticket_id}",
            use_container_width=True,
            type=button_type,
        ):
            set_selected_gap_ticket_id(ticket_id)
            st.rerun()

        tags = [
            str(view.get("effective_severity") or ""),
            str(view.get("status") or ""),
            str(view.get("category") or ""),
        ]
        if bool(view.get("created")):
            tags.append("Created")
        caption_parts = [ticket_id, *tags]
        st.caption(" · ".join(item for item in caption_parts if item))


def _render_regulation_detail_blocks(citations: list[dict], regulation_library: dict[str, dict]) -> None:
    if not citations:
        st.caption("No regulatory citation is available for this finding.")
        return

    for index, citation in enumerate(citations, start=1):
        display = resolve_regulation_display(
            citation.get("authority"),
            citation.get("citation"),
            applicability_explanation=citation.get("applicability_explanation"),
            library=regulation_library,
        )

        authority = _fallback_text(display.get("authority"))
        citation_code = _fallback_text(display.get("citation"))
        title = _fallback_text(display.get("title"))
        body = _fallback_text(display.get("text") or display.get("pending_text"))
        applicability = _fallback_text(display.get("applicability_explanation"))

        with st.container(border=True):
            st.markdown(f"**Citation {index}: {authority} {citation_code}**")
            st.write(f"Title: {title}")
            st.write(body)
            st.caption(f"Applicability: {applicability}")
            source_url = str(display.get("source_url") or "").strip()
            if source_url:
                st.caption(f"Source: {source_url}")


def _open_regulation_dialog_event(
    ticket_id: str,
    citations: list[dict],
    regulation_library: dict[str, dict],
) -> None:
    decorator = _dialog_decorator()
    if callable(decorator):
        @decorator(f"Show regulation: {ticket_id}")
        def _show_regulation_details() -> None:
            st.caption(f"Regulation details for {ticket_id}")
            _render_regulation_detail_blocks(citations, regulation_library)

        _show_regulation_details()
    else:
        with st.container(border=True):
            st.caption(f"Regulation details for {ticket_id}")
            _render_regulation_detail_blocks(citations, regulation_library)


def _render_selected_finding_summary_cards(selected_view: dict) -> None:
    cards = [
        ("Status", str(selected_view.get("status") or "Unknown")),
        ("Category", str(selected_view.get("category") or "General")),
        ("System severity", str(selected_view.get("system_severity") or "Informational")),
        ("Auditor severity", str(selected_view.get("auditor_severity") or "Not set")),
    ]
    cols = st.columns(4, gap="small")
    for col, (label, value) in zip(cols, cards):
        with col:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"**{value}**")


def _render_detail(selected_view: dict, regulation_library: dict[str, dict], audit_setup: dict) -> None:
    ticket_id = str(selected_view.get("id") or "")
    ticket = selected_view.get("ticket") if isinstance(selected_view.get("ticket"), dict) else {}
    linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    linked_workbook = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )
    citations = _extract_citations(ticket)
    rule_results = ticket.get("upstream_rule_results") if isinstance(ticket.get("upstream_rule_results"), list) else []

    st.markdown(f"### {selected_view.get('title')}")
    _render_selected_finding_summary_cards(selected_view)

    utility_row_1 = st.columns(3, gap="small")
    utility_row_2 = st.columns(2, gap="small")

    if utility_row_1[0].button(
        "Open evidence",
        key=f"gap_action_open_evidence_{ticket_id}",
        use_container_width=True,
    ):
        open_original_evidence(_extract_primary_evidence_id(ticket))

    if utility_row_1[1].button(
        "Open workbook location",
        key=f"gap_action_open_workbook_{ticket_id}",
        use_container_width=True,
    ):
        open_workbook_location(_extract_primary_workbook_location(ticket))

    if utility_row_1[2].button(
        "Show regulation",
        key=f"gap_action_show_regulation_{ticket_id}",
        use_container_width=True,
    ):
        _open_regulation_dialog_event(ticket_id, citations, regulation_library)

    if utility_row_2[0].button(
        "Ask Sustentra AI Assistant",
        key=f"gap_action_ask_assistant_{ticket_id}",
        use_container_width=True,
    ):
        question = f"What regulation text applies to {ticket_id} and why?"
        st.session_state["selected_chat_question"] = question
        ask_regulatory_assistant(ticket_id, suggested_prompt=question)

    if utility_row_2[1].button(
        "Draft auditor note",
        key=f"gap_action_draft_note_{ticket_id}",
        use_container_width=True,
    ):
        action_state = (
            (st.session_state.get("mock_auditor_actions") or {}).get(ticket_id, {}).get("action")
            if isinstance(st.session_state.get("mock_auditor_actions"), dict)
            else None
        )
        action_text = str(action_state or "Not set")
        draft = (
            f"Current status: {selected_view.get('status')}. "
            f"Auditor action: {action_text}. "
            f"Finding: {ticket_id} - {selected_view.get('title')}"
        )
        update_mock_auditor_action(ticket_id, {"note": draft})
        st.session_state[_note_widget_key(ticket_id)] = draft
        st.success(f"Drafted note for {ticket_id}.")

    decision_cols = st.columns(3)
    if decision_cols[0].button("Confirm", key=f"gap_decision_confirm_{ticket_id}", use_container_width=True):
        update_mock_auditor_action(ticket_id, {"action": "Confirm"})
        _set_ticket_feedback(ACTION_FEEDBACK_KEY, ticket_id, f"Saved Confirm for {ticket_id}.")
    if decision_cols[1].button("Dismiss", key=f"gap_decision_dismiss_{ticket_id}", use_container_width=True):
        update_mock_auditor_action(ticket_id, {"action": "Dismiss"})
        _set_ticket_feedback(ACTION_FEEDBACK_KEY, ticket_id, f"Saved Dismiss for {ticket_id}.")
    if decision_cols[2].button(
        "Request clarification",
        key=f"gap_decision_clarify_{ticket_id}",
        use_container_width=True,
    ):
        _open_clarification_dialog_event(
            selected_view,
            audit_setup,
        )

    action_feedback = _consume_ticket_feedback(ACTION_FEEDBACK_KEY, ticket_id)
    if action_feedback:
        st.success(action_feedback)

    current_action = ""
    actions_overlay = st.session_state.get("mock_auditor_actions")
    if isinstance(actions_overlay, dict):
        current_action = str((actions_overlay.get(ticket_id) or {}).get("action") or "").strip()
    st.caption(f"Current auditor action: {_fallback_text(current_action)}")

    note_key = _note_widget_key(ticket_id)
    existing_note = ""
    if isinstance(actions_overlay, dict):
        existing_note = str((actions_overlay.get(ticket_id) or {}).get("note") or "")
    if note_key not in st.session_state:
        st.session_state[note_key] = existing_note

    note_value = st.text_area("Add auditor note", key=note_key, height=120)
    if st.button("Save note", key=f"gap_save_note_{ticket_id}"):
        update_mock_auditor_action(ticket_id, {"note": note_value.strip()})
        _set_ticket_feedback(NOTE_FEEDBACK_KEY, ticket_id, f"Saved note for {ticket_id}.")

    note_feedback = _consume_ticket_feedback(NOTE_FEEDBACK_KEY, ticket_id)
    if note_feedback:
        st.success(note_feedback)

    tab_finding, tab_evidence, tab_workbook, tab_regulatory, tab_reasoning = st.tabs(
        ["Finding", "Evidence Trace", "Workbook Trace", "Regulatory Basis", "AI Reasoning"]
    )

    with tab_finding:
        st.write(f"What we found: {_fallback_text(selected_view.get('observed'))}")
        st.write(f"What should be true: {_fallback_text(selected_view.get('expected'))}")
        st.write(f"Why this matters: {_fallback_text(selected_view.get('why'))}")
        st.write(f"Recommended action: {_fallback_text(selected_view.get('action'))}")

    with tab_evidence:
        render_evidence_trace(linked_evidence)

    with tab_workbook:
        if not linked_workbook:
            st.caption("No workbook location is linked to this finding.")
        for location in linked_workbook:
            if not isinstance(location, dict):
                continue
            st.write(summarize_workbook_trace(location))

    with tab_regulatory:
        render_regulatory_basis(citations)
        _render_regulation_detail_blocks(citations, regulation_library)

    with tab_reasoning:
        render_ai_reasoning(rule_results)
        with st.expander("Rule reasoning details", expanded=False):
            render_reasoning_trail(rule_results)

st.set_page_config(
    page_title="Gap Analysis",
    layout="wide",
)

init_session_state()
_inject_page6_layout_style()
st.title("Gap Analysis")
st.caption("Auditor-facing findings with evidence trace, workbook trace, and regulatory basis.")
render_prepared_demo_disclosure()
audit_setup = get_audit_setup()
render_audit_setup_context(audit_setup)

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

gap_tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
if not gap_tickets:
    st.info("No gap tickets are available in the prepared dataset.")
    st.stop()

created_ids = set(get_created_gap_ticket_ids())
overrides = get_gap_ticket_overrides()
all_views = sort_gap_views(build_gap_views(gap_tickets, created_ids, overrides))
if not all_views:
    st.info("No auditor-facing findings are available in the prepared dataset.")
    st.stop()

summary_counts = derive_summary_counts(all_views)
default_view_mode = VIEW_MODE_CREATED if summary_counts.get("created", 0) > 0 else VIEW_MODE_ALL
if VIEW_MODE_KEY not in st.session_state:
    st.session_state[VIEW_MODE_KEY] = default_view_mode
if st.session_state.get(VIEW_MODE_KEY) not in {VIEW_MODE_CREATED, VIEW_MODE_ALL}:
    st.session_state[VIEW_MODE_KEY] = default_view_mode

st.markdown("### Finding summary")
_render_summary_chips(summary_counts)

if hasattr(st, "segmented_control"):
    st.segmented_control(
        "View",
        options=[VIEW_MODE_CREATED, VIEW_MODE_ALL],
        key=VIEW_MODE_KEY,
    )
else:
    st.radio(
        "View",
        options=[VIEW_MODE_CREATED, VIEW_MODE_ALL],
        key=VIEW_MODE_KEY,
        horizontal=True,
    )

filter_options = gap_filter_options(all_views)
_sync_filter_state(filter_options)

fcol1, fcol2, fcol3, fcol4 = st.columns(4)
fcol1.selectbox("Severity", options=filter_options["severity"], key=SEVERITY_FILTER_KEY)
fcol2.selectbox("Status", options=filter_options["status"], key=STATUS_FILTER_KEY)
fcol3.selectbox("Category", options=filter_options["category"], key=CATEGORY_FILTER_KEY)
fcol4.selectbox("Audit objective", options=filter_options["audit_objective"], key=ASSERTION_FILTER_KEY)

filtered_views = sort_gap_views(
    apply_gap_filters(
        all_views,
        view_mode=str(st.session_state.get(VIEW_MODE_KEY) or VIEW_MODE_ALL),
        severity_filter=str(st.session_state.get(SEVERITY_FILTER_KEY) or "All"),
        status_filter=str(st.session_state.get(STATUS_FILTER_KEY) or "All"),
        category_filter=str(st.session_state.get(CATEGORY_FILTER_KEY) or "All"),
        audit_objective_filter=str(st.session_state.get(ASSERTION_FILTER_KEY) or "All"),
    )
)

if not filtered_views:
    st.info("No findings match the current filter set.")
    st.stop()

selected_before = get_selected_gap_ticket_id()
selected_id = ensure_selected_gap_id(filtered_views, selected_before)
if selected_id:
    set_selected_gap_ticket_id(selected_id)

selected_view = find_gap_view(filtered_views, selected_id)
regulation_library = load_regulation_library()

master_col, detail_col = st.columns(
    [1.7, 3.3],
    gap="medium",
)
with master_col:
    _render_master_list(filtered_views, selected_id)

with detail_col:
    if selected_before and selected_before == selected_id:
        st.caption("Opened from upstream workflow context")

    if not isinstance(selected_view, dict):
        st.info("Select a finding from the list to review its detail.")
    else:
        _render_detail(selected_view, regulation_library, audit_setup)
