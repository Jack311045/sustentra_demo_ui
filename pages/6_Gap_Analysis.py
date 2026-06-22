from __future__ import annotations

import streamlit as st

from src.ui.cards import render_gap_card
from src.ui.formatting import assertion_label, category_label, normalize_severity, severity_label, status_label
from src.ui.state import (
    ask_regulatory_assistant,
    draft_auditor_note,
    get_analysis_response,
    init_session_state,
    open_applicable_regulation,
    open_original_evidence,
    open_workbook_location,
)
from src.ui.traceability import render_evidence_trace, render_reasoning_trail, render_regulatory_basis
from src.ui.workflow import render_prepared_demo_disclosure, render_workflow_progress


TITLE_MAP = {
    "GT-DEMO-GAP-002": "Pilot-light emissions may be missing",
    "GT-DEMO-GAP-003": "October natural-gas usage does not match the source bill",
    "GT-DEMO-GAP-004": "Different combustion source types were combined",
    "GT-DEMO-GAP-005": "Biomass activity uses the wrong emission factor",
    "GT-DEMO-GAP-006": "Biomass sampling support is incomplete",
    "GT-DEMO-GAP-007": "December estimate lacks approved substitution support",
    "GT-DEMO-GAP-008": "Annual billing evidence is incomplete",
    "GT-DEMO-GAP-009": "Cross-year bill was not allocated between reporting years",
    "GT-DEMO-GAP-010": "Workbook uses the wrong GWP basis",
}

CATEGORY_BY_TICKET = {
    "GT-DEMO-GAP-002": "Missing evidence",
    "GT-DEMO-GAP-003": "Data mismatch",
    "GT-DEMO-GAP-004": "Boundary or aggregation",
    "GT-DEMO-GAP-005": "Methodology or factor",
    "GT-DEMO-GAP-006": "Sampling support",
    "GT-DEMO-GAP-007": "Unsupported estimate",
    "GT-DEMO-GAP-008": "Missing evidence",
    "GT-DEMO-GAP-009": "Cutoff or allocation",
    "GT-DEMO-GAP-010": "GWP or conversion basis",
}


init_session_state()
st.title("Gap Analysis")
st.caption("Auditor-facing findings with evidence trace, workbook trace, and regulatory basis.")
render_workflow_progress(current_step=6)
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

gap_tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
if not gap_tickets:
    st.info("No gap tickets are available in the prepared dataset.")
    st.stop()

# Gap 1 is excluded from the auditor-facing demo register.
gap_tickets = [
    ticket
    for ticket in gap_tickets
    if str(ticket.get("gap_ticket_id") or "").strip().upper() != "GT-DEMO-GAP-001"
]

for ticket in gap_tickets:
    ticket_id = str(ticket.get("gap_ticket_id") or "")
    ticket["auditor_title"] = TITLE_MAP.get(ticket_id, ticket.get("title") or "Untitled finding")
    ticket["auditor_category"] = CATEGORY_BY_TICKET.get(
        ticket_id,
        category_label(ticket.get("finding_type")),
    )

severity_filters = ["All"] + sorted({severity_label(ticket.get("severity")) for ticket in gap_tickets})
status_filters = ["All"] + sorted({status_label(ticket.get("status")) for ticket in gap_tickets})
category_filters = ["All"] + sorted({str(ticket.get("auditor_category")) for ticket in gap_tickets})
audit_objective_filters = ["All"] + sorted({assertion_label(ticket.get("primary_assertion")) for ticket in gap_tickets})

fcol1, fcol2, fcol3, fcol4 = st.columns(4)
selected_severity = fcol1.selectbox("Severity", options=severity_filters, index=0)
selected_status = fcol2.selectbox("Status", options=status_filters, index=0)
selected_category = fcol3.selectbox("Category", options=category_filters, index=0)
selected_audit_objective = fcol4.selectbox("Audit objective", options=audit_objective_filters, index=0)

