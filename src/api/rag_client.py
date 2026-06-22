from __future__ import annotations

import json
import os
from typing import Any, Iterable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


DEFAULT_AUDIT_CONTEXT = {
    "jurisdiction": "NY",
    "entity_type": "facility owner or operator",
    "audit_scope": "compliance review",
    "reporting_period_end": "2026-12-31",
}


class RagApiError(Exception):
    pass


def _load_dotenv_safely() -> None:
    if load_dotenv is not None:
        load_dotenv(override=False)


def _get_streamlit_secret(key: str) -> str:
    try:
        import streamlit as st
    except Exception:  # pragma: no cover
        return ""

    try:
        value = st.secrets.get(key)
    except Exception:  # pragma: no cover
        return ""
    return str(value or "").strip()


def _resolve_config_value(key: str) -> str:
    direct = str(os.getenv(key) or "").strip()
    if direct:
        return direct

    _load_dotenv_safely()
    from_dotenv = str(os.getenv(key) or "").strip()
    if from_dotenv:
        return from_dotenv

    return _get_streamlit_secret(key)


def _get_rag_base_url() -> str:
    base_url = _resolve_config_value("RAG_API_URL")
    if not base_url:
        raise RagApiError("RAG_API_URL is not configured.")
    return base_url.rstrip("/")


def get_auditor_chat_mode() -> str:
    mode = _resolve_config_value("AUDITOR_CHAT_MODE").strip().lower()
    if mode in {"auto", "real", "mock"}:
        return mode
    return "auto"


def has_rag_configuration() -> bool:
    return bool(_resolve_config_value("RAG_API_URL")) and bool(_resolve_config_value("RAG_API_KEY"))


def _http_status_message(status_code: int) -> str:
    mapping = {
        400: "invalid request",
        401: "missing or invalid credential",
        403: "forbidden request or browser-origin policy issue",
        413: "request too large",
        429: "quota or rate limit exceeded",
        500: "service failure",
        503: "service unavailable",
    }
    return mapping.get(status_code, "unexpected HTTP error")


def _raise_http_error(status_code: int, response_text: str) -> None:
    detail = _http_status_message(status_code)
    body_preview = (response_text or "").strip()
    if len(body_preview) > 250:
        body_preview = body_preview[:250] + "..."

    if body_preview:
        raise RagApiError(
            f"RAG API request failed ({status_code}: {detail}). Response: {body_preview}"
        )
    raise RagApiError(f"RAG API request failed ({status_code}: {detail}).")


def _parse_health_json(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RagApiError("RAG health check returned non-JSON response.") from exc

    if not isinstance(payload, dict):
        raise RagApiError("RAG health check response must be a JSON object.")
    return payload


def _merge_audit_context(audit_context: dict | None) -> dict:
    if not audit_context:
        return dict(DEFAULT_AUDIT_CONTEXT)
    merged = dict(DEFAULT_AUDIT_CONTEXT)
    merged.update(audit_context)
    return merged


def _parse_stream(lines: Iterable[str | bytes]) -> dict:
    result = {
        "answer": "",
        "audit_query_id": None,
        "sources": [],
        "progress_messages": [],
        "citation_validation": None,
        "raw_done_event": None,
    }

    for raw_line in lines:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="ignore").strip()
        else:
            line = raw_line.strip()

        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type") or event.get("event") or "")
        event_data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if event_type == "error" or (not event_type and "error" in event):
            err_value = event.get("error") or event_data.get("error") or event.get("message")
            raise RagApiError(f"RAG query failed: {err_value or 'Unknown stream error event.'}")

        if event_type == "agent_step":
            message = event.get("message") or event_data.get("message") or event_data.get("text")
            if message:
                result["progress_messages"].append(str(message))
            continue

        if event_type == "retrieval":
            sources = (
                event.get("sources")
                or event_data.get("sources")
                or event.get("documents")
                or event_data.get("documents")
            )
            if isinstance(sources, dict):
                sources = [sources]
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        result["sources"].append(source)
            continue

        if event_type == "citation_validation":
            result["citation_validation"] = event_data or event.get("citation_validation") or event
            continue

        if event_type == "done":
            answer = event.get("answer") or event_data.get("answer")
            if isinstance(answer, str):
                result["answer"] = answer

            audit_query = event.get("auditQuery") or event_data.get("auditQuery")
            if isinstance(audit_query, dict):
                query_id = audit_query.get("id") or audit_query.get("auditQueryId")
                if query_id is not None:
                    result["audit_query_id"] = str(query_id)

            result["raw_done_event"] = event

    if result["raw_done_event"] is None:
        raise RagApiError("RAG stream completed without a terminal done event.")

    return result


def check_rag_health() -> dict:
    url = f"{_get_rag_base_url()}/api/health"

    if requests is not None:
        try:
            response = requests.get(url, timeout=20)
        except requests.RequestException as exc:  # type: ignore[attr-defined]
            raise RagApiError(f"RAG health check request failed: {exc}") from exc

        if response.status_code >= 400:
            _raise_http_error(response.status_code, response.text)
        return _parse_health_json(response.text)

    if httpx is not None:
        try:
            response = httpx.get(url, timeout=20)
        except httpx.HTTPError as exc:
            raise RagApiError(f"RAG health check request failed: {exc}") from exc

        if response.status_code >= 400:
            _raise_http_error(response.status_code, response.text)
        return _parse_health_json(response.text)

    raise RagApiError("Neither requests nor httpx is installed. Cannot call RAG API.")


def query_rag(question: str, audit_context: dict | None = None) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise RagApiError("Question must be a non-empty string.")

    api_key = _resolve_config_value("RAG_API_KEY")
    if not api_key:
        raise RagApiError("RAG_API_KEY is missing. Set it in your environment to use real RAG mode.")

    url = f"{_get_rag_base_url()}/api/query/agent/stream"
    payload = {
        "question": question.strip(),
        "regulationKey": "ny-part-253",
        "auditContext": _merge_audit_context(audit_context),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if requests is not None:
        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(15, 120),
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    _raise_http_error(response.status_code, response.text)
                return _parse_stream(response.iter_lines(decode_unicode=True))
        except requests.RequestException as exc:  # type: ignore[attr-defined]
            raise RagApiError(f"RAG query request failed: {exc}") from exc

    if httpx is not None:
        timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=30.0)
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        _raise_http_error(response.status_code, response.text)
                    return _parse_stream(response.iter_lines())
        except httpx.HTTPError as exc:
            raise RagApiError(f"RAG query request failed: {exc}") from exc

    raise RagApiError("Neither requests nor httpx is installed. Cannot call RAG API.")
