from __future__ import annotations

from src.api import assistant_service
from src.api.rag_client import RagApiError


def test_normalize_chat_mode_supports_prepared_alias() -> None:
    assert assistant_service.normalize_chat_mode("mock") == "prepared"
    assert assistant_service.normalize_chat_mode("prepared") == "prepared"
    assert assistant_service.normalize_chat_mode("real") == "real"
    assert assistant_service.normalize_chat_mode("auto") == "auto"
    assert assistant_service.normalize_chat_mode("unknown") == "auto"


def test_build_prepared_answers_only_keeps_valid_pairs() -> None:
    suggestions = [
        {"question": "Q1", "mock_answer": "A1"},
        {"question": "Q2", "mock_answer": ""},
        {"question": "", "mock_answer": "A3"},
        "not-a-dict",
    ]

    assert assistant_service.build_prepared_answers(suggestions) == {"Q1": "A1"}


def test_prepared_mode_exact_match_returns_reviewed_answer() -> None:
    result = assistant_service.answer_assistant_question(
        question="Reviewed question",
        context={"k": "v"},
        prepared_answers={"Reviewed question": "Prepared answer"},
        mode="prepared",
    )

    assert result["answer"] == "Prepared answer"
    assert result["provider"] == "prepared_fallback"
    assert result["prepared_answer_used"] is True
    assert result["fallback_used"] is True
    assert result["error_code"] is None


def test_prepared_mode_unreviewed_question_returns_guardrail() -> None:
    result = assistant_service.answer_assistant_question(
        question="Custom question",
        context={},
        prepared_answers={},
        mode="prepared",
    )

    assert result["prepared_answer_used"] is False
    assert result["error_code"] == "prepared_not_found"
    assert "No reviewed prepared response" in result["answer"]


def test_auto_mode_without_configuration_uses_prepared_answer(monkeypatch) -> None:
    monkeypatch.setattr(assistant_service.rag_client, "has_rag_configuration", lambda: False)

    result = assistant_service.answer_assistant_question(
        question="Reviewed question",
        context={"audit": "context"},
        prepared_answers={"Reviewed question": "Prepared answer"},
        mode="auto",
    )

    assert result["provider"] == "prepared_fallback"
    assert result["prepared_answer_used"] is True
    assert result["error_code"] == "config_missing"


def test_auto_mode_live_success_returns_sources_and_context_passthrough(monkeypatch) -> None:
    monkeypatch.setattr(assistant_service.rag_client, "has_rag_configuration", lambda: True)

    captured: dict = {}

    def _fake_live_query(question: str, context: dict) -> dict:
        captured["question"] = question
        captured["context"] = context
        return {
            "answer": "Live answer",
            "sources": [{"title": "NY Part 253", "sectionId": "253-4.2"}],
            "citation_validation": {"status": "ok"},
            "progress_messages": ["retrieving"],
        }

    monkeypatch.setattr(assistant_service, "_perform_live_query", _fake_live_query)

    context = {"engagement": {"facility_name": "Demo Facility"}}
    result = assistant_service.answer_assistant_question(
        question="What applies?",
        context=context,
        prepared_answers={},
        mode="auto",
    )

    assert result["provider"] == "sustentra_rag"
    assert result["fallback_used"] is False
    assert result["answer"] == "Live answer"
    assert captured["question"] == "What applies?"
    assert captured["context"] == context
    assert isinstance(result["sources"], list) and len(result["sources"]) == 1


def test_auto_mode_live_error_falls_back_and_sanitizes(monkeypatch) -> None:
    monkeypatch.setattr(assistant_service.rag_client, "has_rag_configuration", lambda: True)

    def _raise_live(_: str, __: dict) -> dict:
        raise RagApiError("401 api_key=my-secret-key")

    monkeypatch.setattr(assistant_service, "_perform_live_query", _raise_live)

    result = assistant_service.answer_assistant_question(
        question="Reviewed question",
        context={},
        prepared_answers={"Reviewed question": "Prepared answer"},
        mode="auto",
    )

    assert result["provider"] == "prepared_fallback"
    assert result["fallback_used"] is True
    assert result["prepared_answer_used"] is True
    assert result["error_code"] == "http_401"
    assert "my-secret-key" not in (result["error_message"] or "")
    assert "[REDACTED]" in (result["error_message"] or "")


def test_real_mode_without_configuration_returns_live_unavailable_message(monkeypatch) -> None:
    monkeypatch.setattr(assistant_service.rag_client, "has_rag_configuration", lambda: False)

    result = assistant_service.answer_assistant_question(
        question="Any question",
        context={},
        prepared_answers={"Any question": "Prepared answer"},
        mode="real",
    )

    assert result["provider"] == "sustentra_rag"
    assert result["live_attempted"] is False
    assert result["fallback_used"] is False
    assert result["prepared_answer_used"] is False
    assert result["error_code"] == "config_missing"
    assert "Live source-backed response is unavailable" in result["answer"]


def test_empty_question_is_rejected() -> None:
    result = assistant_service.answer_assistant_question(
        question="  ",
        context={},
        prepared_answers={},
        mode="auto",
    )

    assert result["error_code"] == "empty_question"
    assert result["prepared_answer_used"] is False
