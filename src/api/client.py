"""
Backend API client.

This module will call Claire's backend API once the endpoint contract is available.
Do not import this directly in Streamlit pages. Use adapters and UI models so the UI
does not depend on raw backend response shapes.
"""

from __future__ import annotations


class BackendApiClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def analyze(self, *args, **kwargs):
        raise NotImplementedError("Backend API integration is not implemented yet.")
