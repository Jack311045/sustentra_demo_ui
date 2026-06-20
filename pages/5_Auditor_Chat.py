from __future__ import annotations

import os

import streamlit as st

from src.api.rag_client import RagApiError, check_rag_health, query_rag
from src.ui.state import get_analysis_response, init_session_state


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


def _severity_rank(label: str) -> int:
	ranking = {"critical": 0, "high": 1, "medium": 2, "low": 3}
	return ranking.get(label.lower(), 4)


def _source_field(source: dict, *keys: str) -> str:
	for key in keys:
		value = source.get(key)
		if value not in (None, ""):
			return str(value)
	return "N/A"


def _render_mock_mode(question_to_answer: dict[str, str]) -> None:
	questions = list(question_to_answer.keys())

	if questions:
		previous_question = st.session_state.get("selected_chat_question")
		if previous_question not in questions:
			previous_question = questions[0]

		selected_question = st.selectbox(
			"Prepared demo questions",
			options=questions,
			index=questions.index(previous_question),
		)
		st.session_state["selected_chat_question"] = selected_question

		st.markdown("**Mock answer**")
		st.write(question_to_answer.get(selected_question) or "No mock answer available.")
	else:
		st.info("No prepared chat suggestions are available in the current mock response.")

	typed_question = st.text_input("Ask a question (mock mode only)")
	if typed_question:
		if typed_question in question_to_answer:
			st.markdown("**Mock answer**")
			st.write(question_to_answer[typed_question])
		else:
			st.warning("Mock chat mode only: please select one of the prepared demo questions.")


def _render_rag_mode(gap_tickets: list[dict]) -> None:
	st.caption("Real NY Part 253 RAG query mode. This mode calls Claire's regulatory RAG API.")

	if st.button("Check RAG health"):
		try:
			health = check_rag_health()
			st.success("RAG health check succeeded.")
			st.json(health)
		except RagApiError as exc:
			st.error(str(exc))

	if not os.getenv("RAG_API_KEY", "").strip():
		st.warning("RAG_API_KEY is missing. Set it in your environment to use real RAG query mode.")

	question = st.text_area(
		"Regulatory question",
		placeholder="Ask a NY Part 253 compliance question for this audit context...",
	)

	if st.button("Ask NY Part 253 RAG", type="primary"):
		if not question.strip():
			st.warning("Please enter a regulatory question.")
		else:
			audit_context = {
				"jurisdiction": "NY",
				"entity_type": "facility owner or operator",
				"audit_scope": "compliance review",
				"reporting_period_end": "2026-12-31",
				"findings_count": len(gap_tickets),
			}

			try:
				with st.spinner("Querying NY Part 253 RAG..."):
					rag_result = query_rag(question=question, audit_context=audit_context)

				st.markdown("**Final answer**")
				st.write(rag_result.get("answer") or "No answer returned.")
				st.write(f"**Audit query ID:** {rag_result.get('audit_query_id') or 'N/A'}")

				sources = rag_result.get("sources") or []
				if sources:
					st.markdown("**Sources**")
					for index, source in enumerate(sources, start=1):
						if not isinstance(source, dict):
							continue

						provision_key = _source_field(
							source,
							"provisionKey",
							"provision_key",
							"key",
						)
						title = _source_field(source, "title", "name", "provisionTitle")
						section_id = _source_field(source, "sectionId", "section_id", "section")
						raw_text = _source_field(
							source,
							"rawText",
							"raw_text",
							"text",
							"content",
							"snippet",
						)

						with st.expander(f"Source {index}: {title if title != 'N/A' else provision_key}"):
							st.write(f"**Provision key:** {provision_key}")
							st.write(f"**Title:** {title}")
							st.write(f"**Section ID:** {section_id}")
							st.write("**Raw text:**")
							st.write(raw_text)

				citation_validation = rag_result.get("citation_validation")
				if citation_validation is not None:
					st.markdown("**Citation validation**")
					st.json(citation_validation)

				progress = rag_result.get("progress_messages") or []
				if progress:
					with st.expander("Progress events"):
						for message in progress:
							st.write(f"- {message}")

			except RagApiError as exc:
				st.error(str(exc))

	st.info("This system assists regulatory research and does not provide legal advice.")


init_session_state()

st.title("Auditor Chat")

analysis_response = get_analysis_response()
if not analysis_response:
	st.info(NO_ANALYSIS_MESSAGE)
	st.stop()

suggestions = [s for s in (analysis_response.get("chat_suggestions") or []) if isinstance(s, dict)]
question_to_answer = {
	str(item.get("question")): str(item.get("mock_answer") or "")
	for item in suggestions
	if item.get("question")
}

gap_tickets = [ticket for ticket in (analysis_response.get("gap_tickets") or []) if isinstance(ticket, dict)]
gap_ids = [str(ticket.get("gap_ticket_id")) for ticket in gap_tickets if ticket.get("gap_ticket_id")]

mode = st.radio(
	"Chat mode",
	options=["Mock prepared answers", "Real NY Part 253 RAG query"],
	horizontal=True,
)

if mode == "Mock prepared answers":
	_render_mock_mode(question_to_answer)
else:
	_render_rag_mode(gap_tickets)

st.subheader("Related context")
st.write(f"**Number of findings:** {len(gap_tickets)}")

top_severe = sorted(
	gap_tickets,
	key=lambda t: _severity_rank(_severity_value(t)),
)[:3]

if top_severe:
	st.write("**Top severe findings:**")
	for ticket in top_severe:
		st.write(
			f"- {ticket.get('gap_ticket_id')}: {ticket.get('title')} "
			f"(severity: {_severity_value(ticket) or 'unknown'})"
		)

st.write("**Available gap IDs:**", ", ".join(gap_ids) if gap_ids else "None")
