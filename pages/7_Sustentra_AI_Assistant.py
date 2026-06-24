from __future__ import annotations

import re
from typing import Any

import streamlit as st

from src.api import rag_client
from src.api.assistant_service import (
    answer_assistant_question,
    build_prepared_answers,
    current_chat_mode,
)
from src.ui.assistant_context import NOT_AVAILABLE_IN_CONTEXT, build_assistant_context
from src.ui.formatting import safe_text, sanitize_source_snippet
from src.ui.regulatory_assistant import parse_basis_clause
from src.ui.state import (
    append_chat_message,
    clear_chat_history,
    get_analysis_response,
    get_audit_setup,
    get_chat_context_gap_ticket_id,
    get_chat_history,
    get_created_gap_ticket_ids,
    get_gap_ticket_overrides,
    get_selected_calculation_id,
    get_selected_evidence_id,
    get_selected_validation_id,
    get_selected_workbook_location,
    init_session_state,
    set_chat_context_gap_ticket_id,
)


QUESTION_QUEUE_KEY = "selected_chat_question"
FORCE_REAL_RETRY_KEY = "assistant_force_real_retry"
_LEADING_ANSWER_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*(?:conclusion|answer|final answer|summary)\s*(?:\*\*|__)?\s*[:\-]?\s*(?:\n+)?",
    re.IGNORECASE,
)
INTERNAL_SUGGESTION_EXCLUSIONS = {
    "Which gaps are most important to show in the demo?",
}


def _display_text(value: Any) -> str:
    text = safe_text(value).strip()
    if not text:
        return NOT_AVAILABLE_IN_CONTEXT
    if text.lower().startswith("needs confirmation"):
        return NOT_AVAILABLE_IN_CONTEXT
    return text


def _find_ticket(gap_tickets: list[dict], ticket_id: str | None) -> dict | None:
    if not ticket_id:
        return None
    for ticket in gap_tickets:
        if not isinstance(ticket, dict):
            continue
        if safe_text(ticket.get("gap_ticket_id")).strip() == safe_text(ticket_id).strip():
            return ticket
    return None


def _ticket_title(ticket: dict) -> str:
    return (
        safe_text(ticket.get("auditor_title")).strip()
        or safe_text(ticket.get("title")).strip()
        or "Finding"
    )


def _visible_suggestions(chat_suggestions: list[dict]) -> list[str]:
    questions: list[str] = []
    for item in chat_suggestions:
        if not isinstance(item, dict):
            continue
        question = safe_text(item.get("question")).strip()
        if not question:
            continue
        if question in INTERNAL_SUGGESTION_EXCLUSIONS:
            continue
        if question not in questions:
            questions.append(question)
    return questions


def _queue_question(question: str, *, force_real: bool = False) -> None:
    st.session_state[QUESTION_QUEUE_KEY] = question
    if force_real:
        st.session_state[FORCE_REAL_RETRY_KEY] = True


def _pop_queued_question() -> tuple[str | None, bool]:
    queued = st.session_state.pop(QUESTION_QUEUE_KEY, None)
    force_real = bool(st.session_state.pop(FORCE_REAL_RETRY_KEY, False))
    if isinstance(queued, str) and queued.strip():
        return queued.strip(), force_real
    return None, force_real


def _last_user_question(history: list[dict]) -> str | None:
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if safe_text(item.get("role")).strip() != "user":
            continue
        content = safe_text(item.get("content")).strip()
        if content:
            return content
    return None


def _sanitize_diag_text(value: Any) -> str:
    text = safe_text(value).strip()
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"sk-[A-Za-z0-9._\-]+", "[REDACTED]", text)
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return text


def _strip_redundant_leading_heading(value: Any) -> str:
    text = safe_text(value).strip()
    if not text:
        return ""
    stripped = _LEADING_ANSWER_HEADING_RE.sub("", text, count=1).strip()
    return stripped or text


