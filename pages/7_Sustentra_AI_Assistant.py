from __future__ import annotations

import streamlit as st

from src.ui.formatting import safe_text, sanitize_source_snippet
from src.ui.regulatory_assistant import (
    GAP010_REVIEW_NOTICE,
    UNKNOWN_REVIEWED_SET_MESSAGE,
    build_audit_context_lines,
    parse_basis_clause,
    resolve_curated_answer,
)
from src.ui.state import (
    append_chat_message,
    get_analysis_response,
    get_audit_setup,
    get_chat_context_gap_ticket_id,
    get_chat_history,
    init_session_state,
    open_original_evidence,
    set_chat_context_gap_ticket_id,
    set_selected_gap_ticket_id,
)


PREFERRED_VISIBLE_QUESTIONS = [
    "Can we accept a biomass-derived CO2 classification based only on an invoice line item and a marketing certificate?",
    "Is total fuel quantity alone enough for Part 253 reporting, or do we need supplier account information?",
    "If a facility reports 9,650 MT CO2e from boilers but excludes a 620 MT hydrogen fuel cell, is it below the 10,000 MT reporting threshold?",
]

REGULATION_CONTEXT_STATE_KEY = "assistant_selected_regulation_context"


def _find_ticket(gap_tickets: list[dict], ticket_id: str | None) -> dict | None:
    if not ticket_id:
        return None
    for ticket in gap_tickets:
        if not isinstance(ticket, dict):
            continue
        if str(ticket.get("gap_ticket_id") or "") == str(ticket_id):
            return ticket
    return None


def _find_evidence_record(evidence_results: list[dict], evidence_id: str) -> dict | None:
    for record in evidence_results:
        if not isinstance(record, dict):
            continue
        if str(record.get("evidence_id") or "") == evidence_id:
            return record
    return None


def _resolve_evidence_title(evidence_record: dict | None, evidence_ref: dict) -> str:
    if isinstance(evidence_record, dict):
        document_type = safe_text(evidence_record.get("document_type")).strip()
        if document_type:
            return document_type
        file_name = safe_text(evidence_record.get("file_name")).strip()
        if file_name:
            return file_name
    return safe_text(evidence_ref.get("evidence_id") or "Evidence record")


def _build_evidence_refs(ticket: dict | None, evidence_results: list[dict]) -> list[dict]:
    if not isinstance(ticket, dict):
        return []

    linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
    rows: list[dict] = []

    for item in linked_evidence:
        if not isinstance(item, dict):
            continue
        evidence_id = safe_text(item.get("evidence_id")).strip()
        if not evidence_id:
            continue

        evidence_record = _find_evidence_record(evidence_results, evidence_id)
        source_locations = item.get("source_locations") if isinstance(item.get("source_locations"), list) else []
        first_source = source_locations[0] if source_locations and isinstance(source_locations[0], dict) else {}
        page_number = first_source.get("page_number")
        snippet = sanitize_source_snippet(first_source.get("source_snippet"))

        rows.append(
            {
                "evidence_id": evidence_id,
                "title": _resolve_evidence_title(evidence_record, item),
                "page_number": page_number,
                "snippet": snippet,
                "relationship": safe_text(item.get("relationship_to_gap")).replace("_", " ").strip(),
            }
        )

    return rows


def _build_workbook_refs(ticket: dict | None) -> list[str]:
    if not isinstance(ticket, dict):
        return []
    linked = (
        ticket.get("linked_workbook_locations")
        if isinstance(ticket.get("linked_workbook_locations"), list)
        else []
    )
    rows: list[str] = []
    for item in linked:
        if not isinstance(item, dict):
            continue
        sheet = safe_text(item.get("sheet_name")).strip()
        cell = safe_text(item.get("cell_or_range")).strip()
        if sheet and cell:
            rows.append(f"{sheet}!{cell}")
    return rows


def _normalize_citation_row(item: dict, *, context_gap_id: str | None) -> dict:
    authority = safe_text(item.get("authority")).strip()
    citation = safe_text(item.get("citation")).strip()
    requirement = safe_text(item.get("requirement_summary")).strip()
    applicability = safe_text(item.get("applicability_explanation")).strip()
    source_url = safe_text(item.get("source_url")).strip() or None

    if context_gap_id == "GT-DEMO-GAP-010":
        requirement = "Interpretation under source review."
        applicability = "Not included in the verified assistant knowledge set."

    return {
        "authority": authority,
        "citation": citation,
        "requirement_summary": requirement,
        "applicability_explanation": applicability,
        "source_url": source_url,
    }


