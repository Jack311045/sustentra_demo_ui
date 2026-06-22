from __future__ import annotations

import streamlit as st

from src.ui.cards import render_severity_badge, render_status_badge
from src.ui.formatting import safe_text, severity_label


def render_summary_cards(summary: dict) -> None:
    summary = summary if isinstance(summary, dict) else {}

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Evidence", summary.get("total_evidence", 0))
    col2.metric("Passed", summary.get("passed", 0))
    col3.metric("Flagged", summary.get("flagged", 0))
    col4.metric("Needs Review", summary.get("needs_review", 0))
    col5.metric("Total Findings", summary.get("total_findings", 0))


def render_offering_cards() -> None:
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.markdown("### Evidence extraction")
            st.write("- Clean extraction")
            st.write("- Source traceability")
            st.write("- Human review")

    with col2:
        with st.container(border=True):
            st.markdown("### Gap analysis")
            st.write("- Validation")
            st.write("- Calculation/reconciliation")
            st.write("- Reasoning trail")
            st.write("- Auditor-facing findings")

    with col3:
        with st.container(border=True):
            st.markdown("### Regulation intelligence")
            st.write("- NY Part 253 RAG")
            st.write("- Source-backed regulatory answers")
            st.write("- Contextual audit support")


def render_ticket_header(ticket: dict) -> None:
    ticket = ticket if isinstance(ticket, dict) else {}
    ticket_id = ticket.get("gap_ticket_id", "N/A")
    title = ticket.get("title", "Untitled finding")

    st.subheader(f"{ticket_id}: {title}")
    render_status_badge(safe_text(ticket.get("status", "unknown")))

    severity = ticket.get("severity")
    render_severity_badge(str(severity_label(severity or "unknown")))
