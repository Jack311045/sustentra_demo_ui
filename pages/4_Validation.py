from __future__ import annotations

import streamlit as st

from src.ui.components import render_audit_setup_context
from src.ui.formatting import severity_label
from src.ui.state import (
    create_gap_ticket,
    get_audit_setup,
    get_analysis_response,
    get_created_gap_ticket_ids,
    get_gap_ticket_override,
    get_gap_ticket_overrides,
    get_open_create_modal_for,
    get_selected_validation_id,
    init_session_state,
    set_open_create_modal_for,
    set_selected_gap_ticket_id,
)
from src.ui.validation import (
    derive_monthly_evidence_coverage,
    format_monthly_coverage_banner,
    normalize_validation_status,
    resolve_check_display,
    sort_validation_checks,
    sort_validation_records,
    trace_note_for_check,
    validation_status_label,
)
from src.ui.workflow import render_prepared_demo_disclosure


_STATUS_COLOR = {
    "pass": "#117B34",
    "flagged": "#B54708",
    "fail": "#B42318",
    "unknown": "#475467",
}

_SEVERITY_OPTIONS = ["Critical", "High", "Medium", "Low", "Informational"]


def _status_badge(status: str) -> str:
    normalized = normalize_validation_status(status)
    color = _STATUS_COLOR.get(normalized, _STATUS_COLOR["unknown"])
    label = validation_status_label(status)
    return f"<span style='color:{color};font-weight:600;'>● {label}</span>"


def _switch_to_gap_analysis() -> None:
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        try:
            switch_page("pages/6_Gap_Analysis.py")
            return
        except Exception:
            pass
    st.info("Open Gap Analysis from the sidebar to review the selected finding.")


def _gap_ticket_map(analysis_response: dict) -> dict[str, dict]:
    tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
    mapping: dict[str, dict] = {}
    for ticket in tickets:
        ticket_id = str(ticket.get("gap_ticket_id") or "").strip()
        if not ticket_id:
            continue
        mapping[ticket_id] = ticket
    return mapping


def _default_register_payload(ticket_id: str, ticket: dict) -> dict:
    issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
    remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}
    severity = ticket.get("severity") if isinstance(ticket.get("severity"), dict) else {}
    override = get_gap_ticket_override(ticket_id)

    default_severity = (
        str(
            override.get("severity")
            or severity.get("auditor_assigned")
            or severity.get("system_suggested")
            or "High"
        )
        .strip()
        .lower()
    )
    severity_label_value = severity_label(default_severity)
    if severity_label_value not in _SEVERITY_OPTIONS:
        severity_label_value = "High"

    return {
        "auditor_title": str(
            override.get("auditor_title")
            or ticket.get("auditor_title")
            or ticket.get("title")
            or ""
        ).strip(),
        "severity": severity_label_value,
        "observed_condition": str(
            override.get("observed_condition") or issue.get("observed_condition") or ""
        ).strip(),
        "why_triggered": str(
            override.get("why_triggered") or issue.get("why_triggered") or ""
        ).strip(),
        "recommended_action": str(
            override.get("recommended_action") or remediation.get("recommended_action") or ""
        ).strip(),
    }


def _render_registration_form(ticket_id: str, ticket: dict, *, form_prefix: str) -> None:
    defaults = _default_register_payload(ticket_id, ticket)
    severity_index = _SEVERITY_OPTIONS.index(defaults["severity"]) if defaults["severity"] in _SEVERITY_OPTIONS else 1

    with st.form(f"{form_prefix}_{ticket_id}"):
        st.caption("Create an auditor finding from the linked validation exception.")
        title = st.text_input("Finding title", value=defaults["auditor_title"])
        severity_choice = st.selectbox("Severity assessment", options=_SEVERITY_OPTIONS, index=severity_index)
        observed = st.text_area("Observed condition", value=defaults["observed_condition"], height=120)
        why = st.text_area("Why it matters", value=defaults["why_triggered"], height=120)
        action = st.text_area("Recommended action", value=defaults["recommended_action"], height=120)

        submit_col, cancel_col = st.columns(2)
        submitted = submit_col.form_submit_button("Confirm registration", type="primary")
        cancelled = cancel_col.form_submit_button("Cancel")

    if cancelled:
        set_open_create_modal_for(None)
        st.rerun()

    if submitted:
        create_gap_ticket(
            ticket_id,
            overrides={
                "auditor_title": title.strip(),
                "severity": severity_choice.strip().lower(),
                "observed_condition": observed.strip(),
                "why_triggered": why.strip(),
                "recommended_action": action.strip(),
            },
        )
        set_open_create_modal_for(None)
        st.success(f"Created finding {ticket_id}.")
        st.rerun()


def _render_pending_registration(gap_ticket_map: dict[str, dict], created_ids: set[str]) -> None:
    ticket_id = get_open_create_modal_for()
    if not ticket_id:
        return

    ticket = gap_ticket_map.get(ticket_id)
    if not isinstance(ticket, dict):
        set_open_create_modal_for(None)
        return

    if ticket_id in created_ids:
        set_open_create_modal_for(None)
        return

    dialog_decorator = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if callable(dialog_decorator):
        @dialog_decorator(f"Register finding {ticket_id}")
        def _registration_dialog() -> None:
            _render_registration_form(ticket_id, ticket, form_prefix="validation_dialog")

        _registration_dialog()
    else:
        with st.container(border=True):
            st.markdown(f"### Register finding {ticket_id}")
            _render_registration_form(ticket_id, ticket, form_prefix="validation_inline")


