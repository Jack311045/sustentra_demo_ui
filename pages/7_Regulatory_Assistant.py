from __future__ import annotations

from typing import Any

import streamlit as st

from src.api.rag_client import (
    RagApiError,
    get_auditor_chat_mode,
    has_rag_configuration,
    query_rag,
)
from src.ui.state import (
    append_chat_message,
    get_analysis_response,
    get_audit_setup,
    get_chat_context_gap_ticket_id,
    get_chat_history,
    init_session_state,
    set_chat_context_gap_ticket_id,
)
from src.ui.workflow import render_prepared_demo_disclosure


FALLBACK_NOTICE = "Prepared demo answer shown because the live regulatory service is unavailable."


def _find_ticket(gap_tickets: list[dict], ticket_id: str | None) -> dict | None:
    if not ticket_id:
        return None
    for ticket in gap_tickets:
        if not isinstance(ticket, dict):
            continue
        if str(ticket.get("gap_ticket_id")) == str(ticket_id):
            return ticket
    return None


def _audit_context_text(audit_setup: dict, analysis_response: dict) -> str:
    company_profile = audit_setup.get("company_and_facility_profile", {})
    reporting_boundary = audit_setup.get("reporting_boundary", {})
    regulation = audit_setup.get("regulation_and_verification", {})

    facility_name = company_profile.get("facility_name") or analysis_response.get("engagement", {}).get("facility_name")
    reporting_period = company_profile.get("reporting_period") or "Needs confirmation"
    primary_reg = regulation.get("primary_regulation") or "NY Part 253"
    consolidation = reporting_boundary.get("consolidation_approach") or "Operational control"
    assurance_standard = regulation.get("verification_standard") or "ISSA 5000"
    assurance_level = regulation.get("assurance_level") or "Limited assurance"

    return (
        f"Facility: {facility_name or 'Needs confirmation'}; "
        f"Reporting period: {reporting_period}; "
        f"Primary regulation: {primary_reg}; "
        f"Consolidation approach (audit context): {consolidation}; "
        f"Assurance standard (audit context): {assurance_standard}; "
        f"Assurance level (audit context): {assurance_level}"
    )


def _ticket_issue_text(ticket: dict | None) -> str:
    if not ticket:
        return "Issue\nUse this assistant for NY Part 253 research tied to the current audit step."
    issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
    return f"Issue\n{issue.get('observed_condition') or 'Needs confirmation'}"


def _ticket_evidence_trace(ticket: dict | None) -> str:
    if not ticket:
        return "Evidence trace\nNeeds confirmation"

    linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    linked_workbook = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )

    evidence_part = "Needs confirmation"
    if linked_evidence and isinstance(linked_evidence[0], dict):
        evidence_part = str(linked_evidence[0].get("evidence_id") or "Needs confirmation")

    workbook_part = "Needs confirmation"
    if linked_workbook and isinstance(linked_workbook[0], dict):
        first = linked_workbook[0]
        sheet = first.get("sheet_name") or "Unknown sheet"
        cell = first.get("cell_or_range") or "Unknown cell"
        workbook_part = f"{sheet}!{cell}"

    return f"Evidence trace\n{evidence_part} · {workbook_part}"


def _ticket_next_actions(ticket: dict | None) -> str:
    if not ticket:
        return (
            "Next actions\n"
            "- Open original evidence\n"
            "- Open workbook location\n"
            "- Show applicable regulation\n"
            "- Draft auditor note"
        )

    remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}
    action = remediation.get("recommended_action") or "Needs confirmation"
    return (
        "Next actions\n"
        f"- {action}\n"
        "- Open original evidence\n"
        "- Open workbook location\n"
        "- Show applicable regulation\n"
        "- Draft auditor note"
    )