def _build_ticket_citations(ticket: dict | None) -> list[dict]:
    if not isinstance(ticket, dict):
        return []
    context_gap_id = safe_text(ticket.get("gap_ticket_id")).strip()
    basis = ticket.get("basis") if isinstance(ticket.get("basis"), dict) else {}
    citations = basis.get("regulatory_citations") if isinstance(basis.get("regulatory_citations"), list) else []

    rows: list[dict] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        rows.append(_normalize_citation_row(item, context_gap_id=context_gap_id))
    return rows


def _build_basis_citations_for_unscoped_answer(citations: list[str]) -> list[dict]:
    rows: list[dict] = []
    for citation in citations:
        clean = safe_text(citation).strip()
        if not clean:
            continue
        rows.append(
            {
                "authority": "Reviewed basis",
                "citation": clean,
                "requirement_summary": "",
                "applicability_explanation": "",
                "source_url": None,
            }
        )
    return rows


def _set_regulation_context(citation: dict) -> None:
    st.session_state[REGULATION_CONTEXT_STATE_KEY] = citation


def _render_regulation_context_panel(context_ticket: dict | None) -> None:
    selected = st.session_state.get(REGULATION_CONTEXT_STATE_KEY)
    if not isinstance(selected, dict):
        return

    authority = safe_text(selected.get("authority")).strip()
    citation = safe_text(selected.get("citation")).strip()
    summary = safe_text(selected.get("requirement_summary")).strip()
    applicability = safe_text(selected.get("applicability_explanation")).strip()
    source_url = safe_text(selected.get("source_url")).strip()

    st.markdown("### Regulation context")
    with st.container(border=True):
        heading = " ".join([part for part in [authority, citation] if part]).strip()
        if heading:
            st.markdown(f"**{heading}**")
        if summary:
            st.write(summary)
        if applicability:
            st.caption(f"Applicability: {applicability}")

        action_cols = st.columns(2)
        if source_url:
            action_cols[0].link_button("Open source link", source_url, use_container_width=True)
        if isinstance(context_ticket, dict):
            gap_id = safe_text(context_ticket.get("gap_ticket_id")).strip()
            if gap_id and action_cols[1].button("Back to finding", key="reg_context_back_to_finding", use_container_width=True):
                set_selected_gap_ticket_id(gap_id)
                switch_page = getattr(st, "switch_page", None)
                if callable(switch_page):
                    switch_page("pages/6_Gap_Analysis.py")
                else:
                    st.info("Open Gap Analysis from the sidebar.")


def _render_citation_rows(citations: list[dict], key_prefix: str) -> None:
    for index, citation in enumerate(citations):
        authority = safe_text(citation.get("authority")).strip()
        citation_code = safe_text(citation.get("citation")).strip()
        summary = safe_text(citation.get("requirement_summary")).strip()
        applicability = safe_text(citation.get("applicability_explanation")).strip()
        source_url = safe_text(citation.get("source_url")).strip()

        with st.container(border=True):
            header = " ".join([part for part in [authority, citation_code] if part]).strip()
            if header:
                st.markdown(f"**{header}**")
            if summary:
                st.write(summary)
            if applicability:
                st.caption(f"Applicability: {applicability}")

            control_cols = st.columns(2)
            if control_cols[0].button(
                "View regulation context",
                key=f"{key_prefix}_view_regulation_{index}",
                use_container_width=True,
            ):
                _set_regulation_context(citation)
            if source_url:
                control_cols[1].link_button(
                    "Open source link",
                    source_url,
                    use_container_width=True,
                )


