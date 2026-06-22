from __future__ import annotations

from typing import Any

import streamlit as st


def _check_icon(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"pass", "ok", "accepted"}:
        return "✓"
    if normalized in {"fail", "error"}:
        return "✕"
    return "⚑"


def _check_label(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"pass", "ok", "accepted"}:
        return "Pass"
    if normalized in {"fail", "error"}:
        return "Fail"
    return "Flag"


def render_reasoning_trail(checks: list[dict]) -> None:
    checks = [item for item in checks if isinstance(item, dict)]
    if not checks:
        st.info("No reasoning trail checks are available for this record.")
        return

    for check in checks:
        label = str(check.get("label") or check.get("check_id") or "Check")
        status = str(check.get("status") or check.get("outcome") or "flag")
        observed = check.get("observed")
        expected = check.get("expected")
        explanation = str(check.get("explanation") or check.get("message") or "")

        with st.container(border=True):
            st.markdown(f"**{_check_icon(status)} {label}**")
            st.caption(f"{_check_label(status)}")
            if explanation:
                st.write(explanation)
            if observed is not None:
                st.write(f"Observed: {observed}")
            if expected is not None:
                st.write(f"Expected: {expected}")


def render_evidence_trace(evidence_refs: list[dict]) -> None:
    evidence_refs = [item for item in evidence_refs if isinstance(item, dict)]
    if not evidence_refs:
        st.caption("Evidence trail: Needs confirmation")
        return

    for evidence in evidence_refs:
        evidence_id = evidence.get("evidence_id") or "Unknown evidence"
        relationship = evidence.get("relationship_to_gap") or "linked evidence"
        source_locations = evidence.get("source_locations") if isinstance(evidence.get("source_locations"), list) else []

        with st.container(border=True):
            st.write(f"**{evidence_id}** ({relationship})")
            if source_locations:
                first = source_locations[0] if isinstance(source_locations[0], dict) else {}
                page = first.get("page_number")
                snippet = first.get("source_snippet")
                if page is not None:
                    st.caption(f"Source page: {page}")
                if snippet:
                    st.write(snippet)


def render_regulatory_basis(citations: list[dict]) -> None:
    citations = [item for item in citations if isinstance(item, dict)]
    if not citations:
        st.caption("Regulatory basis: Needs confirmation")
        return

    for citation in citations:
        authority = citation.get("authority") or "Authority"
        citation_code = citation.get("citation") or "Citation"
        summary = citation.get("requirement_summary") or "Regulatory summary"
        applicability = citation.get("applicability_explanation") or "Needs confirmation"

        with st.container(border=True):
            st.write(f"**{authority} {citation_code}**")
            st.write(f"Regulatory summary: {summary}")
            st.caption(f"Applicability: {applicability}")


def summarize_workbook_trace(location: dict[str, Any] | None) -> str:
    if not isinstance(location, dict):
        return "Needs confirmation"
    sheet = location.get("sheet_name")
    cell = location.get("cell_or_range")
    if sheet and cell:
        return f"{sheet}!{cell}"
    return "Needs confirmation"
