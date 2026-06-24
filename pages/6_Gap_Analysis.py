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
        row_label = f"{ticket_id} - {title}" if ticket_id else title
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
        st.caption(" | ".join([tag for tag in tags if tag]))


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
    cols = st.columns(4)
    for col, (label, value) in zip(cols, cards):
        with col:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"**{value}**")


def _render_detail(selected_view: dict, regulation_library: dict[str, dict]) -> None:
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

    action_cols = st.columns(5)
    if action_cols[0].button(
        "Open evidence",
        key=f"gap_action_open_evidence_{ticket_id}",
        use_container_width=True,
    ):
        open_original_evidence(_extract_primary_evidence_id(ticket))

    if action_cols[1].button(
        "Open workbook location",
        key=f"gap_action_open_workbook_{ticket_id}",
        use_container_width=True,
    ):
        open_workbook_location(_extract_primary_workbook_location(ticket))

    if action_cols[2].button(
        "Show regulation",
        key=f"gap_action_show_regulation_{ticket_id}",
        use_container_width=True,
    ):
        _open_regulation_dialog_event(ticket_id, citations, regulation_library)

    if action_cols[3].button(
        "Ask Sustentra AI Assistant",
        key=f"gap_action_ask_assistant_{ticket_id}",
        use_container_width=True,
    ):
        question = f"What regulation text applies to {ticket_id} and why?"
        st.session_state["selected_chat_question"] = question
        ask_regulatory_assistant(ticket_id, suggested_prompt=question)

    if action_cols[4].button(
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
        update_mock_auditor_action(ticket_id, {"action": "Request clarification"})
        _set_ticket_feedback(
            ACTION_FEEDBACK_KEY,
            ticket_id,
            f"Saved Request clarification for {ticket_id}.",
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


init_session_state()
st.title("Gap Analysis")
st.caption("Auditor-facing findings with evidence trace, workbook trace, and regulatory basis.")
render_prepared_demo_disclosure()
render_audit_setup_context(get_audit_setup())

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

master_col, detail_col = st.columns([1.25, 2.75], gap="large")
with master_col:
    _render_master_list(filtered_views, selected_id)

with detail_col:
    if selected_before and selected_before == selected_id:
        st.caption("Opened from upstream workflow context")

    if not isinstance(selected_view, dict):
        st.info("Select a finding from the list to review its detail.")
    else:
        _render_detail(selected_view, regulation_library)
