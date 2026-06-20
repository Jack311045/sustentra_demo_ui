from __future__ import annotations

import streamlit as st

from src.ui.state import get_analysis_response, init_session_state
from src.ui.tables import render_evidence_table


NO_ANALYSIS_MESSAGE = (
	'No analysis result loaded yet. Go to Upload and Analyze and click "Run demo analysis."'
)


def _normalized_review_status(record: dict) -> str:
	raw = (record.get("ui_status") or record.get("status") or "").strip().lower()
	if raw == "needs_review":
		return "need_review"
	return raw


init_session_state()

st.title("Evidence Review")

analysis_response = get_analysis_response()
if not analysis_response:
	st.info(NO_ANALYSIS_MESSAGE)
	st.stop()

uploaded_demo_files = analysis_response.get("uploaded_demo_files")
if isinstance(uploaded_demo_files, dict):
	workbook = uploaded_demo_files.get("workbook")
	workbook_name = workbook.get("name") if isinstance(workbook, dict) else None
	evidence_files = uploaded_demo_files.get("evidence_files")
	evidence_count = len(evidence_files) if isinstance(evidence_files, list) else 0
	if workbook_name or evidence_count:
		st.caption(
			"Demo analysis loaded for uploaded files: "
			f"{workbook_name or 'N/A'} + {evidence_count} evidence file(s)."
		)

evidence_results = analysis_response.get("evidence_results") or []

status_counts = {"pass": 0, "flagged": 0, "need_review": 0}
for evidence in evidence_results:
	if not isinstance(evidence, dict):
		continue
	status = _normalized_review_status(evidence)
	if status in status_counts:
		status_counts[status] += 1

col1, col2, col3, col4 = st.columns(4)
col1.metric("Evidence records", len(evidence_results))
col2.metric("Pass", status_counts["pass"])
col3.metric("Flagged", status_counts["flagged"])
col4.metric("Need review", status_counts["need_review"])

filter_option = st.selectbox(
	"Filter by review status",
	options=["all", "pass", "flagged", "need_review"],
	index=0,
)

if filter_option == "all":
	filtered_evidence = [r for r in evidence_results if isinstance(r, dict)]
else:
	filtered_evidence = [
		r
		for r in evidence_results
		if isinstance(r, dict) and _normalized_review_status(r) == filter_option
	]

st.subheader("Evidence table")
render_evidence_table(filtered_evidence)

evidence_ids = [str(r.get("evidence_id")) for r in filtered_evidence if r.get("evidence_id")]
if not evidence_ids:
	st.info("No evidence records available for the selected filter.")
	st.stop()

previous_id = st.session_state.get("selected_evidence_id")
default_index = evidence_ids.index(previous_id) if previous_id in evidence_ids else 0

selected_evidence_id = st.selectbox(
	"Select evidence by evidence_id",
	options=evidence_ids,
	index=default_index,
)
st.session_state["selected_evidence_id"] = selected_evidence_id

selected_evidence = next(
	(
		record
		for record in filtered_evidence
		if str(record.get("evidence_id")) == selected_evidence_id
	),
	None,
)

if not selected_evidence:
	st.info("Selected evidence item could not be found.")
	st.stop()

st.subheader("Selected evidence detail")
detail_col1, detail_col2, detail_col3 = st.columns(3)
detail_col1.write(f"**Document type:** {selected_evidence.get('document_type') or 'N/A'}")
detail_col2.write(
	f"**Evidence type:** {selected_evidence.get('evidence_type_name') or selected_evidence.get('evidence_type_id') or 'N/A'}"
)
detail_col3.write(
	f"**Status:** {selected_evidence.get('ui_status') or selected_evidence.get('status') or 'N/A'}"
)

linked_ids = selected_evidence.get("linked_gap_ticket_ids") or []
st.write("**Linked gap ticket IDs:**", ", ".join(str(i) for i in linked_ids) if linked_ids else "None")

st.markdown("**Extracted fields**")
st.json(selected_evidence.get("extracted_fields") or {})

st.markdown("**Source references**")
st.json(selected_evidence.get("source_references") or [])
