from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest


jsonschema = pytest.importorskip("jsonschema")


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def test_canonical_mock_audit_setup_validates() -> None:
    schema = _read_json("schemas/audit_setup.schema.json")
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    jsonschema.validate(instance=payload, schema=schema)


def test_assurance_level_rejects_unsupported_values() -> None:
    schema = _read_json("schemas/audit_setup.schema.json")
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    invalid_payload = copy.deepcopy(payload)
    invalid_payload["regulation_and_verification"]["assurance_level"] = "Moderate assurance"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_payload, schema=schema)


def test_consolidation_approach_rejects_unsupported_values() -> None:
    schema = _read_json("schemas/audit_setup.schema.json")
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    invalid_payload = copy.deepcopy(payload)
    invalid_payload["reporting_boundary"]["consolidation_approach"] = "Dual control"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_payload, schema=schema)


def test_materiality_absolute_presence_matches_schema_design() -> None:
    schema = _read_json("schemas/audit_setup.schema.json")
    payload = _read_json("data/demo/mock_outputs/mock_audit_setup.json")

    assert payload["materiality_and_thresholds"].get("materiality_absolute")

    materiality_schema = schema["properties"]["materiality_and_thresholds"]
    required_fields = materiality_schema.get("required", [])
    assert "materiality_absolute" in required_fields