def _build_structured_response(
    question: str,
    chat_suggestions: list[dict],
    context_ticket: dict | None,
    analysis_response: dict,
    audit_setup: dict,
) -> dict:
    curated_answer = resolve_curated_answer(chat_suggestions, question)
    direct_answer = UNKNOWN_REVIEWED_SET_MESSAGE if curated_answer is None else curated_answer

    body_text, parsed_basis_citations = parse_basis_clause(direct_answer)
    if curated_answer is None:
        body_text = UNKNOWN_REVIEWED_SET_MESSAGE
        parsed_basis_citations = []

    context_gap_id = safe_text(context_ticket.get("gap_ticket_id")) if isinstance(context_ticket, dict) else ""
    context_gap_id = context_gap_id.strip()
    if context_gap_id == "GT-DEMO-GAP-010":
        body_text = GAP010_REVIEW_NOTICE

    evidence_results = [item for item in (analysis_response.get("evidence_results") or []) if isinstance(item, dict)]
    evidence_refs = _build_evidence_refs(context_ticket, evidence_results)
    workbook_refs = _build_workbook_refs(context_ticket)

    if isinstance(context_ticket, dict):
        regulatory_citations = _build_ticket_citations(context_ticket)
    else:
        regulatory_citations = _build_basis_citations_for_unscoped_answer(parsed_basis_citations)

    issue_text = ""
    if isinstance(context_ticket, dict):
        issue = context_ticket.get("issue") if isinstance(context_ticket.get("issue"), dict) else {}
        issue_text = safe_text(issue.get("observed_condition")).strip()

    audit_context_lines = build_audit_context_lines(audit_setup, analysis_response)

    next_actions: list[dict] = []
    if evidence_refs:
        next_actions.append(
            {
                "action": "open_source_evidence",
                "label": "Open source evidence",
                "evidence_id": evidence_refs[0].get("evidence_id"),
            }
        )
    if regulatory_citations:
        next_actions.append(
            {
                "action": "view_regulation_context",
                "label": "View regulation context",
                "citation_index": 0,
            }
        )
    if not next_actions and isinstance(context_ticket, dict):
        next_actions.append(
            {
                "action": "back_to_finding",
                "label": "Back to finding",
                "gap_ticket_id": context_gap_id,
            }
        )
    next_actions = next_actions[:2]

    return {
        "question": question,
        "direct_answer": body_text,
        "issue": issue_text,
        "evidence_refs": evidence_refs,
        "workbook_refs": workbook_refs,
        "audit_context_lines": audit_context_lines,
        "regulatory_citations": regulatory_citations,
        "next_actions": next_actions,
        "context_gap_ticket_id": context_gap_id or None,
    }


