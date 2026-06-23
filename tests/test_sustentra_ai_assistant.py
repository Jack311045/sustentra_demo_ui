from __future__ import annotations

import ast
import json
import py_compile
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.regulatory_assistant import (
    GAP010_REVIEW_NOTICE,
    UNKNOWN_REVIEWED_SET_MESSAGE,
    parse_basis_clause,
    resolve_curated_answer,
)

PAGE_7 = Path("pages/7_Sustentra_AI_Assistant.py")
OLD_PAGE_7 = Path("pages/7_Regulatory_Assistant.py")
STATE_FILE = Path("src/ui/state.py")
CARDS_FILE = Path("src/ui/cards.py")
APP_FILE = Path("app.py")

MOCK_RESPONSE_FILES = [
    Path("data/demo/mock_outputs/mock_analysis_response.json"),
    Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"),
    Path("data/demo/mock_outputs/mock_analysis_response_clean_path.json"),
]

APPROVED_TIER1_QUESTIONS = [
    "Can we accept a biomass-derived CO2 classification based only on an invoice line item and a marketing certificate?",
    "Is total fuel quantity alone enough for Part 253 reporting, or do we need supplier account information?",
    "If a facility reports 9,650 MT CO2e from boilers but excludes a 620 MT hydrogen fuel cell, is it below the 10,000 MT reporting threshold?",
    "Do we need a separate scope 1 line for pilot fuel used in flare operation, or can it stay embedded in total fuel gas?",
    "Can we carry over a prior-year fuel meter value as opening inventory without documenting meter reset and calibration evidence?",
    "If district steam purchases are billed in MMBtu but internal logs convert to tonnes steam, which value is acceptable for Part 253 reporting support?",
]

FORBIDDEN_PAGE_STRINGS = (
    "Prepared demo workflow",
    "Live service",
    "Auto mode",
    "Fallback answer",
    "Citation review warning",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_page7(
    response: dict,
    *,
    context_gap_ticket_id: str | None = None,
    selected_chat_question: str | None = None,
    chat_history: list[dict] | None = None,
) -> AppTest:
    at = AppTest.from_file(str(PAGE_7), default_timeout=45)
    at.session_state["analysis_response"] = deepcopy(response)
    at.session_state["audit_setup"] = deepcopy(response.get("audit_setup") or {})
    if context_gap_ticket_id is not None:
        at.session_state["chat_context_gap_ticket_id"] = context_gap_ticket_id
    if selected_chat_question is not None:
        at.session_state["selected_chat_question"] = selected_chat_question
    if chat_history is not None:
        at.session_state["chat_history"] = chat_history
    at.run()
    return at


def _collect_text(at: AppTest) -> str:
    parts: list[str] = []
    for group in ("markdown", "caption", "text", "success", "warning", "error", "info"):
        for item in getattr(at, group):
            value = getattr(item, "value", None)
            if isinstance(value, str) and value.strip():
                parts.append(value)
    for button in at.button:
        if isinstance(button.label, str) and button.label.strip():
            parts.append(button.label)
    for chat_message in at.chat_message:
        role = getattr(chat_message, "name", None)
        if isinstance(role, str):
            parts.append(role)
    return "\n".join(parts)


def test_page7_compiles_and_old_page_is_removed() -> None:
    py_compile.compile(str(PAGE_7), doraise=True)
    assert OLD_PAGE_7.exists() is False


def test_page7_source_contract_blocks_live_rag_and_forbidden_phrases() -> None:
    source = PAGE_7.read_text(encoding="utf-8")
    tree = ast.parse(source)

    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)

    for forbidden_id in ("query_rag", "get_auditor_chat_mode", "has_rag_configuration", "set_analysis_response"):
        assert forbidden_id not in identifiers
        assert forbidden_id not in source

    for forbidden_phrase in FORBIDDEN_PAGE_STRINGS:
        assert forbidden_phrase not in source

    assert (
        "Sustentra AI Assistant supports regulatory research and audit documentation. "
        "It does not provide legal advice."
    ) in source
    assert "visible_questions = ordered_questions[:3]" in source
    assert "More reviewed questions" in source


def test_navigation_and_labels_use_sustentra_ai_assistant_name() -> None:
    state_source = STATE_FILE.read_text(encoding="utf-8")
    cards_source = CARDS_FILE.read_text(encoding="utf-8")
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert "pages/7_Sustentra_AI_Assistant.py" in state_source
    assert "Open Sustentra AI Assistant from the sidebar." in state_source
    assert "Ask Sustentra AI Assistant" in cards_source
    assert "Sustentra AI Assistant" in app_source