@st.cache_data(ttl=45, show_spinner=False)
def _cached_health_snapshot(cache_token: str) -> dict:
    try:
        payload = rag_client.check_rag_health()
        return {"ok": True, "category": "healthy", "message": "Service reachable", "payload": payload}
    except rag_client.RagApiError as exc:
        return {
            "ok": False,
            "category": "unhealthy",
            "message": _sanitize_diag_text(exc),
            "payload": {},
        }


def _citation_requires_review(citation_validation: Any) -> bool:
    if not isinstance(citation_validation, dict):
        return False
    status = safe_text(citation_validation.get("status")).strip().lower()
    if status in {"warning", "flagged", "fail", "invalid"}:
        return True
    if citation_validation.get("valid") is False:
        return True
    return bool(safe_text(citation_validation.get("warning")).strip())


def _normalize_sources(sources: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        title = (
            safe_text(source.get("title")).strip()
            or safe_text(source.get("provisionKey")).strip()
            or "Retrieved source"
        )
        authority = (
            safe_text(source.get("authority")).strip()
            or safe_text(source.get("regulation")).strip()
            or safe_text(source.get("jurisdiction")).strip()
        )
        citation = (
            safe_text(source.get("sectionId")).strip()
            or safe_text(source.get("section")).strip()
            or safe_text(source.get("citation")).strip()
            or safe_text(source.get("provisionKey")).strip()
        )
        excerpt = (
            safe_text(source.get("rawText")).strip()
            or safe_text(source.get("text")).strip()
            or safe_text(source.get("content")).strip()
            or safe_text(source.get("snippet")).strip()
        )
        url = (
            safe_text(source.get("source_url")).strip()
            or safe_text(source.get("url")).strip()
            or safe_text(source.get("link")).strip()
            or ""
        )

        rows.append(
            {
                "title": title,
                "authority": authority,
                "citation": citation,
                "excerpt": _display_text(sanitize_source_snippet(excerpt)) if excerpt else "",
                "url": url,
            }
        )
    return rows


def _context_evidence_lines(ticket: dict | None, assistant_context: dict) -> list[str]:
    lines: list[str] = []
    if isinstance(ticket, dict):
        gap_id = safe_text(ticket.get("gap_ticket_id")).strip()
        lines.append(f"Finding: {gap_id} - {_ticket_title(ticket)}")

        issue = ticket.get("issue") if isinstance(ticket.get("issue"), dict) else {}
        observed = _display_text(issue.get("observed_condition"))
        if observed != NOT_AVAILABLE_IN_CONTEXT:
            lines.append(f"Observed condition: {observed}")

        linked_evidence = ticket.get("linked_evidence") if isinstance(ticket.get("linked_evidence"), list) else []
        evidence_ids = [
            safe_text(item.get("evidence_id")).strip()
            for item in linked_evidence
            if isinstance(item, dict) and safe_text(item.get("evidence_id")).strip()
        ]
        if evidence_ids:
            lines.append("Evidence IDs: " + ", ".join(evidence_ids))

        linked_workbook = (
            ticket.get("linked_workbook_locations")
            if isinstance(ticket.get("linked_workbook_locations"), list)
            else []
        )
        workbook_refs = []
        for item in linked_workbook:
            if not isinstance(item, dict):
                continue
            sheet = safe_text(item.get("sheet_name")).strip()
            cell = safe_text(item.get("cell_or_range")).strip()
            if sheet and cell:
                workbook_refs.append(f"{sheet}!{cell}")
        if workbook_refs:
            lines.append("Workbook trace: " + ", ".join(workbook_refs))

    active_context = assistant_context.get("active_context") if isinstance(assistant_context.get("active_context"), dict) else {}
    selected_evidence_id = safe_text(active_context.get("active_evidence_id")).strip()
    selected_validation_id = safe_text(active_context.get("active_validation_id")).strip()
    selected_calculation_id = safe_text(active_context.get("active_calculation_id")).strip()

    if selected_evidence_id:
        lines.append(f"Selected evidence context: {selected_evidence_id}")
    if selected_validation_id:
        lines.append(f"Selected validation context: {selected_validation_id}")
    if selected_calculation_id:
        lines.append(f"Selected calculation context: {selected_calculation_id}")

    if not lines:
        lines.append(NOT_AVAILABLE_IN_CONTEXT)
    return lines


def _gap_citation_lines(ticket: dict | None) -> list[str]:
    if not isinstance(ticket, dict):
        return []
    basis = ticket.get("basis") if isinstance(ticket.get("basis"), dict) else {}
    citations = basis.get("regulatory_citations") if isinstance(basis.get("regulatory_citations"), list) else []
    rows: list[str] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        authority = safe_text(item.get("authority")).strip()
        citation = safe_text(item.get("citation")).strip()
        summary = safe_text(item.get("requirement_summary")).strip()
        prefix = " ".join(part for part in [authority, citation] if part).strip()
        if prefix and summary:
            rows.append(f"{prefix}: {summary}")
        elif prefix:
            rows.append(prefix)
    return rows


def _next_step(ticket: dict | None, provider: str) -> str:
    if isinstance(ticket, dict):
        remediation = ticket.get("remediation") if isinstance(ticket.get("remediation"), dict) else {}
        action = safe_text(remediation.get("recommended_action")).strip()
        if action:
            return action
    if provider == "sustentra_rag":
        return "Review the cited sources and align any auditor note with the retrieved regulatory basis."
    return "Review the linked finding context and select another reviewed question if additional support is needed."


def _build_sections(result: dict, ticket: dict | None, assistant_context: dict) -> dict:
    answer_text = _display_text(_strip_redundant_leading_heading(result.get("answer")))
    prepared_used = bool(result.get("prepared_answer_used"))
    provider = safe_text(result.get("provider")).strip()

    parsed_body, parsed_citations = parse_basis_clause(answer_text)
    if provider == "prepared_fallback" and prepared_used:
        conclusion = _display_text(_strip_redundant_leading_heading(parsed_body or answer_text))
        regulatory_basis = parsed_citations or _gap_citation_lines(ticket)
    else:
        conclusion = answer_text
        regulatory_basis = []

    sources = _normalize_sources(result.get("sources") if isinstance(result.get("sources"), list) else [])
    if provider == "sustentra_rag" and sources:
        for source in sources:
            authority = _display_text(source.get("authority"))
            citation = _display_text(source.get("citation"))
            if authority != NOT_AVAILABLE_IN_CONTEXT and citation != NOT_AVAILABLE_IN_CONTEXT:
                regulatory_basis.append(f"{authority} {citation}")
            elif citation != NOT_AVAILABLE_IN_CONTEXT:
                regulatory_basis.append(citation)

    if not regulatory_basis:
        regulatory_basis = _gap_citation_lines(ticket)

    return {
        "conclusion": conclusion,
        "evidence_context": _context_evidence_lines(ticket, assistant_context),
        "regulatory_basis": regulatory_basis,
        "next_step": _next_step(ticket, provider),
        "sources": sources,
    }


def _render_assistant_message(metadata: dict, fallback_content: str, key_prefix: str) -> None:
    provider_label = _display_text(metadata.get("provider_label"))
    st.caption(provider_label)

    if _citation_requires_review(metadata.get("citation_validation")):
        st.warning("Citation validation indicates this answer requires source review.")

    sections = metadata.get("sections") if isinstance(metadata.get("sections"), dict) else {}
    conclusion = _display_text(
        _strip_redundant_leading_heading(sections.get("conclusion") or fallback_content)
    )
    st.markdown(conclusion)

    evidence_context = (
        sections.get("evidence_context")
        if isinstance(sections.get("evidence_context"), list)
        else []
    )

    regulatory_basis = (
        sections.get("regulatory_basis")
        if isinstance(sections.get("regulatory_basis"), list)
        else []
    )

    sources = (
        sections.get("sources")
        if isinstance(sections.get("sources"), list)
        else []
    )

    with st.expander(
        "Evidence & context",
        expanded=False,
    ):
        if evidence_context:
            for line in evidence_context:
                st.markdown(
                    f"- {_display_text(line)}"
                )
        else:
            st.markdown(
                f"- {NOT_AVAILABLE_IN_CONTEXT}"
            )

    with st.expander(
        "Regulatory basis",
        expanded=False,
    ):
        if regulatory_basis:
            for line in regulatory_basis:
                st.markdown(
                    f"- {_display_text(line)}"
                )
        else:
            st.markdown(
                f"- {NOT_AVAILABLE_IN_CONTEXT}"
            )

    if sources:
        with st.expander(
            f"Sources ({len(sources)})",
            expanded=False,
        ):
            for index, source in enumerate(
                sources,
                start=1,
            ):
                if not isinstance(source, dict):
                    continue

                st.write(
                    f"{index}. "
                    f"{_display_text(source.get('title'))} — "
                    f"{_display_text(source.get('authority'))} "
                    f"{_display_text(source.get('citation'))}"
                )

                excerpt = _display_text(
                    source.get("excerpt")
                )

                if excerpt != NOT_AVAILABLE_IN_CONTEXT:
                    st.caption(excerpt)

                url = safe_text(
                    source.get("url")
                ).strip()

                if url:
                    st.link_button(
                        "Open source link",
                        url,
                    )

    st.markdown(
        "**Next step:** "
        f"{_display_text(sections.get('next_step'))}"
    )

    error_code = safe_text(metadata.get("error_code")).strip()
    error_message = safe_text(metadata.get("error_message")).strip()
    if error_code and error_message:
        st.caption(f"Diagnostic: {error_code} ({error_message})")


init_session_state()

st.title("Sustentra AI Assistant")
st.caption("Source-backed audit research · not legal advice")

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No analysis is loaded. Open Evidence Intake and run the workflow to continue.")
    st.stop()

audit_setup = get_audit_setup()
gap_tickets = [item for item in (analysis_response.get("gap_tickets") or []) if isinstance(item, dict)]
chat_suggestions = [item for item in (analysis_response.get("chat_suggestions") or []) if isinstance(item, dict)]
prepared_answers = build_prepared_answers(chat_suggestions)

current_mode = current_chat_mode()
rag_configured = rag_client.has_rag_configuration()
health_snapshot = {"ok": False, "category": "skipped", "message": "Health check skipped."}
if current_mode != "prepared" and rag_configured:
    health_snapshot = _cached_health_snapshot(f"{current_mode}:configured")

with st.sidebar:
    st.markdown("### Context")

    current_gap_id = get_chat_context_gap_ticket_id()

    if (
        current_gap_id
        and _find_ticket(gap_tickets, current_gap_id) is None
    ):
        set_chat_context_gap_ticket_id(None)
        current_gap_id = None

    if gap_tickets:
        labels = ["(none)"]
        label_to_id = {"(none)": None}

        for ticket in gap_tickets:
            gap_id = safe_text(
                ticket.get("gap_ticket_id")
            ).strip()

            if not gap_id:
                continue

            label = f"{_ticket_title(ticket)} ({gap_id})"
            labels.append(label)
            label_to_id[label] = gap_id

        selected_label = "(none)"

        if current_gap_id:
            for label, gap_id in label_to_id.items():
                if gap_id == current_gap_id:
                    selected_label = label
                    break

        selected_label = st.selectbox(
            "Selected finding",
            options=labels,
            index=labels.index(selected_label),
        )

        selected_gap_id = label_to_id.get(selected_label)

        if selected_gap_id != current_gap_id:
            set_chat_context_gap_ticket_id(selected_gap_id)
            current_gap_id = selected_gap_id

    context_ticket = _find_ticket(
        gap_tickets,
        current_gap_id,
    )

    latest_provider = ""

    for item in reversed(get_chat_history()):
        if not isinstance(item, dict):
            continue

        if safe_text(item.get("role")).strip() != "assistant":
            continue

        metadata = (
            item.get("metadata")
            if isinstance(item.get("metadata"), dict)
            else {}
        )

        if metadata:
            latest_provider = safe_text(
                metadata.get("provider")
            ).strip()
            break

    if (
        latest_provider == "sustentra_rag"
        or (
            current_mode != "prepared"
            and rag_configured
            and health_snapshot.get("ok")
        )
    ):
        status_md = ":green[Live source-backed]"
    else:
        status_md = ":orange[Prepared fallback]"

    profile = (
        audit_setup.get("company_and_facility_profile")
        if isinstance(
            audit_setup.get("company_and_facility_profile"),
            dict,
        )
        else {}
    )

    facility_label = _display_text(
        profile.get("facility_name")
    )
    period_label = _display_text(
        profile.get("reporting_period")
    )

    selected_evidence_id = get_selected_evidence_id()
    selected_validation_id = get_selected_validation_id()
    selected_calculation_id = get_selected_calculation_id()
    selected_workbook_location = (
        get_selected_workbook_location()
    )

    workbook_label = NOT_AVAILABLE_IN_CONTEXT

    if isinstance(selected_workbook_location, dict):
        sheet = safe_text(
            selected_workbook_location.get("sheet_name")
        ).strip()
        cell = safe_text(
            selected_workbook_location.get("cell_or_range")
        ).strip()

        if sheet and cell:
            workbook_label = f"{sheet}!{cell}"

    st.caption(f"Facility · {facility_label}")
    st.caption(f"Period · {period_label}")

    if _display_text(selected_evidence_id) != NOT_AVAILABLE_IN_CONTEXT:
        st.caption(
            "Evidence · "
            f"{_display_text(selected_evidence_id)}"
        )

    if _display_text(selected_validation_id) != NOT_AVAILABLE_IN_CONTEXT:
        st.caption(
            "Validation · "
            f"{_display_text(selected_validation_id)}"
        )

    if _display_text(selected_calculation_id) != NOT_AVAILABLE_IN_CONTEXT:
        st.caption(
            "Calculation · "
            f"{_display_text(selected_calculation_id)}"
        )

    if workbook_label != NOT_AVAILABLE_IN_CONTEXT:
        st.caption(f"Workbook · {workbook_label}")

    if isinstance(context_ticket, dict):
        st.caption(
            "Finding · "
            f"{_display_text(context_ticket.get('gap_ticket_id'))}"
        )

    st.markdown(f"Status · {status_md}")
    st.divider()
    st.markdown("##### Session")

    if st.button(
        "Retry on live service",
        use_container_width=True,
    ):
        last_question = _last_user_question(
            get_chat_history()
        )

        if last_question:
            _queue_question(
                last_question,
                force_real=True,
            )
        else:
            st.info("No previous question to retry.")

    if st.button(
        "Clear conversation",
        use_container_width=True,
    ):
        clear_chat_history()

    if st.button(
        "Remove finding context",
        use_container_width=True,
    ):
        set_chat_context_gap_ticket_id(None)

if isinstance(context_ticket, dict):
    context_gap_id = _display_text(context_ticket.get("gap_ticket_id"))
    context_title = _ticket_title(context_ticket)

    qa_cols = st.columns(
        [1, 1, 1, 0.6],
        gap="small",
    )

    if qa_cols[0].button(
        "Explain finding",
        use_container_width=True,
    ):
        _queue_question(f"Explain this finding in auditor terms: {context_gap_id} - {context_title}.")

    if qa_cols[1].button(
        "Evidence trace",
        use_container_width=True,
    ):
        _queue_question(f"Show the evidence and workbook trace for {context_gap_id}.")

    if qa_cols[2].button(
        "Regulatory basis",
        use_container_width=True,
    ):
        _queue_question(f"Explain the regulatory basis for finding {context_gap_id}.")

    popover = getattr(st, "popover", None)

    with qa_cols[3]:
        more_context = (
            popover("More")
            if callable(popover)
            else st.expander("More")
        )

    with more_context:
        if st.button("Draft auditor note", use_container_width=True):
            _queue_question(f"Draft an auditor note for {context_gap_id}.")

suggested_questions = _visible_suggestions(chat_suggestions)
if suggested_questions:
    with st.expander(
        "Suggested questions",
        expanded=False,
    ):
        for idx, question in enumerate(
            suggested_questions
        ):
            if st.button(question, key=f"suggested_question_{idx}", use_container_width=True):
                _queue_question(question)

history = get_chat_history()
for idx, message in enumerate(history):
    role = _display_text(message.get("role") if isinstance(message, dict) else "assistant")
    content = _display_text(message.get("content") if isinstance(message, dict) else "")
    metadata = message.get("metadata") if isinstance(message, dict) and isinstance(message.get("metadata"), dict) else {}

    with st.chat_message(role if role in {"user", "assistant", "system"} else "assistant"):
        if role != "assistant":
            st.markdown(content)
            continue
        _render_assistant_message(metadata, content, key_prefix=f"history_{idx}")

queued_question, force_real_retry = _pop_queued_question()
user_input = st.chat_input("Ask a source-backed audit question")

question_to_ask = None
if isinstance(user_input, str) and user_input.strip():
    question_to_ask = user_input.strip()
elif queued_question:
    question_to_ask = queued_question

if question_to_ask:
    append_chat_message("user", question_to_ask)
    with st.chat_message("user"):
        st.markdown(question_to_ask)

    context_payload = build_assistant_context(
        analysis_response=analysis_response,
        audit_setup=audit_setup,
        selected_gap_ticket_id=current_gap_id,
        reviewed_extraction_fields=st.session_state.get("reviewed_extraction_fields", {}),
        created_gap_ticket_ids=get_created_gap_ticket_ids(),
        gap_ticket_overrides=get_gap_ticket_overrides(),
        active_selection={
            "selected_evidence_id": selected_evidence_id,
            "selected_validation_id": selected_validation_id,
            "selected_calculation_id": selected_calculation_id,
            "selected_workbook_location": selected_workbook_location,
        },
    )

    mode_for_request = "real" if force_real_retry else current_mode
    result = answer_assistant_question(
        question=question_to_ask,
        context=context_payload,
        prepared_answers=prepared_answers,
        mode=mode_for_request,
    )
    sections = _build_sections(result, context_ticket, context_payload)

    metadata = {
        "provider": result.get("provider"),
        "provider_label": result.get("provider_label"),
        "mode_used": result.get("mode_used"),
        "live_attempted": bool(result.get("live_attempted")),
        "fallback_used": bool(result.get("fallback_used")),
        "prepared_answer_used": bool(result.get("prepared_answer_used")),
        "error_code": result.get("error_code"),
        "error_message": _sanitize_diag_text(result.get("error_message")),
        "citation_validation": result.get("citation_validation"),
        "sources": result.get("sources") if isinstance(result.get("sources"), list) else [],
        "context_size_chars": (context_payload.get("included_counts") or {}).get("context_size_chars"),
        "context_truncated": bool(context_payload.get("truncated")),
        "sections": sections,
    }

    assistant_text = _display_text(result.get("answer"))
    append_chat_message("assistant", assistant_text, metadata=metadata)
    with st.chat_message("assistant"):
        _render_assistant_message(metadata, assistant_text, key_prefix="latest")

latest_history = get_chat_history()
latest_assistant_meta: dict[str, Any] = {}
for item in reversed(latest_history):
    if not isinstance(item, dict):
        continue
    if safe_text(item.get("role")).strip() != "assistant":
        continue
    maybe_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if maybe_metadata:
        latest_assistant_meta = maybe_metadata
        break

with st.expander("Assistant diagnostics", expanded=False):
    st.write(f"Configured: {'yes' if rag_configured else 'no'}")
    st.write(f"Selected mode: {current_mode}")
    st.write(f"Last provider: {_display_text(latest_assistant_meta.get('provider_label'))}")
    st.write(f"Last status category: {_display_text(latest_assistant_meta.get('error_code'))}")
    st.write(f"Context size: {_display_text(latest_assistant_meta.get('context_size_chars'))}")
    st.write(f"Context truncated: {'yes' if latest_assistant_meta.get('context_truncated') else 'no'}")
    sources_count = len(latest_assistant_meta.get("sources") or []) if isinstance(latest_assistant_meta.get("sources"), list) else 0
    st.write(f"Returned sources: {sources_count}")
    st.write(f"Health status: {_display_text(health_snapshot.get('category'))}")
    st.write(f"Health detail: {_display_text(health_snapshot.get('message'))}")