def _render_structured_assistant_message(structured: dict, key_prefix: str) -> None:
    st.markdown("**Answer**")
    with st.container(border=True):
        st.markdown(safe_text(structured.get("direct_answer")))
        issue_text = safe_text(structured.get("issue")).strip()
        if issue_text:
            st.caption(f"Finding context: {issue_text}")

    evidence_refs = structured.get("evidence_refs") if isinstance(structured.get("evidence_refs"), list) else []
    workbook_refs = structured.get("workbook_refs") if isinstance(structured.get("workbook_refs"), list) else []
    if evidence_refs or workbook_refs:
        st.markdown("**Evidence trace**")
        with st.container(border=True):
            for index, item in enumerate(evidence_refs):
                if not isinstance(item, dict):
                    continue
                title = safe_text(item.get("title")).strip() or "Evidence"
                page_number = item.get("page_number")
                snippet = safe_text(item.get("snippet")).strip()
                relationship = safe_text(item.get("relationship")).strip()
                evidence_id = safe_text(item.get("evidence_id")).strip()

                row_col_left, row_col_right = st.columns([5, 2])
                with row_col_left:
                    st.markdown(f"**{title}**")
                    detail_bits = []
                    if relationship:
                        detail_bits.append(relationship)
                    if page_number is not None:
                        detail_bits.append(f"Page {page_number}")
                    if detail_bits:
                        st.caption(" | ".join(detail_bits))
                    if snippet:
                        st.caption(snippet)
                with row_col_right:
                    if evidence_id:
                        st.button(
                            "Open source evidence",
                            key=f"{key_prefix}_open_source_evidence_{index}",
                            use_container_width=True,
                            on_click=open_original_evidence,
                            args=(evidence_id,),
                        )

            if workbook_refs:
                st.caption("Workbook references: " + ", ".join(workbook_refs))

    audit_context_lines = (
        structured.get("audit_context_lines") if isinstance(structured.get("audit_context_lines"), list) else []
    )
    if audit_context_lines:
        st.markdown("**Audit context**")
        with st.container(border=True):
            for line in audit_context_lines:
                if isinstance(line, str) and line.strip():
                    st.markdown(line)

    regulatory_citations = (
        structured.get("regulatory_citations")
        if isinstance(structured.get("regulatory_citations"), list)
        else []
    )
    if regulatory_citations:
        st.markdown("**Regulatory basis**")
        _render_citation_rows(regulatory_citations, key_prefix=key_prefix)

    next_actions = structured.get("next_actions") if isinstance(structured.get("next_actions"), list) else []
    if next_actions:
        st.markdown("**Next action**")
        with st.container(border=True):
            for action_index, action in enumerate(next_actions):
                if not isinstance(action, dict):
                    continue
                action_type = safe_text(action.get("action")).strip()
                label = safe_text(action.get("label")).strip()
                if not action_type or not label:
                    continue

                if action_type == "open_source_evidence":
                    evidence_id = safe_text(action.get("evidence_id")).strip()
                    if evidence_id:
                        st.button(
                            label,
                            key=f"{key_prefix}_next_open_evidence_{action_index}",
                            use_container_width=True,
                            on_click=open_original_evidence,
                            args=(evidence_id,),
                        )
                elif action_type == "view_regulation_context":
                    citation_index = int(action.get("citation_index") or 0)
                    citations = (
                        structured.get("regulatory_citations")
                        if isinstance(structured.get("regulatory_citations"), list)
                        else []
                    )
                    if 0 <= citation_index < len(citations):
                        citation = citations[citation_index]
                        if isinstance(citation, dict) and st.button(
                            label,
                            key=f"{key_prefix}_next_view_regulation_{action_index}",
                            use_container_width=True,
                        ):
                            _set_regulation_context(citation)
                elif action_type == "back_to_finding":
                    gap_ticket_id = safe_text(action.get("gap_ticket_id")).strip()
                    if gap_ticket_id and st.button(
                        label,
                        key=f"{key_prefix}_next_back_to_finding_{action_index}",
                        use_container_width=True,
                    ):
                        set_selected_gap_ticket_id(gap_ticket_id)
                        switch_page = getattr(st, "switch_page", None)
                        if callable(switch_page):
                            switch_page("pages/6_Gap_Analysis.py")
                        else:
                            st.info("Open Gap Analysis from the sidebar.")


def _ordered_question_list(chat_suggestions: list[dict]) -> list[str]:
    suggestions = [
        safe_text(item.get("question")).strip()
        for item in chat_suggestions
        if isinstance(item, dict) and safe_text(item.get("question")).strip()
    ]
    visible: list[str] = []

    for preferred in PREFERRED_VISIBLE_QUESTIONS:
        if preferred in suggestions and preferred not in visible:
            visible.append(preferred)

    for question in suggestions:
        if question not in visible and len(visible) < 3:
            visible.append(question)

    remaining = [question for question in suggestions if question not in visible]
    return visible + remaining


init_session_state()
st.title("Sustentra AI Assistant")
st.caption("Sustentra AI Assistant supports regulatory research and audit documentation. It does not provide legal advice.")

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No analysis is loaded. Open Evidence Intake and run the workflow to continue.")
    st.stop()

gap_tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
chat_suggestions = [item for item in (analysis_response.get("chat_suggestions") or []) if isinstance(item, dict)]

context_ticket_id = get_chat_context_gap_ticket_id()
context_ticket = _find_ticket(gap_tickets, context_ticket_id)
if context_ticket_id and context_ticket is None:
    set_chat_context_gap_ticket_id(None)

