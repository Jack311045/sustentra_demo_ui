from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st

from src.api.adapters import adapt_analysis_response, resolve_audit_setup
from src.api.mock_client import MockApiClient
from src.ui.components import render_audit_setup_context
from src.ui.state import (
    get_audit_setup,
    init_session_state,
    is_audit_setup_user_saved,
    set_analysis_response,
    set_audit_setup,
    set_prepared_demo_disclosure_acknowledged,
    set_selected_demo_scenario,
    set_uploaded_evidence_metadata,
    set_uploaded_workbook_metadata,
)
from src.ui.workflow import render_prepared_demo_disclosure


PREPARED_SCENARIO_ID = "gap_path"
PREPARED_SCENARIO_LABEL = "Data with gaps"


init_session_state()
st.title("Evidence Intake")
st.caption("Upload engagement files and run the prepared workflow dataset for this demo.")
render_prepared_demo_disclosure()
render_audit_setup_context(get_audit_setup())

st.info(
    "The uploaded files establish the demo engagement workflow. The current build uses prepared "
    "extraction, validation, calculation, and gap results until the document-analysis API is connected."
)
st.caption("Current session Audit Setup values are preserved when running the prepared workflow.")

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

set_selected_demo_scenario(PREPARED_SCENARIO_ID)

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
    client = MockApiClient()
    raw_response = client.analyze(scenario_id=PREPARED_SCENARIO_ID)
    adapted = adapt_analysis_response(raw_response)

    uploaded_files_payload = {
        "workbook": workbook_metadata,
        "evidence_files": uploaded_evidence,
        "scenario_id": PREPARED_SCENARIO_ID,
        "scenario_label": PREPARED_SCENARIO_LABEL,
        "note": (
            "Prepared extraction, validation, calculation, and gap results were used for this demo run."
        ),
    }

    effective_setup = resolve_audit_setup(
        session_setup=get_audit_setup(),
        response_setup=adapted.get("audit_setup"),
        prepared_setup=client.load_audit_setup(),
        session_is_user_saved=is_audit_setup_user_saved(),
    )

    set_audit_setup(
        effective_setup,
        user_saved=is_audit_setup_user_saved(),
        increment_revision=True,
    )

    adapted["uploaded_demo_files"] = uploaded_files_payload
    adapted["audit_setup"] = deepcopy(effective_setup)
    adapted["selected_demo_scenario"] = PREPARED_SCENARIO_ID

    set_analysis_response(adapted)
    st.session_state["demo_analysis_loaded_from_uploaded_flow"] = True
    set_prepared_demo_disclosure_acknowledged(True)
