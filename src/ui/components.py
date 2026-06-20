from __future__ import annotations

import streamlit as st


def render_status_badge(label: str) -> None:
    value = (label or "unknown").strip() or "unknown"
    st.caption(f"Status: {value}")


def render_severity_badge(label: str) -> None:
    value = (label or "unknown").strip() or "unknown"
    st.caption(f"Severity: {value}")


def render_summary_cards(summary: dict) -> None:
    summary = summary if isinstance(summary, dict) else {}

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Evidence", summary.get("total_evidence", 0))
    col2.metric("Passed", summary.get("passed", 0))
    col3.metric("Flagged", summary.get("flagged", 0))
    col4.metric("Needs Review", summary.get("needs_review", 0))
    col5.metric("Total Findings", summary.get("total_findings", 0))


def render_ticket_header(ticket: dict) -> None:
    ticket = ticket if isinstance(ticket, dict) else {}
    ticket_id = ticket.get("gap_ticket_id", "N/A")
    title = ticket.get("title", "Untitled finding")

    st.subheader(f"{ticket_id}: {title}")
    render_status_badge(ticket.get("status", "unknown"))

    severity = ticket.get("severity")
    if isinstance(severity, dict):
        severity_label = severity.get("auditor_assigned") or severity.get("system_suggested")
    else:
        severity_label = severity
    render_severity_badge(str(severity_label or "unknown"))
