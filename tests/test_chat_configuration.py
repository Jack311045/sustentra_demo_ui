from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.api import rag_client


def test_chat_mode_defaults_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDITOR_CHAT_MODE", raising=False)
    assert rag_client.get_auditor_chat_mode() == "auto"


def test_chat_mode_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDITOR_CHAT_MODE", "real")
    assert rag_client.get_auditor_chat_mode() == "real"

    monkeypatch.setenv("AUDITOR_CHAT_MODE", "prepared")
    assert rag_client.get_auditor_chat_mode() == "prepared"

    monkeypatch.setenv("AUDITOR_CHAT_MODE", "mock")
    assert rag_client.get_auditor_chat_mode() == "prepared"


def test_chat_mode_invalid_value_falls_back_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDITOR_CHAT_MODE", "unexpected-value")
    assert rag_client.get_auditor_chat_mode() == "auto"


def test_has_rag_configuration_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values_missing = {"RAG_API_URL": None, "RAG_API_KEY": None}
    monkeypatch.setattr(rag_client, "_resolve_config_value", lambda name: values_missing.get(name))
    assert rag_client.has_rag_configuration() is False

    values_present = {"RAG_API_URL": "https://example.test", "RAG_API_KEY": "example-key"}
    monkeypatch.setattr(rag_client, "_resolve_config_value", lambda name: values_present.get(name))
    assert rag_client.has_rag_configuration() is True


def test_query_rag_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_API_URL", "https://example.test")
    monkeypatch.delenv("RAG_API_KEY", raising=False)

    with pytest.raises(rag_client.RagApiError):
        rag_client.query_rag("What applies to this scenario?")


def test_rag_client_does_not_print_keys() -> None:
    source = Path("src/api/rag_client.py").read_text(encoding="utf-8")
    assert "print(" not in source
    assert "st.write(api_key" not in source
    assert "st.json(headers" not in source