def _citation_warning_needed(citation_validation: Any) -> bool:
    if not isinstance(citation_validation, dict):
        return False
    status = str(citation_validation.get("status") or "").strip().lower()
    if status in {"warning", "flagged", "fail", "invalid"}:
        return True
    valid_flag = citation_validation.get("valid")
    if valid_flag is False:
        return True
    warning_text = str(citation_validation.get("warning") or "").strip()
    return bool(warning_text)


def _fallback_answer(question: str, prepared_answers: dict[str, str]) -> str:
    direct = prepared_answers.get(question)
    if direct:
        return direct
    return (
        "Regulatory summary\n"
        "This prepared demo fallback cannot verify live regulation text right now. "
        "Use the available gap evidence trail and rerun with live service when available."
    )


def _compose_response(
    question: str,
    ticket: dict | None,
    audit_setup: dict,
    analysis_response: dict,
    prepared_answers: dict[str, str],
    mode: str,
) -> tuple[str, dict]:
    can_use_real = has_rag_configuration()
    use_real = mode == "real" or (mode == "auto" and can_use_real)

    metadata: dict[str, Any] = {
        "sources": [],
        "citation_validation": None,
        "fallback_used": False,
    }

    if use_real:
        try:
            rag_result = query_rag(question=question)
            answer_text = str(rag_result.get("answer") or "Regulatory summary unavailable from live service.")
            metadata["sources"] = rag_result.get("sources") or []
            metadata["citation_validation"] = rag_result.get("citation_validation")
            regulatory_basis = f"Regulatory basis\n{answer_text}"
        except RagApiError:
            metadata["fallback_used"] = True
            fallback_text = _fallback_answer(question, prepared_answers)
            regulatory_basis = f"Regulatory basis\nRegulatory summary\n{fallback_text}"
    else:
        metadata["fallback_used"] = True
        fallback_text = _fallback_answer(question, prepared_answers)
        regulatory_basis = f"Regulatory basis\nRegulatory summary\n{fallback_text}"

    composed = "\n\n".join(
        [
            _ticket_issue_text(ticket),
            _ticket_evidence_trace(ticket),
            f"Audit context\n{_audit_context_text(audit_setup, analysis_response)}",
            regulatory_basis,
            _ticket_next_actions(ticket),
        ]
    )

    return composed, metadata


init_session_state()
st.title("Regulatory Assistant")
st.caption("Source-backed regulatory support for NY Part 253 audit workflows.")
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

st.info("This system assists regulatory research and does not provide legal advice.")

mode = get_auditor_chat_mode()
gap_tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
chat_suggestions = [item for item in (analysis_response.get("chat_suggestions") or []) if isinstance(item, dict)]
prepared_answers = {
    str(item.get("question")): str(item.get("mock_answer") or "")
    for item in chat_suggestions
    if item.get("question")
}

context_ticket_id = get_chat_context_gap_ticket_id()
context_ticket = _find_ticket(gap_tickets, context_ticket_id)

if context_ticket:
    st.caption(f"Current gap context: {context_ticket.get('gap_ticket_id')} - {context_ticket.get('title')}")

if context_ticket:
    action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
    if action_col1.button("Explain why this gap matters"):
        st.session_state["pending_chat_prompt"] = f"Explain why {context_ticket.get('gap_ticket_id')} matters."
    if action_col2.button("Show supporting regulation"):
        st.session_state["pending_chat_prompt"] = f"Show the supporting regulation for {context_ticket.get('gap_ticket_id')}."
    if action_col3.button("Show evidence and workbook trace"):
        st.session_state["pending_chat_prompt"] = f"Show the evidence and workbook trace for {context_ticket.get('gap_ticket_id')}."
    if action_col4.button("Draft client clarification request"):
        st.session_state["pending_chat_prompt"] = f"Draft a client clarification request for {context_ticket.get('gap_ticket_id')}."
    if action_col5.button("Draft auditor note"):
        st.session_state["pending_chat_prompt"] = f"Draft an auditor note for {context_ticket.get('gap_ticket_id')}."

