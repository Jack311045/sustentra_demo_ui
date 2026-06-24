from __future__ import annotations

import re
from typing import Any

from src.api import rag_client

LIVE_UNAVAILABLE_UNREVIEWED_MESSAGE = (
    "A live source-backed answer is not available, and this question does not match a reviewed "
    "prepared response. Check the API configuration or select one of the reviewed suggested questions."
)

REAL_MODE_FAILURE_MESSAGE = (
    "Live source-backed response is unavailable right now. Retry or switch to prepared mode."
)

PREPARED_UNREVIEWED_MESSAGE = (
    "No reviewed prepared response is available for that question. Select one of the reviewed "
    "suggested questions or switch to live mode."
)

_ERROR_CODE_PATTERNS: list[tuple[str, str]] = [
    (r"401", "http_401"),
    (r"403", "http_403"),
    (r"413", "http_413"),
    (r"429", "http_429"),
    (r"500", "http_500"),
    (r"503", "http_503"),
    (r"RAG_API_URL|configured", "config_missing_url"),
    (r"RAG_API_KEY|credential", "config_missing_key"),
    (r"timed out|timeout", "timeout"),
]


def normalize_chat_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == "mock":
        return "prepared"
    if normalized in {"auto", "real", "prepared"}:
        return normalized
    return "auto"


def current_chat_mode() -> str:
    return normalize_chat_mode(rag_client.get_auditor_chat_mode())


def build_prepared_answers(chat_suggestions: list[dict] | None) -> dict[str, str]:
    prepared: dict[str, str] = {}
    for item in chat_suggestions or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("mock_answer") or "").strip()
        if question and answer:
            prepared[question] = answer
    return prepared


def _sanitize_error_message(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        return ""

    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"sk-[A-Za-z0-9._\-]+", "[REDACTED]", text)
    text = re.sub(r"(api[_-]?key\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)

    if len(text) > 240:
        text = text[:237].rstrip() + "..."
    return text


def _error_code_from_message(message: str) -> str:
    for pattern, code in _ERROR_CODE_PATTERNS:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return code
    return "request_error"


def _provider_label(provider: str, prepared_answer_used: bool) -> str:
    if provider == "sustentra_rag":
        return "Live source-backed response"
    if prepared_answer_used:
        return "Prepared reviewed response"
    return "Prepared fallback"


def _base_result(mode: str) -> dict:
    return {
        "answer": "",
        "provider": "prepared_fallback",
        "provider_label": "Prepared fallback",
        "live_attempted": False,
        "fallback_used": False,
        "prepared_answer_used": False,
        "sources": [],
        "citation_validation": None,
        "progress_messages": [],
        "error_code": None,
        "error_message": None,
        "mode_used": normalize_chat_mode(mode),
    }


def _prepared_result(
    mode: str,
    answer: str,
    *,
    error_code: str | None,
    error_message: str | None,
    prepared_answer_used: bool,
) -> dict:
    result = _base_result(mode)
    result.update(
        {
            "answer": answer,
            "provider": "prepared_fallback",
            "provider_label": _provider_label("prepared_fallback", prepared_answer_used),
            "live_attempted": normalize_chat_mode(mode) != "prepared",
            "fallback_used": True,
            "prepared_answer_used": prepared_answer_used,
            "error_code": error_code,
            "error_message": error_message,
        }
    )
    return result


def _live_result(mode: str, payload: dict) -> dict:
    result = _base_result(mode)
    result.update(
        {
            "answer": str(payload.get("answer") or "").strip(),
            "provider": "sustentra_rag",
            "provider_label": _provider_label("sustentra_rag", False),
            "live_attempted": True,
            "fallback_used": False,
            "prepared_answer_used": False,
            "sources": payload.get("sources") if isinstance(payload.get("sources"), list) else [],
            "citation_validation": payload.get("citation_validation"),
            "progress_messages": payload.get("progress_messages") if isinstance(payload.get("progress_messages"), list) else [],
            "error_code": None,
            "error_message": None,
        }
    )

    if not result["answer"]:
        result["answer"] = "Live source-backed response returned no answer text."
    return result


def _perform_live_query(question: str, context: dict) -> dict:
    return rag_client.query_rag(question=question, audit_context=context)


def answer_assistant_question(
    question: str,
    context: dict,
    prepared_answers: dict[str, str],
    mode: str,
) -> dict:
    mode_used = normalize_chat_mode(mode)
    asked = str(question or "").strip()
    prepared_answer = str(prepared_answers.get(asked) or "").strip()

    if not asked:
        return _prepared_result(
            mode_used,
            PREPARED_UNREVIEWED_MESSAGE,
            error_code="empty_question",
            error_message="Question is empty.",
            prepared_answer_used=False,
        )

    if mode_used == "prepared":
        if prepared_answer:
            return _prepared_result(
                mode_used,
                prepared_answer,
                error_code=None,
                error_message=None,
                prepared_answer_used=True,
            )
        return _prepared_result(
            mode_used,
            PREPARED_UNREVIEWED_MESSAGE,
            error_code="prepared_not_found",
            error_message=None,
            prepared_answer_used=False,
        )

    can_use_live = rag_client.has_rag_configuration()

    if mode_used == "real":
        if not can_use_live:
            return {
                **_base_result(mode_used),
                "answer": REAL_MODE_FAILURE_MESSAGE,
                "provider": "sustentra_rag",
                "provider_label": _provider_label("sustentra_rag", False),
                "live_attempted": False,
                "fallback_used": False,
                "prepared_answer_used": False,
                "error_code": "config_missing",
                "error_message": "RAG configuration is incomplete.",
            }

        try:
            payload = _perform_live_query(asked, context)
            return _live_result(mode_used, payload)
        except rag_client.RagApiError as exc:
            sanitized = _sanitize_error_message(exc)
            return {
                **_base_result(mode_used),
                "answer": REAL_MODE_FAILURE_MESSAGE,
                "provider": "sustentra_rag",
                "provider_label": _provider_label("sustentra_rag", False),
                "live_attempted": True,
                "fallback_used": False,
                "prepared_answer_used": False,
                "error_code": _error_code_from_message(sanitized),
                "error_message": sanitized,
            }

    # Auto mode.
    if can_use_live:
        try:
            payload = _perform_live_query(asked, context)
            return _live_result(mode_used, payload)
        except rag_client.RagApiError as exc:
            sanitized = _sanitize_error_message(exc)
            if prepared_answer:
                return _prepared_result(
                    mode_used,
                    prepared_answer,
                    error_code=_error_code_from_message(sanitized),
                    error_message=sanitized,
                    prepared_answer_used=True,
                )
            return _prepared_result(
                mode_used,
                LIVE_UNAVAILABLE_UNREVIEWED_MESSAGE,
                error_code=_error_code_from_message(sanitized),
                error_message=sanitized,
                prepared_answer_used=False,
            )

    if prepared_answer:
        return _prepared_result(
            mode_used,
            prepared_answer,
            error_code="config_missing",
            error_message="RAG configuration is incomplete.",
            prepared_answer_used=True,
        )

    return _prepared_result(
        mode_used,
        LIVE_UNAVAILABLE_UNREVIEWED_MESSAGE,
        error_code="config_missing",
        error_message="RAG configuration is incomplete.",
        prepared_answer_used=False,
    )
