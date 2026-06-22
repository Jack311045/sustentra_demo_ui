from __future__ import annotations

import json
from pathlib import Path


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

    assert "duns_number" in profile
    assert profile["duns_number"] in {"Needs confirmation", "", None}


def test_analysis_response_includes_audit_setup() -> None:
    payload = _read_json("data/demo/mock_outputs/mock_analysis_response.json")

    assert "audit_setup" in payload
    assert isinstance(payload["audit_setup"], dict)
