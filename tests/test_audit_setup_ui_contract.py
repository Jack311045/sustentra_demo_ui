from __future__ import annotations

import json
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def test_audit_setup_replaces_prepared_placeholders() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    assert payload["company_and_facility_profile"]["duns_number"] != "Needs confirmation"
    assert payload["materiality_and_thresholds"]["reporting_threshold"] != "Prepared demo threshold - Needs confirmation"
    assert payload["engagement_details"]["auditor_reviewer"] != "Needs confirmation"


def test_reporting_criteria_and_assurance_sections_are_separate() -> None:
    source = _read("pages/1_Audit_Setup.py")

    assert "Reporting criteria" in source
    assert "Assurance standard" in source
    assert 'CRITERIA_OPTIONS = ["NY Part 253", "EPA Part 98", "GHG Protocol"]' in source
    assert 'ASSURANCE_STANDARD_OPTIONS = ["ISSA 5000", "ISO 14064-3"]' in source


def test_exactly_one_consolidation_approach_is_saved() -> None:
    source = _read("pages/1_Audit_Setup.py")

    assert "Consolidation approach" in source
    assert "st.selectbox(" in source
    assert '"consolidation_approach": consolidation_approach' in source
    assert '"ownership_control": ownership_control' not in source
    assert '"operational_control": operational_control' not in source


def test_assurance_level_and_absolute_materiality_fields_exist() -> None:
    source = _read("pages/1_Audit_Setup.py")

    assert "Assurance level" in source
    assert "Limited assurance" in source
    assert "Reasonable assurance" in source
    assert "Material misstatement (absolute)" in source
    assert '"materiality_absolute": materiality_absolute' in source


def test_disclosure_and_advanced_json_are_preserved_without_workflow_boxes() -> None:
    source = _read("pages/1_Audit_Setup.py")

    assert "render_workflow_progress" not in source
    assert "render_prepared_demo_disclosure()" in source
    assert "Advanced setup JSON" in source
    assert "build_engagement_expectation_summary(" in source


def test_client_contact_fields_render_and_save() -> None:
    source = _read("pages/1_Audit_Setup.py")

    assert "Client contact name" in source
    assert "Client contact email" in source
    assert 'key="audit_client_contact_name"' in source
    assert 'key="audit_client_contact_email"' in source
    assert '"client_contact_name": client_contact_name' in source
    assert '"client_contact_email": client_contact_email' in source
