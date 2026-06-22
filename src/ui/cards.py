from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui.formatting import category_label, normalize_severity, severity_label, status_label


def render_severity_badge(severity: str) -> None:
    normalized = normalize_severity(severity)
    if normalized in {"critical", "high"}:
        st.markdown(f"<span style='color:#B42318;'>⚠ {severity_label(severity)}</span>", unsafe_allow_html=True)
    elif normalized == "medium":
        st.markdown(f"<span style='color:#B54708;'>⚑ {severity_label(severity)}</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span style='color:#175CD3;'>ℹ {severity_label(severity)}</span>", unsafe_allow_html=True)


def render_status_badge(status: str) -> None:
    text = status_label(status)
    st.markdown(f"<span style='color:#344054;'>● {text}</span>", unsafe_allow_html=True)


def render_gap_category_badge(category: str) -> None:
    text = category_label(category)
    st.markdown(f"<span style='color:#475467;'>Category: {text}</span>", unsafe_allow_html=True)


def _single_line(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return "Needs confirmation"
    if len(value) <= 180:
        return value
    return value[:177] + "..."


def render_gap_card(ticket: dict, key_prefix: str) -> dict[str, bool]:
    issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
    remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}
    linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    linked_workbook = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )

    title = ticket.get("auditor_title") or ticket.get("title") or "Untitled finding"
    severity = ticket.get("severity")
    category = ticket.get("auditor_category") or ticket.get("finding_type")

    with st.container(border=True):
        top_col1, top_col2, top_col3 = st.columns([1, 1, 3])
        with top_col1:
            render_severity_badge(str(severity or ""))
        with top_col2:
            render_gap_category_badge(str(category or ""))
        with top_col3:
            render_status_badge(str(ticket.get("status") or ""))

        st.markdown(f"### {title}")
        st.write(f"**What we found:** {_single_line(issue.get('observed_condition'))}")
        st.write(f"**Why this matters:** {_single_line(issue.get('why_triggered'))}")
        st.write(f"**What's next:** {_single_line(remediation.get('recommended_action'))}")

        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        action_open_evidence = action_col1.button(
            "Open evidence",
            key=f"{key_prefix}_open_evidence",
            use_container_width=True,
        )
        action_open_workbook = action_col2.button(
            "Open workbook location",
            key=f"{key_prefix}_open_workbook",
            use_container_width=True,
        )
        action_show_regulation = action_col3.button(
            "Show regulation",
            key=f"{key_prefix}_show_regulation",
            use_container_width=True,
        )
        action_ask_reg = action_col4.button(
            "Ask Regulatory Assistant",
            key=f"{key_prefix}_ask_reg",
            use_container_width=True,
        )
        action_note = action_col5.button(
            "Draft auditor note",
            key=f"{key_prefix}_draft_note",
            use_container_width=True,
        )

        evidence_bits: list[str] = []
        if linked_evidence:
            first = linked_evidence[0] if isinstance(linked_evidence[0], dict) else {}
            evidence_bits.append(str(first.get("evidence_id") or "Unknown evidence"))
        if linked_workbook:
            first_loc = linked_workbook[0] if isinstance(linked_workbook[0], dict) else {}
            sheet = first_loc.get("sheet_name")
            cell = first_loc.get("cell_or_range")
            if sheet and cell:
                evidence_bits.append(f"{sheet}!{cell}")

        st.caption("Evidence trail: " + (" · ".join(evidence_bits) if evidence_bits else "Needs confirmation"))

        with st.expander("Advanced rule trace", expanded=False):
            st.json(ticket.get("upstream_rule_results") or [])

    return {
        "open_evidence": action_open_evidence,
        "open_workbook": action_open_workbook,
        "show_regulation": action_show_regulation,
        "ask_regulatory_assistant": action_ask_reg,
        "draft_auditor_note": action_note,
    }
