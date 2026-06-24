from __future__ import annotations

import ast
import json
import py_compile
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


PAGE_7 = Path("pages/7_Sustentra_AI_Assistant.py")
OLD_PAGE_7 = Path("pages/7_Regulatory_Assistant.py")
STATE_FILE = Path("src/ui/state.py")
GAP_PAGE_FILE = Path("pages/6_Gap_Analysis.py")
APP_FILE = Path("app.py")
FIXTURE_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")


@pytest.fixture(autouse=True)
def _stable_prepared_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDITOR_CHAT_MODE", "prepared")
    monkeypatch.setenv("RAG_API_URL", "")
    monkeypatch.setenv("RAG_API_KEY", "")
    monkeypatch.setenv("ASSISTANT_CONTEXT_MAX_CHARS", "60000")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_page7(
    response: dict,
    *,
    context_gap_ticket_id: str | None = None,
    selected_chat_question: str | None = None,
    chat_history: list[dict] | None = None,
    selected_evidence_id: str | None = None,
    selected_validation_id: str | None = None,
    selected_calculation_id: str | None = None,
    selected_workbook_location: dict | None = None,
    created_gap_ticket_ids: list[str] | None = None,
    gap_ticket_overrides: dict | None = None,
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
    if selected_evidence_id is not None:
        at.session_state["selected_evidence_id"] = selected_evidence_id
    if selected_validation_id is not None:
        at.session_state["selected_validation_id"] = selected_validation_id
    if selected_calculation_id is not None:
        at.session_state["selected_calculation_id"] = selected_calculation_id
    if selected_workbook_location is not None:
        at.session_state["selected_workbook_location"] = selected_workbook_location
    if created_gap_ticket_ids is not None:
        at.session_state["created_gap_ticket_ids"] = created_gap_ticket_ids
    if gap_ticket_overrides is not None:
        at.session_state["gap_ticket_overrides"] = gap_ticket_overrides

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
    return "\n".join(parts)


def test_page7_compiles_and_old_page_is_removed() -> None:
    py_compile.compile(str(PAGE_7), doraise=True)
    assert OLD_PAGE_7.exists() is False


def test_page7_source_contract_includes_live_orchestration() -> None:
    source = PAGE_7.read_text(encoding="utf-8")
    tree = ast.parse(source)

    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)

    assert "answer_assistant_question" in identifiers
    assert "build_assistant_context" in identifiers
    assert "has_rag_configuration" in source
    assert "Retry on live service" in source
    assert "Retry last question using live service" not in source
    assert "Assistant diagnostics" in source
    assert "with st.sidebar" in source
    assert "not legal advice" in source.lower()
    assert "Draft client clarification request" not in source
    assert "Context summary" not in source
    assert "More suggested questions" not in source
    assert "Evidence & context" in source
    assert '"**Next step:** "' in source
    assert "_LEADING_ANSWER_HEADING_RE" in source
    assert "_strip_redundant_leading_heading" in source
    assert 'st.markdown("**Conclusion**")' not in source


def test_navigation_and_labels_use_sustentra_ai_assistant_name() -> None:
    state_source = STATE_FILE.read_text(encoding="utf-8")
    gap_source = GAP_PAGE_FILE.read_text(encoding="utf-8")
    app_source = APP_FILE.read_text(encoding="utf-8")

    assert "pages/7_Sustentra_AI_Assistant.py" in state_source
    assert "Open Sustentra AI Assistant from the sidebar." in state_source
    assert "Ask Sustentra AI Assistant" in gap_source
    assert "Sustentra AI Assistant" in app_source


def test_page7_renders_sidebar_context_actions_and_diagnostics() -> None:
    response = _read_json(FIXTURE_PATH)
    at = _run_page7(response, context_gap_ticket_id="GT-DEMO-GAP-003")

    assert len(at.exception) == 0
    rendered = _collect_text(at)

    assert "Context summary" not in rendered
    assert "Facility ·" in rendered
    assert "Clear conversation" in rendered
    assert "Retry on live service" in rendered
    assert "Remove finding context" in rendered
    assert "Explain finding" in rendered
    assert "Draft auditor note" in rendered
    assert "Draft client clarification request" not in rendered


def test_page7_suggested_questions_use_single_collapsed_group() -> None:
    source = PAGE_7.read_text(encoding="utf-8")

    assert "Suggested questions" in source
    assert "More suggested questions" not in source


