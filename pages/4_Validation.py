from __future__ import annotations

import streamlit as st

from src.ui.state import (
    get_analysis_response,
    get_selected_validation_id,
    init_session_state,
    set_selected_validation_id,
)
from src.ui.tables import render_validation_table
from src.ui.traceability import render_reasoning_trail
from src.ui.workflow import render_prepared_demo_disclosure, render_workflow_progress


init_session_state()
st.title("Validation")
st.caption("Deterministic rule checks and record-level reasoning trail for auditor review.")
render_workflow_progress(current_step=4)
render_prepared_demo_disclosure()

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
    overall = str(record.get("overall_status") or "").strip().lower()
    if overall in status_counts:
        status_counts[overall] += 1

count_col1, count_col2, count_col3, count_col4 = st.columns(4)
count_col1.metric("Validation records", len(validation_results))
count_col2.metric("Pass", status_counts["pass"])
count_col3.metric("Flagged", status_counts["flagged"])
count_col4.metric("Fail", status_counts["fail"])

render_validation_table(validation_results)

validation_ids = [str(item.get("validation_id")) for item in validation_results if item.get("validation_id")]
if not validation_ids:
    st.info("Validation IDs are missing from the prepared dataset.")
    st.stop()

selected_validation_id = get_selected_validation_id()
if selected_validation_id not in validation_ids:
    selected_validation_id = validation_ids[0]

selected_validation_id = st.selectbox(
    "Select validation record",
    options=validation_ids,
    index=validation_ids.index(selected_validation_id),
)
set_selected_validation_id(selected_validation_id)

selected_record = next(
    (
        item
        for item in validation_results
        if str(item.get("validation_id")) == selected_validation_id
    ),
    None,
)
if not selected_record:
    st.info("Selected validation record could not be found.")
    st.stop()

st.subheader(str(selected_record.get("record_label") or selected_validation_id))
st.caption(f"Overall result: {selected_record.get('overall_status') or 'Needs confirmation'}")
if selected_record.get("next_check"):
    st.caption(f"Next check: {selected_record.get('next_check')}")

render_reasoning_trail(selected_record.get("checks") if isinstance(selected_record.get("checks"), list) else [])

with st.expander("Advanced validation JSON", expanded=False):
    st.json(selected_record)