if isinstance(context_ticket, dict):
    context_gap_id = safe_text(context_ticket.get("gap_ticket_id")).strip()
    context_title = safe_text(context_ticket.get("title")).strip() or "Finding"
    context_issue = context_ticket.get("issue") if isinstance(context_ticket.get("issue"), dict) else {}
    context_issue_text = safe_text(context_issue.get("observed_condition")).strip()

    context_evidence_refs = _build_evidence_refs(
        context_ticket,
        [item for item in (analysis_response.get("evidence_results") or []) if isinstance(item, dict)],
    )
    context_citations = _build_ticket_citations(context_ticket)

    st.markdown("### Context finding")
    with st.container(border=True):
        st.markdown(f"**{context_title}**")
        if context_issue_text:
            st.caption(context_issue_text)

        control_labels: list[tuple[str, str]] = []
        if context_evidence_refs:
            control_labels.append(("open_evidence", "Open source evidence"))
        if context_citations:
            control_labels.append(("view_regulation", "View regulation context"))
        if context_gap_id:
            control_labels.append(("back_to_finding", "Back to finding"))

        if control_labels:
            controls = st.columns(len(control_labels))
            for idx, (action_key, label) in enumerate(control_labels):
                if action_key == "open_evidence":
                    first_id = safe_text(context_evidence_refs[0].get("evidence_id")).strip()
                    controls[idx].button(
                        label,
                        key="context_open_source_evidence",
                        use_container_width=True,
                        on_click=open_original_evidence,
                        args=(first_id,),
                    )
                elif action_key == "view_regulation":
                    if controls[idx].button(
                        label,
                        key="context_view_regulation",
                        use_container_width=True,
                    ):
                        _set_regulation_context(context_citations[0])
                elif action_key == "back_to_finding":
                    if controls[idx].button(
                        label,
                        key="context_back_to_finding",
                        use_container_width=True,
                    ):
                        set_selected_gap_ticket_id(context_gap_id)
                        switch_page = getattr(st, "switch_page", None)
                        if callable(switch_page):
                            switch_page("pages/6_Gap_Analysis.py")
                        else:
                            st.info("Open Gap Analysis from the sidebar.")

ordered_questions = _ordered_question_list(chat_suggestions)
visible_questions = ordered_questions[:3]
more_questions = ordered_questions[3:]

queued_question: str | None = None

if visible_questions:
    st.markdown("### Reviewed questions")
    for index, question in enumerate(visible_questions):
        if st.button(question, key=f"visible_reviewed_question_{index}", use_container_width=True):
            queued_question = question

if more_questions:
    with st.expander("More reviewed questions", expanded=False):
        for index, question in enumerate(more_questions):
            if st.button(question, key=f"more_reviewed_question_{index}", use_container_width=True):
                queued_question = question

selected_chat_question = st.session_state.pop("selected_chat_question", None)
if queued_question is None and isinstance(selected_chat_question, str) and selected_chat_question.strip():
    queued_question = selected_chat_question.strip()

history = get_chat_history()
for idx, message in enumerate(history):
    role = safe_text(message.get("role")).strip() or "assistant"
    content = safe_text(message.get("content"))
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}

    with st.chat_message(role):
        if role != "assistant":
            st.markdown(content)
            continue

        structured = metadata.get("structured_response") if isinstance(metadata.get("structured_response"), dict) else None
        if isinstance(structured, dict):
            _render_structured_assistant_message(structured, key_prefix=f"history_{idx}")
        else:
            st.markdown(content)

user_input = st.chat_input("Ask a question from the verified regulatory set")
question = queued_question or user_input

if isinstance(question, str) and question.strip():
    final_question = question.strip()
    append_chat_message("user", final_question)
    with st.chat_message("user"):
        st.markdown(final_question)

    structured_response = _build_structured_response(
        question=final_question,
        chat_suggestions=chat_suggestions,
        context_ticket=context_ticket,
        analysis_response=analysis_response,
        audit_setup=get_audit_setup(),
    )

    append_chat_message(
        "assistant",
        safe_text(structured_response.get("direct_answer")),
        metadata={"structured_response": structured_response},
    )
    with st.chat_message("assistant"):
        _render_structured_assistant_message(structured_response, key_prefix="latest")

if gap_tickets:
    gap_ids = [safe_text(item.get("gap_ticket_id")).strip() for item in gap_tickets if safe_text(item.get("gap_ticket_id")).strip()]
    if gap_ids:
        selected_context_id = st.selectbox(
            "Context finding",
            options=["(none)"] + gap_ids,
            index=(gap_ids.index(context_ticket_id) + 1) if context_ticket_id in gap_ids else 0,
        )
        set_chat_context_gap_ticket_id(None if selected_context_id == "(none)" else selected_context_id)

_render_regulation_context_panel(context_ticket)