def test_selected_chat_question_from_gap_action_is_processed_once_with_structured_metadata() -> None:
    response = _read_json(FIXTURE_PATH)
    queued_question = "What regulation text applies to GT-DEMO-GAP-003 and why?"

    at = _run_page7(
        response,
        context_gap_ticket_id="GT-DEMO-GAP-003",
        selected_chat_question=queued_question,
    )

    assert len(at.exception) == 0
    assert "selected_chat_question" not in at.session_state

    history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assert isinstance(history, list)
    assert len(history) >= 2

    queued_messages = [
        item
        for item in history
        if isinstance(item, dict)
        and item.get("role") == "user"
        and item.get("content") == queued_question
    ]
    assert len(queued_messages) == 1

    assistant_message = history[-1]
    assert assistant_message.get("role") == "assistant"

    metadata = assistant_message.get("metadata") if isinstance(assistant_message.get("metadata"), dict) else {}
    assert metadata.get("provider") in {"prepared_fallback", "sustentra_rag"}
    assert isinstance(metadata.get("sections"), dict)

    sections = metadata.get("sections") if isinstance(metadata.get("sections"), dict) else {}
    assert isinstance(sections.get("conclusion"), str)
    assert isinstance(sections.get("evidence_context"), list)
    assert isinstance(sections.get("regulatory_basis"), list)

    history_len = len(history)
    at.run()
    assert len(at.exception) == 0
    next_history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assert len(next_history) == history_len


def test_page7_context_uses_created_gap_ticket_ids_and_overrides() -> None:
    source = PAGE_7.read_text(encoding="utf-8")
    assert "created_gap_ticket_ids=get_created_gap_ticket_ids()" in source
    assert "gap_ticket_overrides=get_gap_ticket_overrides()" in source

    response = _read_json(FIXTURE_PATH)
    created_ids = ["GT-DEMO-GAP-003", "GT-DEMO-GAP-005"]
    overrides = {
        "GT-DEMO-GAP-003": {
            "severity": "critical",
            "auditor_title": "Auditor override title",
        }
    }

    at = _run_page7(
        response,
        context_gap_ticket_id="GT-DEMO-GAP-003",
        created_gap_ticket_ids=created_ids,
        gap_ticket_overrides=overrides,
    )

    assert len(at.exception) == 0


def test_auto_mode_without_match_returns_controlled_unavailable_message() -> None:
    response = _read_json(FIXTURE_PATH)

    at = _run_page7(
        response,
        selected_chat_question="Custom question with no reviewed prepared answer",
    )

    assert len(at.exception) == 0
    history = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    assert len(history) >= 2

    assistant_message = history[-1]
    metadata = assistant_message.get("metadata") if isinstance(assistant_message.get("metadata"), dict) else {}

    assert metadata.get("provider") == "prepared_fallback"
    assert metadata.get("prepared_answer_used") is False
    assert metadata.get("error_code") in {"prepared_not_found", "config_missing", "request_error"}
    content = str(assistant_message.get("content") or "")
    assert (
        "No reviewed prepared response" in content
        or "not available" in content.lower()
    )


def test_legacy_string_only_assistant_history_renders_without_exception() -> None:
    response = _read_json(FIXTURE_PATH)
    at = _run_page7(
        response,
        chat_history=[{"role": "assistant", "content": "Legacy assistant response"}],
    )

    assert len(at.exception) == 0
    rendered = _collect_text(at)
    assert "Legacy assistant response" in rendered


def test_page7_includes_selected_navigation_context_identifiers() -> None:
    response = _read_json(FIXTURE_PATH)
    evidence_id = str((response.get("evidence_results") or [{}])[0].get("evidence_id") or "")
    validation_id = str((response.get("validation_results") or [{}])[0].get("validation_id") or "")
    calculation_id = str((response.get("calculation_results") or [{}])[0].get("calculation_id") or "")

    at = _run_page7(
        response,
        selected_evidence_id=evidence_id,
        selected_validation_id=validation_id,
        selected_calculation_id=calculation_id,
        selected_workbook_location={"sheet_name": "Summary", "cell_or_range": "D12"},
    )

    assert len(at.exception) == 0
    rendered = _collect_text(at)
    assert evidence_id in rendered
    assert validation_id in rendered
    assert calculation_id in rendered
    assert "Summary!D12" in rendered


def test_page7_does_not_mutate_analysis_response_payload() -> None:
    response = _read_json(FIXTURE_PATH)
    baseline = deepcopy(response)

    at = _run_page7(response, context_gap_ticket_id="GT-DEMO-GAP-003")
    assert len(at.exception) == 0
    assert "analysis_response" in at.session_state
    assert at.session_state["analysis_response"] == baseline
