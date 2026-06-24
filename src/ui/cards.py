from __future__ import annotations

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


def render_gap_card(ticket: dict, key_prefix: str) -> dict[str, bool]:
    st.info("render_gap_card is deprecated. Use the Gap Analysis master-detail workspace on Page 6.")
    return {
        "open_evidence": False,
        "open_workbook": False,
        "show_regulation": False,
        "ask_regulatory_assistant": False,
        "draft_auditor_note": False,
    }
