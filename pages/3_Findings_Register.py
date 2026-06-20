from __future__ import annotations

import streamlit as st

from src.ui.state import (
	get_analysis_response,
	init_session_state,
	set_selected_gap_ticket_id,
)
from src.ui.tables import render_findings_table


NO_ANALYSIS_MESSAGE = (
	'No analysis result loaded yet. Go to Upload and Analyze and click "Run demo analysis."'
)


def _severity_value(ticket: dict) -> str:
	severity = ticket.get("severity")
	if isinstance(severity, dict):
		return str(severity.get("auditor_assigned") or severity.get("system_suggested") or "")
	if severity is None:
		return ""
	return str(severity)


init_session_state()

st.title("Findings Register")

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

gap_tickets = [ticket for ticket in (analysis_response.get("gap_tickets") or []) if isinstance(ticket, dict)]
if not gap_tickets:
	st.info("No findings available in the loaded analysis response.")
	st.stop()

assertion_options = ["all"] + sorted(
	{str(t.get("primary_assertion")) for t in gap_tickets if t.get("primary_assertion")}
)
severity_options = ["all"] + sorted(
	{v for v in (_severity_value(t) for t in gap_tickets) if v}
)
status_options = ["all"] + sorted({str(t.get("status")) for t in gap_tickets if t.get("status")})
finding_type_options = ["all"] + sorted(
	{str(t.get("finding_type")) for t in gap_tickets if t.get("finding_type")}
)

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
selected_assertion = filter_col1.selectbox("Assertion", assertion_options, index=0)
selected_severity = filter_col2.selectbox("Severity", severity_options, index=0)
selected_status = filter_col3.selectbox("Status", status_options, index=0)
selected_finding_type = filter_col4.selectbox("Finding type", finding_type_options, index=0)

filtered_tickets = []
for ticket in gap_tickets:
	if selected_assertion != "all" and str(ticket.get("primary_assertion")) != selected_assertion:
		continue
	if selected_severity != "all" and _severity_value(ticket) != selected_severity:
		continue
	if selected_status != "all" and str(ticket.get("status")) != selected_status:
		continue
	if selected_finding_type != "all" and str(ticket.get("finding_type")) != selected_finding_type:
		continue
	filtered_tickets.append(ticket)

st.subheader("Findings table")
render_findings_table(filtered_tickets)

ticket_ids = [str(t.get("gap_ticket_id")) for t in filtered_tickets if t.get("gap_ticket_id")]
if not ticket_ids:
	st.info("No findings match the selected filters.")
	st.stop()

selected_ticket_id = st.selectbox("Select finding by gap_ticket_id", ticket_ids, index=0)
set_selected_gap_ticket_id(selected_ticket_id)

selected_ticket = next(
	(t for t in filtered_tickets if str(t.get("gap_ticket_id")) == selected_ticket_id),
	None,
)
if not selected_ticket:
	st.info("Selected finding could not be found.")
	st.stop()

issue = selected_ticket.get("issue") if isinstance(selected_ticket.get("issue"), dict) else {}
remediation = (
	selected_ticket.get("remediation")
	if isinstance(selected_ticket.get("remediation"), dict)
	else {}
)

st.subheader("Selected finding preview")
st.write(f"**Title:** {selected_ticket.get('title') or 'N/A'}")
st.write(f"**Observed condition:** {issue.get('observed_condition') or 'N/A'}")
st.write(f"**Expected condition:** {issue.get('expected_condition') or 'N/A'}")
st.write(f"**Why triggered:** {issue.get('why_triggered') or 'N/A'}")
st.write(f"**Recommended action:** {remediation.get('recommended_action') or 'N/A'}")
st.info("Open Finding Detail for full traceability and mock auditor action controls.")
