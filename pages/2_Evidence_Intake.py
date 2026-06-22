from __future__ import annotations

from typing import Any

import streamlit as st

from src.api.adapters import adapt_analysis_response
from src.api.mock_client import MockApiClient
from src.ui.state import (
    get_audit_setup,
    get_selected_demo_scenario,
    init_session_state,
    set_analysis_response,
    set_prepared_demo_disclosure_acknowledged,
    set_selected_demo_scenario,
    set_uploaded_evidence_metadata,
    set_uploaded_workbook_metadata,
)
from src.ui.workflow import render_prepared_demo_disclosure, render_workflow_progress


SCENARIO_OPTIONS = {
    "gap_path": "Data with gaps",
    "clean_path": "Clean data path",
}


init_session_state()
st.title("Evidence Intake")
st.caption("Upload engagement files and run the prepared workflow dataset for this demo.")
render_workflow_progress(current_step=2)
render_prepared_demo_disclosure()

st.info(
    "The uploaded files establish the demo engagement workflow. The current build uses prepared "
    "extraction, validation, calculation, and gap results until the document-analysis API is connected."
)

workbook_file = st.file_uploader(
    "Upload workbook",
    type=["xlsx", "xlsm", "csv"],
    accept_multiple_files=False,
)
evidence_files = st.file_uploader(
    "Upload evidence files",
    type=["pdf", "docx", "xlsx", "csv", "json", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

selected_scenario = st.selectbox(
    "Prepared scenario",
    options=list(SCENARIO_OPTIONS.keys()),
    format_func=lambda option: SCENARIO_OPTIONS.get(option, option),
    index=list(SCENARIO_OPTIONS.keys()).index(get_selected_demo_scenario())
    if get_selected_demo_scenario() in SCENARIO_OPTIONS
    else 0,
)
set_selected_demo_scenario(selected_scenario)

workbook_metadata: dict[str, Any] = {}
if workbook_file is not None:
    workbook_metadata = {
        "name": workbook_file.name,
        "mime_type": workbook_file.type,
        "size_bytes": workbook_file.size,
    }

uploaded_evidence = []
for file in evidence_files or []:
    uploaded_evidence.append(
        {
            "name": file.name,
            "mime_type": file.type,
            "size_bytes": file.size,
        }
    )

set_uploaded_workbook_metadata(workbook_metadata)
set_uploaded_evidence_metadata(uploaded_evidence)

st.subheader("Uploaded file summary")
summary_col1, summary_col2 = st.columns(2)
with summary_col1:
    if workbook_metadata:
        st.write(f"Workbook: {workbook_metadata.get('name')}")
        st.caption(f"Type: {workbook_metadata.get('mime_type') or 'Unknown'}")
        st.caption(f"Size: {workbook_metadata.get('size_bytes') or 0} bytes")
    else:
        st.caption("No workbook uploaded yet.")
with summary_col2:
    if uploaded_evidence:
        st.write(f"Evidence files: {len(uploaded_evidence)}")
        for item in uploaded_evidence:
            st.caption(
                f"- {item.get('name')} | {item.get('mime_type') or 'Unknown'} | {item.get('size_bytes') or 0} bytes"
            )
    else:
        st.caption("No evidence files uploaded yet.")

if st.button("Run prepared demo workflow", type="primary"):
    raw_response = MockApiClient().analyze(scenario_id=selected_scenario)
    adapted = adapt_analysis_response(raw_response)

    uploaded_files_payload = {
        "workbook": workbook_metadata,
        "evidence_files": uploaded_evidence,
        "scenario_id": selected_scenario,
        "scenario_label": SCENARIO_OPTIONS.get(selected_scenario, selected_scenario),
        "note": (
            "Prepared extraction, validation, calculation, and gap results were used for this demo run."
        ),
    }

    adapted["uploaded_demo_files"] = uploaded_files_payload
    adapted["audit_setup"] = get_audit_setup()
    adapted["selected_demo_scenario"] = selected_scenario
    adapted.setdefault("warnings", [])
    if selected_scenario == "clean_path" and adapted.get("scenario_status") == "not_available":
        adapted["warnings"].append(
            "Clean data path is not available in the current prepared dataset."
        )

    set_analysis_response(adapted)
    st.session_state["demo_analysis_loaded_from_uploaded_flow"] = True
    set_prepared_demo_disclosure_acknowledged(True)
    st.success("Prepared demo workflow loaded into session state.")

analysis_response = st.session_state.get("analysis_response")
if isinstance(analysis_response, dict):
    st.subheader("Loaded analysis snapshot")
    col1, col2, col3 = st.columns(3)
    col1.metric("Run ID", str(analysis_response.get("run_id") or "N/A"))
    col2.metric("Status", str(analysis_response.get("status") or "unknown"))
    col3.metric("Scenario", SCENARIO_OPTIONS.get(selected_scenario, selected_scenario))

    warnings = analysis_response.get("warnings") if isinstance(analysis_response.get("warnings"), list) else []
    if warnings:
        with st.expander("Warnings", expanded=False):
            for warning in warnings:
                st.write(f"- {warning}")
