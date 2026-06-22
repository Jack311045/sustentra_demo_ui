from __future__ import annotations

import importlib
import subprocess

import pytest


def test_streamlit_cloud_compatible_imports() -> None:
    modules = [
        "src.api.adapters",
        "src.api.mock_client",
        "src.ui.state",
        "src.ui.workflow",
    ]
    for module_name in modules:
        importlib.import_module(module_name)


def test_protected_extraction_pipeline_files_unchanged() -> None:
    paths = [
        "src/run_document_pipeline.py",
        "src/textract_json_to_markdown.py",
        "src/fill_json_from_markdown.py",
        "src/test_openai_connection.py",
        ".env",
    ]
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *paths],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("git status is unavailable in this environment")
    assert result.stdout.strip() == ""