filtered_tickets = []
for ticket in gap_tickets:
    ticket_severity = severity_label(ticket.get("severity"))
    ticket_status = status_label(ticket.get("status"))
    ticket_category = str(ticket.get("auditor_category"))
    ticket_assertion = assertion_label(ticket.get("primary_assertion"))

    if selected_severity != "All" and ticket_severity != selected_severity:
        continue
    if selected_status != "All" and ticket_status != selected_status:
        continue
    if selected_category != "All" and ticket_category != selected_category:
        continue
    if selected_audit_objective != "All" and ticket_assertion != selected_audit_objective:
        continue

    filtered_tickets.append(ticket)

if not filtered_tickets:
    st.info("No gap tickets match this filter set.")
    st.stop()

st.caption(f"Displaying {len(filtered_tickets)} auditor-facing gap cards.")

for ticket in sorted(filtered_tickets, key=lambda item: normalize_severity(item.get("severity"))):
    ticket_id = str(ticket.get("gap_ticket_id") or "")

    actions = render_gap_card(ticket, key_prefix=ticket_id)

    linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    linked_workbook = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )
    basis = ticket.get("basis") if isinstance(ticket.get("basis"), dict) else {}

    if actions.get("open_evidence"):
        selected_evidence = linked_evidence[0].get("evidence_id") if linked_evidence and isinstance(linked_evidence[0], dict) else None
        open_original_evidence(selected_evidence)

    if actions.get("open_workbook"):
        selected_location = linked_workbook[0] if linked_workbook and isinstance(linked_workbook[0], dict) else None
        open_workbook_location(selected_location)

    if actions.get("show_regulation"):
        open_applicable_regulation(ticket_id)

    if actions.get("ask_regulatory_assistant"):
        ask_regulatory_assistant(
            ticket_id,
            suggested_prompt=f"Explain why {ticket.get('auditor_title')} matters for this audit.",
        )

    if actions.get("draft_auditor_note"):
        draft_auditor_note(ticket_id)

    action_col1, action_col2, action_col3 = st.columns(3)
    if action_col1.button("Confirm", key=f"confirm_{ticket_id}"):
        st.session_state.setdefault("mock_auditor_actions", {})
        st.session_state["mock_auditor_actions"][ticket_id] = {"action": "Confirm"}
    if action_col2.button("Dismiss", key=f"dismiss_{ticket_id}"):
        st.session_state.setdefault("mock_auditor_actions", {})
        st.session_state["mock_auditor_actions"][ticket_id] = {"action": "Dismiss"}
    if action_col3.button("Request clarification", key=f"clarify_{ticket_id}"):
        st.session_state.setdefault("mock_auditor_actions", {})
        st.session_state["mock_auditor_actions"][ticket_id] = {"action": "Request clarification"}

    note_value = st.text_area("Add auditor note", key=f"note_{ticket_id}", height=80)
    if st.button("Save note", key=f"save_note_{ticket_id}"):
        st.session_state.setdefault("mock_auditor_actions", {})
        current = st.session_state["mock_auditor_actions"].get(ticket_id, {})
        current["note"] = note_value
        st.session_state["mock_auditor_actions"][ticket_id] = current
        st.success(f"Saved note for {ticket_id}.")

    with st.expander("Details", expanded=False):
        issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
        st.write(f"**What we found:** {issue.get('observed_condition') or 'Needs confirmation'}")
        st.write(f"**What should be true:** {issue.get('expected_condition') or 'Needs confirmation'}")
        st.write(f"**Why this matters:** {issue.get('why_triggered') or 'Needs confirmation'}")
        remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}
        st.write(f"**What's next:** {remediation.get('recommended_action') or 'Needs confirmation'}")

    with st.expander("Evidence trail", expanded=False):
        render_evidence_trace(linked_evidence)
        if linked_workbook:
            st.write("Workbook trace")
            for location in linked_workbook:
                if not isinstance(location, dict):
                    continue
                sheet = location.get("sheet_name") or "Unknown sheet"
                cell = location.get("cell_or_range") or "Unknown cell"
                st.caption(f"{sheet}!{cell}")

    with st.expander("Regulatory basis", expanded=False):
        citations = basis.get("regulatory_citations") if isinstance(basis.get("regulatory_citations"), list) else []
        render_regulatory_basis(citations)

    with st.expander("Reasoning trail", expanded=False):
        render_reasoning_trail(ticket.get("upstream_rule_results") if isinstance(ticket.get("upstream_rule_results"), list) else [])