def _render_linked_finding_controls(
    validation_id: str,
    check_id: str,
    linked_gap_ticket_id: str,
    *,
    created_ids: set[str],
) -> None:
    action_col1, action_col2 = st.columns(2)

    if linked_gap_ticket_id in created_ids:
        action_col1.success("Created")
        if action_col2.button(
            "Open in Gap Analysis",
            key=f"validation_open_gap_{validation_id}_{check_id}_{linked_gap_ticket_id}",
            use_container_width=True,
        ):
            set_selected_gap_ticket_id(linked_gap_ticket_id)
            _switch_to_gap_analysis()
        return

    if action_col1.button(
        "Register finding",
        key=f"validation_register_gap_{validation_id}_{check_id}_{linked_gap_ticket_id}",
        use_container_width=True,
    ):
        set_open_create_modal_for(linked_gap_ticket_id)
        st.rerun()


def _render_check_card(
    validation_id: str,
    check: dict,
    audit_setup: dict,
    *,
    created_ids: set[str],
    gap_ticket_map: dict[str, dict],
) -> None:
    check_id = str(check.get("check_id") or "")
    display = resolve_check_display(validation_id, check)

    with st.container(border=True):
        st.markdown(f"**Q: {display['question']}**")
        answer = f"A: {display['answer']}"
        tone = display.get("tone")
        if tone == "positive":
            st.success(answer)
        elif tone == "negative":
            st.error(answer)
        elif tone == "warning":
            st.warning(answer)
        else:
            st.info(answer)

        linked_gap_ticket_id = str(check.get("linked_gap_ticket_id") or "").strip()
        check_status = normalize_validation_status(check.get("status"))
        if (
            linked_gap_ticket_id
            and linked_gap_ticket_id in gap_ticket_map
            and check_status in {"fail", "flagged"}
        ):
            _render_linked_finding_controls(
                validation_id,
                check_id,
                linked_gap_ticket_id,
                created_ids=created_ids,
            )

        trace_note = trace_note_for_check(check_id, audit_setup)
        if trace_note:
            st.caption(trace_note)

        with st.expander("Check details", expanded=False):
            st.caption(f"Check ID: {check_id or 'Unavailable'}")
            st.caption(f"Status: {validation_status_label(check.get('status'))}")
            if check.get("observed") is not None:
                st.write(f"Observed: {check.get('observed')}")
            if check.get("expected") is not None:
                st.write(f"Expected: {check.get('expected')}")
            if check.get("explanation"):
                st.write(f"Explanation: {check.get('explanation')}")


def _render_validation_record(
    record: dict,
    audit_setup: dict,
    selected_validation_id: str | None,
    *,
    created_ids: set[str],
    gap_ticket_map: dict[str, dict],
) -> None:
    record_label = str(record.get("record_label") or "Validation record")
    validation_id = str(record.get("validation_id") or "")
    evidence_id = str(record.get("evidence_id") or "")
    overall_status = str(record.get("overall_status") or "")
    expanded = normalize_validation_status(overall_status) in {"fail", "flagged"} or (
        selected_validation_id is not None and validation_id == selected_validation_id
    )

    with st.expander(record_label, expanded=expanded):
        if selected_validation_id is not None and validation_id == selected_validation_id:
            st.caption("Opened from Calculation & Reconciliation")
        st.markdown(_status_badge(overall_status), unsafe_allow_html=True)
        caption_bits = []
        if validation_id:
            caption_bits.append(f"Validation ID: {validation_id}")
        if evidence_id:
            caption_bits.append(f"Evidence ID: {evidence_id}")
        if caption_bits:
            st.caption(" | ".join(caption_bits))

        checks = sort_validation_checks(record.get("checks") if isinstance(record.get("checks"), list) else [])
        if not checks:
            st.info("No checks are available for this validation record.")
        else:
            for check in checks:
                _render_check_card(
                    validation_id,
                    check,
                    audit_setup,
                    created_ids=created_ids,
                    gap_ticket_map=gap_ticket_map,
                )

        with st.expander("Advanced validation JSON", expanded=False):
            st.json(record)


init_session_state()
st.title("Validation")
st.caption("Validate the approved evidence baseline against engagement and methodology rules.")
st.caption("Validating the approved evidence baseline")
render_prepared_demo_disclosure()

audit_setup = get_audit_setup()
render_audit_setup_context(audit_setup)

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

validation_results = [
    item for item in (analysis_response.get("validation_results") or []) if isinstance(item, dict)
]
if not validation_results:
    st.info("No validation results are available in this prepared dataset.")
    st.stop()

status_counts = {"pass": 0, "flagged": 0, "fail": 0}
for record in validation_results:
    overall = normalize_validation_status(record.get("overall_status"))
    if overall in status_counts:
        status_counts[overall] += 1

count_col1, count_col2, count_col3, count_col4 = st.columns(4)
count_col1.metric("Validation records", len(validation_results))
count_col2.metric("Pass", status_counts["pass"])
count_col3.metric("Flagged", status_counts["flagged"])
count_col4.metric("Fail", status_counts["fail"])

coverage = derive_monthly_evidence_coverage(analysis_response, audit_setup)
st.info(format_monthly_coverage_banner(coverage))

selected_validation_id = get_selected_validation_id()
gap_ticket_map = _gap_ticket_map(analysis_response)
created_ids = set(get_created_gap_ticket_ids())

for record in sort_validation_records(validation_results):
    _render_validation_record(
        record,
        audit_setup,
        selected_validation_id,
        created_ids=created_ids,
        gap_ticket_map=gap_ticket_map,
    )

_render_pending_registration(gap_ticket_map, created_ids)
