from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from src.api.adapters import (
    adapt_analysis_response,
    has_meaningful_audit_setup,
    normalize_audit_setup,
    resolve_audit_setup,
)
from src.api.mock_client import MockApiClient
from src.ui import state as state_module


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _sample_setup(company_name: str) -> dict:
    return normalize_audit_setup(
        {
            "company_and_facility_profile": {
                "company_name": company_name,
                "facility_name": "Main Plant",
                "facility_address": "100 Demo Rd",
                "company_facility_identifier": "FAC-001",
                "industry": "Manufacturing",
                "facility_type": "Plant",
                "reporting_period": "2023-01-01 to 2023-12-31",
            },
            "engagement_details": {
                "engagement_name": "Prepared Demo Engagement",
            },
        }
    )


def _install_fake_streamlit(monkeypatch):
    fake_st = SimpleNamespace(session_state={}, info=lambda *args, **kwargs: None, switch_page=None)
    monkeypatch.setattr(state_module, "st", fake_st)
    return fake_st


def _is_meaningful_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    return not text.lower().startswith("needs confirmation")


def test_has_meaningful_audit_setup_detects_real_content() -> None:
    assert has_meaningful_audit_setup({}) is False
    assert has_meaningful_audit_setup(normalize_audit_setup({})) is False
    assert (
        has_meaningful_audit_setup(
            {
                "company_and_facility_profile": {
                    "company_name": "Needs confirmation from facility controller",
                }
            }
        )
        is False
    )

    prepared_setup = _read_json("data/demo/mock_outputs/mock_audit_setup.json")
    assert has_meaningful_audit_setup(prepared_setup) is True


def test_resolve_audit_setup_priority_saved_session_over_response() -> None:
    resolved = resolve_audit_setup(
        session_setup=_sample_setup("Saved Co"),
        response_setup=_sample_setup("Response Co"),
        prepared_setup=_sample_setup("Prepared Co"),
        session_is_user_saved=True,
    )
    profile = resolved.get("company_and_facility_profile", {})
    assert profile.get("company_name") == "Saved Co"


def test_resolve_audit_setup_priority_response_when_session_not_saved() -> None:
    resolved = resolve_audit_setup(
        session_setup=_sample_setup("Unsaved Session Co"),
        response_setup=_sample_setup("Response Co"),
        prepared_setup=_sample_setup("Prepared Co"),
        session_is_user_saved=False,
    )
    profile = resolved.get("company_and_facility_profile", {})
    assert profile.get("company_name") == "Response Co"


def test_resolve_audit_setup_priority_unsaved_session_over_prepared() -> None:
    resolved = resolve_audit_setup(
        session_setup=_sample_setup("Unsaved Session Co"),
        response_setup={},
        prepared_setup=_sample_setup("Prepared Co"),
        session_is_user_saved=False,
    )
    profile = resolved.get("company_and_facility_profile", {})
    assert profile.get("company_name") == "Unsaved Session Co"


def test_resolve_audit_setup_priority_prepared_fallback() -> None:
    resolved = resolve_audit_setup(
        session_setup={},
        response_setup={},
        prepared_setup=_sample_setup("Prepared Co"),
        session_is_user_saved=False,
    )
    profile = resolved.get("company_and_facility_profile", {})
    assert profile.get("company_name") == "Prepared Co"


def test_resolve_audit_setup_returns_empty_when_all_inputs_empty() -> None:
    resolved = resolve_audit_setup(
        session_setup={},
        response_setup={},
        prepared_setup={},
        session_is_user_saved=False,
    )
    assert resolved == {}


def test_init_session_state_keeps_empty_setup_shell_out_of_session(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    state_module.init_session_state()

    assert fake_st.session_state.get("audit_setup") == {}
    assert state_module.get_audit_setup() == {}


def test_set_analysis_response_keeps_empty_audit_setup_empty(monkeypatch) -> None:
    _install_fake_streamlit(monkeypatch)

    state_module.init_session_state()
    state_module.set_analysis_response(
        {
            "run_id": "run-001",
            "status": "ok",
            "audit_setup": {},
        }
    )

    response = state_module.get_analysis_response()
    assert isinstance(response, dict)
    assert response.get("audit_setup") == {}


def test_set_audit_setup_revision_changes_only_on_setup_change(monkeypatch) -> None:
    _install_fake_streamlit(monkeypatch)

    state_module.init_session_state()
    saved_setup = _sample_setup("Alpha Co")

    state_module.set_audit_setup(saved_setup, user_saved=True, increment_revision=True)
    revision_after_first_save = state_module.get_audit_setup_revision()

    state_module.set_audit_setup(copy.deepcopy(saved_setup), user_saved=True, increment_revision=True)
    revision_after_same_save = state_module.get_audit_setup_revision()

    updated_setup = copy.deepcopy(saved_setup)
    updated_setup["company_and_facility_profile"]["company_name"] = "Beta Co"
    state_module.set_audit_setup(updated_setup, user_saved=True, increment_revision=True)
    revision_after_change = state_module.get_audit_setup_revision()

    assert revision_after_first_save > 0
    assert revision_after_same_save == revision_after_first_save
    assert revision_after_change == revision_after_same_save + 1


def test_evidence_intake_resolution_keeps_required_profile_fields_meaningful() -> None:
    client = MockApiClient()
    adapted = adapt_analysis_response(client.analyze("gap_path"))

    effective_setup = resolve_audit_setup(
        session_setup={},
        response_setup=adapted.get("audit_setup"),
        prepared_setup=client.load_audit_setup(),
        session_is_user_saved=False,
    )

    profile = effective_setup.get("company_and_facility_profile", {})
    required_fields = [
        "company_name",
        "facility_name",
        "facility_address",
        "company_facility_identifier",
        "industry",
        "facility_type",
        "reporting_period",
    ]

    for field in required_fields:
        assert _is_meaningful_text(profile.get(field)), f"Expected meaningful value for {field}"


def test_user_saved_setup_persists_after_prepared_workflow_resolution() -> None:
    client = MockApiClient()
    session_setup = client.load_audit_setup()
    session_setup["company_and_facility_profile"]["company_name"] = "Temporary Test Value"

    adapted = adapt_analysis_response(client.analyze("gap_path"))
    effective_setup = resolve_audit_setup(
        session_setup=session_setup,
        response_setup=adapted.get("audit_setup"),
        prepared_setup=client.load_audit_setup(),
        session_is_user_saved=True,
    )

    profile = effective_setup.get("company_and_facility_profile", {})
    assert profile.get("company_name") == "Temporary Test Value"


def test_source_contract_removed_workflow_progress_renderer_from_active_pages() -> None:
    active_pages = [
        "app.py",
        "pages/1_Audit_Setup.py",
        "pages/2_Evidence_Intake.py",
        "pages/3_Extraction_Review.py",
        "pages/4_Validation.py",
        "pages/5_Calculation_and_Reconciliation.py",
        "pages/6_Gap_Analysis.py",
    ]

    for path in active_pages:
        source = Path(path).read_text(encoding="utf-8")
        assert "render_workflow_progress" not in source

    workflow_source = Path("src/ui/workflow.py").read_text(encoding="utf-8")
    assert "def render_workflow_progress" not in workflow_source
    assert "WORKFLOW_STEPS" not in workflow_source