def test_chat_suggestions_are_exact_reviewed_tier1_set() -> None:
    for path in MOCK_RESPONSE_FILES:
        payload = _read_json(path)
        suggestions = payload.get("chat_suggestions")

        assert isinstance(suggestions, list)
        assert len(suggestions) == 6

        questions: list[str] = []
        for item in suggestions:
            assert isinstance(item, dict)
            assert set(item.keys()) == {"question", "mock_answer"}

            question = str(item.get("question") or "")
            answer = str(item.get("mock_answer") or "")

            assert question
            assert answer
            assert "Needs confirmation" not in answer
            questions.append(question)

        assert questions == APPROVED_TIER1_QUESTIONS


def test_basis_parser_supports_plain_and_parenthetical_basis_trailers() -> None:
    plain_text = "Use traceable support and supplier records. Basis: 6 NYCRR 253-4.2 and 6 NYCRR 253-8.2"
    plain_body, plain_citations = parse_basis_clause(plain_text)
    assert plain_body == "Use traceable support and supplier records"
    assert "6 NYCRR 253-4.2" in plain_citations
    assert "6 NYCRR 253-8.2" in plain_citations

    wrapped_text = "Use controlled conversion records. (Basis: 6 NYCRR 253-8.2; 6 NYCRR 253-4.1)"
    wrapped_body, wrapped_citations = parse_basis_clause(wrapped_text)
    assert wrapped_body == "Use controlled conversion records."
    assert "6 NYCRR 253-8.2" in wrapped_citations
    assert "6 NYCRR 253-4.1" in wrapped_citations


def test_unknown_question_maps_to_reviewed_set_guardrail_message() -> None:
    payload = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    suggestions = payload.get("chat_suggestions") or []

    assert resolve_curated_answer(suggestions, "Unknown question") is None
    assert "reviewed answer" in UNKNOWN_REVIEWED_SET_MESSAGE


def test_selected_chat_question_generates_structured_response_once_for_gap_context() -> None:
    response = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    at = _run_page7(
        response,
        context_gap_ticket_id="GT-DEMO-GAP-003",
        selected_chat_question=APPROVED_TIER1_QUESTIONS[0],
    )

    assert len(at.exception) == 0
    assert "selected_chat_question" not in at.session_state

    history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assert isinstance(history, list)
    assert len(history) >= 2

    assistant_message = history[-1]
    assert assistant_message.get("role") == "assistant"
    metadata = assistant_message.get("metadata") if isinstance(assistant_message.get("metadata"), dict) else {}
    structured = metadata.get("structured_response") if isinstance(metadata.get("structured_response"), dict) else {}

    assert structured.get("context_gap_ticket_id") == "GT-DEMO-GAP-003"
    assert isinstance(structured.get("evidence_refs"), list) and structured.get("evidence_refs")
    assert isinstance(structured.get("regulatory_citations"), list) and structured.get("regulatory_citations")
    assert structured.get("direct_answer") != UNKNOWN_REVIEWED_SET_MESSAGE

    history_len = len(history)
    at.run()
    assert len(at.exception) == 0
    next_history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assert len(next_history) == history_len


def test_gap010_context_uses_under_review_response_and_neutralized_citation_text() -> None:
    response = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    at = _run_page7(
        response,
        context_gap_ticket_id="GT-DEMO-GAP-010",
        selected_chat_question=APPROVED_TIER1_QUESTIONS[1],
    )

    assert len(at.exception) == 0
    history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assistant_message = history[-1]
    metadata = assistant_message.get("metadata") if isinstance(assistant_message.get("metadata"), dict) else {}
    structured = metadata.get("structured_response") if isinstance(metadata.get("structured_response"), dict) else {}

    assert structured.get("direct_answer") == GAP010_REVIEW_NOTICE

    citations = structured.get("regulatory_citations") if isinstance(structured.get("regulatory_citations"), list) else []
    assert citations
    for citation in citations:
        assert citation.get("requirement_summary") == "Interpretation under source review."
        assert citation.get("applicability_explanation") == "Not included in the verified assistant knowledge set."


def test_legacy_string_only_assistant_history_renders_without_exception() -> None:
    response = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    at = _run_page7(
        response,
        chat_history=[{"role": "assistant", "content": "Legacy assistant response"}],
    )

    assert len(at.exception) == 0
    rendered = _collect_text(at)
    assert "Legacy assistant response" in rendered


def test_page7_context_controls_and_top_reviewed_questions_render() -> None:
    response = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    at = _run_page7(response, context_gap_ticket_id="GT-DEMO-GAP-003")

    assert len(at.exception) == 0
    labels = [str(button.label) for button in at.button]

    for question in APPROVED_TIER1_QUESTIONS[:3]:
        assert question in labels

    assert "Open source evidence" in labels
    assert "View regulation context" in labels
    assert "Back to finding" in labels


def test_page7_does_not_mutate_analysis_response_payload() -> None:
    response = _read_json(Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json"))
    baseline = deepcopy(response)

    at = _run_page7(response, context_gap_ticket_id="GT-DEMO-GAP-003")
    assert len(at.exception) == 0
    assert "analysis_response" in at.session_state
    assert at.session_state["analysis_response"] == baseline
