from __future__ import annotations

import json
from pathlib import Path

from src.api.adapters import normalize_audit_setup


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_mock_audit_setup_sections_exist() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    required_sections = [
        "company_and_facility_profile",
        "reporting_boundary",
        "regulation_and_verification",
        "materiality_and_thresholds",
        "engagement_details",
        "methodology_defaults",
    ]
    for section in required_sections:
        assert section in payload
        assert isinstance(payload[section], dict)


def test_unknown_values_not_invented() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")
    profile = payload["company_and_facility_profile"]
    materiality = payload["materiality_and_thresholds"]
    engagement = payload["engagement_details"]

    assert "duns_number" in profile
    assert profile["duns_number"] == "00-123-4567"
    assert materiality.get("reporting_threshold") == "1,000 tCO2e (organizational reporting threshold)"
    assert engagement.get("auditor_reviewer") == "Sustentra prepared-demo reviewer"


def test_audit_setup_fixture_includes_client_contact_fields() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")
    profile = payload["company_and_facility_profile"]

    assert profile.get("client_contact_name") == "Dana Whitfield"
    assert profile.get("client_contact_email") == "dana.whitfield@ab-baldwinsville.example.com"


def test_analysis_response_includes_audit_setup() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_analysis_response.json")

    assert "audit_setup" in payload
    assert isinstance(payload["audit_setup"], dict)


def test_normalize_legacy_operational_control_migrates() -> None:
    normalized = normalize_audit_setup(
        {
            "reporting_boundary": {
                "scope_1": True,
                "scope_2": False,
                "scope_3": False,
                "boundary_type": "Facility",
                "operational_control": True,
                "ownership_control": False,
            }
        }
    )

    boundary = normalized["reporting_boundary"]
    assert boundary.get("consolidation_approach") == "Operational control"
    assert "operational_control" not in boundary
    assert "ownership_control" not in boundary


def test_normalize_preserves_canonical_consolidation() -> None:
    normalized = normalize_audit_setup(
        {
            "reporting_boundary": {
                "scope_1": True,
                "scope_2": False,
                "scope_3": False,
                "boundary_type": "Facility",
                "consolidation_approach": "Equity share",
            }
        }
    )
    assert normalized["reporting_boundary"]["consolidation_approach"] == "Equity share"


def test_normalize_adds_defaults_for_assurance_and_absolute_materiality() -> None:
    normalized = normalize_audit_setup(
        {
            "regulation_and_verification": {
                "primary_regulation": "NY Part 253",
                "additional_frameworks": ["NY Part 253", "EPA Part 98"],
                "verification_standard": "ISSA 5000",
            },
            "materiality_and_thresholds": {
                "material_misstatement_percentage": "5%",
            },
        }
    )

    regulation = normalized["regulation_and_verification"]
    materiality = normalized["materiality_and_thresholds"]
    assert regulation.get("assurance_level") == "Limited assurance"
    assert regulation.get("additional_frameworks") == ["EPA Part 98"]
    assert materiality.get("materiality_absolute") == "750 tCO2e"