suggested_questions = [
    str(item.get("question"))
    for item in chat_suggestions
    if item.get("question")
]
if suggested_questions:
    st.caption("Suggested questions")
    q_cols = st.columns(min(3, len(suggested_questions)))
    for idx, question in enumerate(suggested_questions[:3]):
        if q_cols[idx].button(question, key=f"suggested_q_{idx}"):
            st.session_state["pending_chat_prompt"] = question

history = get_chat_history()
for message in history:
    role = str(message.get("role") or "assistant")
    content = str(message.get("content") or "")
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}

    with st.chat_message(role):
        st.write(content)

        if metadata.get("fallback_used"):
            st.caption(FALLBACK_NOTICE)

        citation_validation = metadata.get("citation_validation")
        if _citation_warning_needed(citation_validation):
            st.warning("Citation review warning: verify cited references before relying on this response.")

        sources = metadata.get("sources") if isinstance(metadata.get("sources"), list) else []
        if sources:
            for index, source in enumerate(sources, start=1):
                if not isinstance(source, dict):
                    continue
                title = source.get("title") or source.get("provisionKey") or f"Source {index}"
                with st.expander(f"Source {index}: {title}", expanded=False):
                    st.write(f"Provision key: {source.get('provisionKey') or 'N/A'}")
                    st.write(f"Section: {source.get('sectionId') or source.get('section') or 'N/A'}")
                    raw_text = source.get("rawText") or source.get("text") or source.get("content")
                    if raw_text:
                        st.write(raw_text)

pending_prompt = st.session_state.pop("pending_chat_prompt", None)
if pending_prompt and isinstance(pending_prompt, str):
    st.session_state["prefilled_chat_prompt"] = pending_prompt

prefilled_prompt = st.session_state.pop("prefilled_chat_prompt", None)
if prefilled_prompt:
    st.caption(f"Queued prompt: {prefilled_prompt}")

user_input = st.chat_input("Ask a regulatory question")
question = user_input or prefilled_prompt
if question:
    append_chat_message("user", question)
    with st.chat_message("user"):
        st.write(question)

    response_text, metadata = _compose_response(
        question=question,
        ticket=context_ticket,
        audit_setup=get_audit_setup(),
        analysis_response=analysis_response,
        prepared_answers=prepared_answers,
        mode=mode,
    )

    append_chat_message("assistant", response_text, metadata=metadata)
    with st.chat_message("assistant"):
        st.write(response_text)
        if metadata.get("fallback_used"):
            st.caption(FALLBACK_NOTICE)

        citation_validation = metadata.get("citation_validation")
        if _citation_warning_needed(citation_validation):
            st.warning("Citation review warning: verify cited references before relying on this response.")

        sources = metadata.get("sources") if isinstance(metadata.get("sources"), list) else []
        if sources:
            for index, source in enumerate(sources, start=1):
                if not isinstance(source, dict):
                    continue
                title = source.get("title") or source.get("provisionKey") or f"Source {index}"
                with st.expander(f"Source {index}: {title}", expanded=False):
                    st.write(f"Provision key: {source.get('provisionKey') or 'N/A'}")
                    st.write(f"Section: {source.get('sectionId') or source.get('section') or 'N/A'}")
                    raw_text = source.get("rawText") or source.get("text") or source.get("content")
                    if raw_text:
                        st.write(raw_text)

# Keep context controls visible for users that want to switch to a different gap context.
if gap_tickets:
    gap_ids = [str(item.get("gap_ticket_id")) for item in gap_tickets if item.get("gap_ticket_id")]
    if gap_ids:
        selected_context_id = st.selectbox(
            "Context gap ticket",
            options=["(none)"] + gap_ids,
            index=(gap_ids.index(context_ticket_id) + 1) if context_ticket_id in gap_ids else 0,
        )
        set_chat_context_gap_ticket_id(None if selected_context_id == "(none)" else selected_context_id)
