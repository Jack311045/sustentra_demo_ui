from __future__ import annotations

import streamlit as st

from src.ui.components import render_ticket_header
from src.ui.state import (
	get_analysis_response,
	get_selected_gap_ticket_id,
	init_session_state,
	set_selected_gap_ticket_id,
)


NO_ANALYSIS_MESSAGE = (
	'No analysis result loaded yet. Go to Upload and Analyze and click "Load prepared demo analysis."'
)


def _severity_value(ticket: dict) -> str:
	severity = ticket.get("severity")
	if isinstance(severity, dict):
		return str(severity.get("auditor_assigned") or severity.get("system_suggested") or "")
	if severity is None:
		return ""
	return str(severity)


init_session_state()

st.title("Finding Detail")

analysis_response = get_analysis_response()
if not analysis_response:
	st.info(NO_ANALYSIS_MESSAGE)
	st.stop()

gap_tickets = [ticket for ticket in (analysis_response.get("gap_tickets") or []) if isinstance(ticket, dict)]
if not gap_tickets:
	st.info("No findings available in the loaded analysis response.")
	st.stop()

ticket_by_id = {
	str(ticket.get("gap_ticket_id")): ticket
	for ticket in gap_tickets
	if ticket.get("gap_ticket_id")
}
ticket_ids = list(ticket_by_id.keys())
if not ticket_ids:
	st.info("No gap_ticket_id values were found in gap tickets.")
	st.stop()

selected_ticket_id = get_selected_gap_ticket_id()
if selected_ticket_id not in ticket_by_id:
	selected_ticket_id = ticket_ids[0]

selected_ticket_id = st.selectbox(
	"Select gap ticket",
	options=ticket_ids,
	index=ticket_ids.index(selected_ticket_id),
)
set_selected_gap_ticket_id(selected_ticket_id)

ticket = ticket_by_id[selected_ticket_id]
render_ticket_header(ticket)

issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
basis = ticket.get("basis") if isinstance(ticket.get("basis"), dict) else {}
remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}

st.subheader("Core fields")
core_col1, core_col2, core_col3 = st.columns(3)
core_col1.write(f"**Ticket ID:** {ticket.get('gap_ticket_id') or 'N/A'}")
core_col1.write(f"**Title:** {ticket.get('title') or 'N/A'}")
core_col1.write(f"**Status:** {ticket.get('status') or 'N/A'}")

core_col2.write(f"**Assertion:** {ticket.get('primary_assertion') or 'N/A'}")
core_col2.write(f"**Severity:** {_severity_value(ticket) or 'N/A'}")
core_col2.write(f"**Finding type:** {ticket.get('finding_type') or 'N/A'}")

core_col3.write(f"**Observed condition:** {issue.get('observed_condition') or 'N/A'}")
core_col3.write(f"**Expected condition:** {issue.get('expected_condition') or 'N/A'}")
core_col3.write(f"**Why triggered:** {issue.get('why_triggered') or 'N/A'}")

st.subheader("Scope and rule trace")
st.write(f"**Affected scope:**")
st.json(ticket.get("affected_scope") or {})
st.write("**Upstream rule results:**")
st.json(ticket.get("upstream_rule_results") or [])

st.subheader("Linked evidence and workbook locations")
st.write("**Linked evidence:**")
st.json(ticket.get("linked_evidence") or [])
st.write("**Linked workbook locations:**")
st.json(ticket.get("linked_workbook_locations") or [])

st.subheader("Regulatory and assurance basis")
st.write("**Regulatory citations:**")
st.json(basis.get("regulatory_citations") or [])
st.write("**Assurance basis:**")
st.json(basis.get("assurance_basis") or [])
st.write("**Internal basis:**")
st.json(basis.get("internal_basis") or [])

st.subheader("Remediation")
st.write(f"**Recommended action:** {remediation.get('recommended_action') or 'N/A'}")
st.write("**Required additional evidence:**")
st.json(remediation.get("required_additional_evidence") or [])
st.write(
	f"**Suggested client question:** {remediation.get('suggested_client_question') or 'N/A'}"
)

st.subheader("Mock auditor actions")
action_key = f"auditor_action_{selected_ticket_id}"
note_key = f"auditor_note_{selected_ticket_id}"

action = st.radio(
	"Choose auditor action",
	options=["Confirm", "Dismiss", "Request clarification"],
	horizontal=True,
	key=action_key,
)
note = st.text_area("Add auditor note", key=note_key)

if st.button("Apply mock auditor action"):
	st.session_state.setdefault("mock_auditor_actions", {})
	st.session_state["mock_auditor_actions"][selected_ticket_id] = {
		"action": action,
		"note": note,
	}
	st.success(f"Saved mock auditor action for {selected_ticket_id} in session state.")

existing_action = st.session_state.get("mock_auditor_actions", {}).get(selected_ticket_id)
if existing_action:
	st.info(
		f"Current mock action: {existing_action.get('action')} | Note: {existing_action.get('note') or '(none)'}"
	)
