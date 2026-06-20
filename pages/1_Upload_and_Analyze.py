from __future__ import annotations

import streamlit as st

from src.api.adapters import adapt_analysis_response
from src.api.mock_client import MockApiClient
from src.ui.components import render_summary_cards
from src.ui.state import (
	get_analysis_response,
	get_uploaded_file_metadata,
	init_session_state,
	set_analysis_response,
	set_uploaded_file_metadata,
)


init_session_state()

st.title("Upload and Analyze")
st.caption(
	"Upload the company workbook and supporting evidence package. In this demo build, "
	"the uploaded files are captured for workflow simulation and the analysis results "
	"are loaded from a prepared backend response. Real document extraction/gap generation "
	"will be connected when the ingestion API is available."
)

st.session_state["use_mock_api"] = True

st.subheader("Demo inputs")
workbook_file = st.file_uploader(
	"Workbook file",
	type=["xlsx", "xlsm", "csv"],
	accept_multiple_files=False,
)
evidence_files = st.file_uploader(
	"Evidence pack / evidence files",
	type=["pdf", "docx", "xlsx", "csv", "json"],
	accept_multiple_files=True,
)
st.info(
	"Files are captured for workflow simulation only. This page does not save files to disk "
	"or send files to an ingestion backend."
)

workbook_name = workbook_file.name if workbook_file is not None else None
workbook_size = workbook_file.size if workbook_file is not None else None

evidence_file_metadata = [
	{"name": file.name, "size_bytes": file.size}
	for file in (evidence_files or [])
]
set_uploaded_file_metadata(workbook_name, workbook_size, evidence_file_metadata)

if workbook_name:
	st.write(f"**Workbook uploaded:** {workbook_name} ({workbook_size} bytes)")
else:
	st.caption("No workbook uploaded yet.")

if evidence_file_metadata:
	st.write(f"**Evidence files uploaded:** {len(evidence_file_metadata)}")
	for item in evidence_file_metadata:
		st.write(f"- {item['name']} ({item['size_bytes']} bytes)")
else:
	st.caption("No evidence files uploaded yet.")

if st.button("Run demo analysis", type="primary"):
	raw_response = MockApiClient().analyze()
	adapted_response = adapt_analysis_response(raw_response)

	if not workbook_name and not evidence_file_metadata:
		st.warning("No files uploaded. Loading prepared demo analysis without uploaded-file metadata.")
	else:
		adapted_response["uploaded_demo_files"] = {
			"workbook": {
				"name": workbook_name,
				"size_bytes": workbook_size,
			},
			"evidence_files": evidence_file_metadata,
			"note": (
				"Files captured for demo UI flow; prepared mock analysis response "
				"used for findings."
			),
		}

	set_analysis_response(adapted_response)
	st.session_state["demo_analysis_loaded_from_uploaded_flow"] = True
	st.success("Demo analysis run complete. Prepared backend response loaded.")

analysis_response = get_analysis_response()

if analysis_response:
	st.subheader("Loaded analysis snapshot")

	snapshot_col1, snapshot_col2, snapshot_col3 = st.columns(3)
	snapshot_col1.metric("Run ID", analysis_response.get("run_id", "N/A"))
	snapshot_col2.metric("Status", analysis_response.get("status", "unknown"))
	snapshot_col3.metric("Generated", analysis_response.get("generated_at") or "N/A")

	uploaded_demo_files = (
		analysis_response.get("uploaded_demo_files")
		if isinstance(analysis_response.get("uploaded_demo_files"), dict)
		else {}
	)
	workbook_info = (
		uploaded_demo_files.get("workbook")
		if isinstance(uploaded_demo_files.get("workbook"), dict)
		else {}
	)
	evidence_info = uploaded_demo_files.get("evidence_files")
	evidence_count = len(evidence_info) if isinstance(evidence_info, list) else 0

	if workbook_info.get("name"):
		st.write(f"**Uploaded workbook:** {workbook_info.get('name')}")
	if evidence_count:
		st.write(f"**Uploaded evidence count:** {evidence_count}")

	render_summary_cards(analysis_response.get("summary", {}))

	session_upload_meta = get_uploaded_file_metadata()
	if session_upload_meta.get("uploaded_evidence_count"):
		st.caption(
			"Session upload metadata captured: "
			f"{session_upload_meta.get('uploaded_evidence_count')} evidence file(s), "
			f"{session_upload_meta.get('uploaded_evidence_total_size')} total bytes."
		)

	warnings = analysis_response.get("warnings") or []
	if warnings:
		with st.expander("Response warnings", expanded=False):
			for warning in warnings:
				st.write(f"- {warning}")
