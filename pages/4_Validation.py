from __future__ import annotations

import streamlit as st

from src.ui.components import render_audit_setup_context
from src.ui.state import (
    get_audit_setup,
    get_analysis_response,
    init_session_state,
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


def _status_badge(status: str) -> str:
    normalized = normalize_validation_status(status)
    color = _STATUS_COLOR.get(normalized, _STATUS_COLOR["unknown"])
    label = validation_status_label(status)
    return f"<span style='color:{color};font-weight:600;'>● {label}</span>"


def _render_check_card(validation_id: str, check: dict, audit_setup: dict) -> None:
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


def _render_validation_record(record: dict, audit_setup: dict) -> None:
    record_label = str(record.get("record_label") or "Validation record")
    validation_id = str(record.get("validation_id") or "")
    evidence_id = str(record.get("evidence_id") or "")
    overall_status = str(record.get("overall_status") or "")
    expanded = normalize_validation_status(overall_status) in {"fail", "flagged"}

    with st.expander(record_label, expanded=expanded):
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
                _render_check_card(validation_id, check, audit_setup)

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

for record in sort_validation_records(validation_results):
    _render_validation_record(record, audit_setup)
