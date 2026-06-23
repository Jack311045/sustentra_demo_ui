from __future__ import annotations

import py_compile
from pathlib import Path

from src.api.adapters import adapt_analysis_response
from src.api.mock_client import MockApiClient
from src.ui.formatting import is_internal_routing_evidence
from src.ui.workflow import build_engagement_expectation_summary


def test_mock_client_gap_path_loads() -> None:
    response = MockApiClient().analyze("gap_path")

    assert response.get("scenario_id") == "gap_path"
    assert isinstance(response.get("evidence_results"), list)
    assert isinstance(response.get("validation_results"), list)
    assert isinstance(response.get("calculation_results"), list)
    assert isinstance(response.get("gap_tickets"), list)


def test_mock_client_clean_path_structure_exists() -> None:
    response = MockApiClient().analyze("clean_path")

    assert response.get("scenario_id") == "clean_path"
    assert response.get("scenario_status") == "not_available"
    assert isinstance(response.get("warnings"), list)


def test_adapter_populates_new_defaults() -> None:
    adapted = adapt_analysis_response({})

    assert isinstance(adapted.get("audit_setup"), dict)
    assert isinstance(adapted.get("uploaded_demo_files"), dict)
    assert isinstance(adapted.get("validation_results"), list)
    assert isinstance(adapted.get("calculation_results"), list)
    assert isinstance(adapted.get("reconciliation_summary"), dict)


def test_internal_evidence_id_flagged_for_hidden_default_view() -> None:
    assert is_internal_routing_evidence("EV-PACK-INDEX-2023-000") is True
    assert is_internal_routing_evidence("EV-NG-2023-010") is False


def test_all_pages_compile() -> None:
    targets = [
        "app.py",
        "pages/1_Audit_Setup.py",
        "pages/2_Evidence_Intake.py",
        "pages/3_Extraction_Review.py",
        "pages/4_Validation.py",
        "pages/5_Calculation_and_Reconciliation.py",
        "pages/6_Gap_Analysis.py",
        "pages/7_Sustentra_AI_Assistant.py",
    ]
    for target in targets:
        py_compile.compile(target, doraise=True)


def test_evidence_intake_has_prepared_workflow_button_and_disclosure() -> None:
    source = Path("pages/2_Evidence_Intake.py").read_text(encoding="utf-8")

    assert "Run prepared demo workflow" in source
    assert "current build uses prepared" in source.lower()


def test_sustentra_ai_assistant_disclaimer_and_no_live_rag_strings() -> None:
    source = Path("pages/7_Sustentra_AI_Assistant.py").read_text(encoding="utf-8")

    assert "does not provide legal advice" in source
    assert "query_rag" not in source
    assert "get_auditor_chat_mode" not in source
    assert "Live service" not in source
    assert "Chat mode" not in source


def test_workflow_progress_renderer_removed() -> None:
    source = Path("src/ui/workflow.py").read_text(encoding="utf-8")

    assert "render_workflow_progress" not in source
    assert "WORKFLOW_STEPS" not in source


def test_engagement_expectation_summary_helper_returns_text() -> None:
    summary = build_engagement_expectation_summary(
        selected_scopes=["Scope 1", "Scope 2"],
        reporting_period="2023-01-01 to 2023-12-31",
        materiality_absolute="750 tCO2e",
    )

    assert isinstance(summary, str)
    assert "Scope 1, Scope 2" in summary
    assert "12 per selected scope" in summary
    assert "750 tCO2e" in summary
