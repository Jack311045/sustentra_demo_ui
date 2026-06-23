"""Tests for the Extraction Review (Page 3) and Calculation & Reconciliation
(Page 5) feature: derived review gate, field-confidence projection, dynamic
library resolution, materiality parsing, and source-of-truth protection.

These tests deliberately avoid importing the Streamlit pages or ``src.ui.state``
(which require a Streamlit runtime). They exercise the pure helper modules and
validate the page source statically.
"""

from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

from src.ui.extraction_review import (
    APPROVED_REVIEW_STATUSES,
    BUCKET_FAIL,
    BUCKET_NEEDS_REVIEW,
    BUCKET_PASS,
    FINAL_REVIEW_STATUSES,
    UNCONFIRMED_STATUS,
    bucket_from_ui_status,
    get_extraction_review_progress,
    get_field_confidence,
    get_field_review_status,
    get_reviewable_evidence_records,
    is_record_approved,
    normalize_review_status,
    record_confidence_bucket,
)
from src.ui.libraries import (
    emission_factor_library_source_label,
    factor_energy_basis,
    factor_reference_label,
    gwp_reference_label,
    gwp_values,
    parse_leading_number,
    parse_materiality_absolute,
    parse_materiality_percent,
    resolve_calculation_template,
    resolve_emission_factor,
    resolve_formula,
    resolve_formulas,
    resolve_gwp_set,
)


PAGE_3 = Path("pages/3_Extraction_Review.py")
PAGE_5 = Path("pages/5_Calculation_and_Reconciliation.py")
CALC_PATH = Path("data/demo/mock_outputs/mock_calculation_results.json")
RECON_PATH = Path("data/demo/mock_outputs/mock_reconciliation_summary.json")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sample_record(ui_status: str = "pass") -> dict:
    return {
        "evidence_id": "EV-TEST-001",
        "ui_status": ui_status,
        "extracted_fields": {"usage_value": 100, "period": "October"},
    }


# --- Source-of-truth protection ----------------------------------------------


def _page_symbols(page: Path) -> tuple[set[str], set[str]]:
    """Return (referenced identifiers, exact string constants) ignoring prose.

    Docstrings/comments are excluded by walking the AST: identifiers come from
    Name/Attribute/import nodes, and string constants are matched exactly so the
    explanatory module docstring does not trigger false positives.
    """
    tree = ast.parse(page.read_text(encoding="utf-8-sig"))
    identifiers: set[str] = set()
    constants: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.alias):
            identifiers.add((node.asname or node.name).split(".")[0])
            identifiers.add(node.name.split(".")[-1])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            constants.add(node.value)
    return identifiers, constants


def test_pages_do_not_mutate_analysis_response() -> None:
    forbidden_calls = ["set_analysis_response", "MockApiClient", "adapt_analysis_response"]
    for page in (PAGE_3, PAGE_5):
        identifiers, constants = _page_symbols(page)
        for token in forbidden_calls:
            assert token not in identifiers, f"{page.name} must not use {token!r}"
        # No persisted review_complete flag (identifier or exact state key).
        assert "review_complete" not in identifiers, f"{page.name} must not use review_complete"
        assert "review_complete" not in constants, f"{page.name} must not persist review_complete"


def test_pages_do_not_emit_needs_confirmation_placeholder() -> None:
    for page in (PAGE_3, PAGE_5):
        assert "Needs confirmation" not in page.read_text(encoding="utf-8-sig")


def test_pages_compile() -> None:
    py_compile.compile(str(PAGE_3), doraise=True)
    py_compile.compile(str(PAGE_5), doraise=True)


# --- Review status / confidence helpers --------------------------------------


def test_default_field_status_is_unconfirmed() -> None:
    assert get_field_review_status({}, "usage_value") == UNCONFIRMED_STATUS
    assert normalize_review_status(None) == UNCONFIRMED_STATUS


def test_final_and_approved_status_sets() -> None:
    assert UNCONFIRMED_STATUS not in FINAL_REVIEW_STATUSES
    assert "Accepted" in APPROVED_REVIEW_STATUSES
    assert "Edited" in APPROVED_REVIEW_STATUSES
    assert "Rejected" not in APPROVED_REVIEW_STATUSES


def test_bucket_from_ui_status_mapping() -> None:
    assert bucket_from_ui_status("pass", None) == BUCKET_PASS
    assert bucket_from_ui_status("needs_review", None) == BUCKET_NEEDS_REVIEW
    assert bucket_from_ui_status("flagged", None) == BUCKET_FAIL


def test_field_confidence_prefers_explicit_override() -> None:
    record = _sample_record("pass")
    record["field_confidence"] = {"usage_value": {"bucket": "fail", "score": 0.2}}
    conf = get_field_confidence(record, "usage_value")
    assert conf["bucket"] == BUCKET_FAIL
    assert conf["score"] == 0.2


def test_field_confidence_falls_back_to_ui_status() -> None:
    conf = get_field_confidence(_sample_record("flagged"), "usage_value")
    assert conf["bucket"] == BUCKET_FAIL
    assert conf["score"] is None
    assert conf["basis"] == "prepared_demo"


def test_record_bucket_is_worst_field() -> None:
    record = _sample_record("pass")
    record["field_confidence"] = {"period": {"bucket": "needs_review"}}
    assert record_confidence_bucket(record) == BUCKET_NEEDS_REVIEW


# --- Reviewable records & derived gate ----------------------------------------


def test_reviewable_records_exclude_internal_routing() -> None:
    response = {
        "evidence_results": [
            _sample_record("pass"),
            {"evidence_id": "EV-PACK-INDEX-2023-000", "extracted_fields": {"x": 1}},
            {"evidence_id": "EV-NO-FIELDS", "extracted_fields": {}},
        ]
    }
    reviewable = get_reviewable_evidence_records(response)
    ids = {r["evidence_id"] for r in reviewable}
    assert ids == {"EV-TEST-001"}


def test_gate_incomplete_until_all_fields_final() -> None:
    response = {"evidence_results": [_sample_record("pass")]}

    progress = get_extraction_review_progress(response, {})
    assert progress["total_fields"] == 2
    assert progress["confirmed_fields"] == 0
    assert progress["is_complete"] is False

    reviewed = {
        "EV-TEST-001": {
            "usage_value": {"status": "Accepted"},
            "period": {"status": "Edited", "edited_value": "Oct 2023"},
        }
    }
    progress = get_extraction_review_progress(response, reviewed)
    assert progress["confirmed_fields"] == 2
    assert progress["is_complete"] is True
    assert progress["approved_record_count"] == 1


def test_rejected_field_completes_gate_but_not_approval() -> None:
    response = {"evidence_results": [_sample_record("pass")]}
    reviewed = {
        "EV-TEST-001": {
            "usage_value": {"status": "Accepted"},
            "period": {"status": "Rejected"},
        }
    }
    progress = get_extraction_review_progress(response, reviewed)
    assert progress["is_complete"] is True
    assert progress["approved_record_count"] == 0


def test_is_record_approved_requires_all_fields() -> None:
    record = _sample_record("pass")
    reviewed = {"usage_value": {"status": "Accepted"}}
    assert is_record_approved(record, reviewed) is False
    reviewed["period"] = {"status": "Accepted"}
    assert is_record_approved(record, reviewed) is True


# --- Dynamic library resolution ----------------------------------------------


def test_resolve_formulas_for_natural_gas() -> None:
    for fid in ("R-001", "R-002", "R-003"):
        assert resolve_formula(fid) is not None, fid
    resolved = resolve_formulas(["R-001", "R-002"])
    assert [r["formula_id"] for r in resolved] == ["R-001", "R-002"]


def test_resolve_emission_factor_natural_gas() -> None:
    factor = resolve_emission_factor("EPA_HUB_2025_SC_NATURAL_GAS")
    assert factor is not None
    basis = factor_energy_basis(factor)
    assert basis["co2"]["value"] == 53.06
    assert basis["ch4"]["value"] == 1.0
    assert basis["n2o"]["value"] == 0.1


def test_resolve_gwp_set_combustion_values() -> None:
    gwp_set = resolve_gwp_set("IPCC_AR6_100_YEAR_COMBUSTION")
    values = gwp_values(gwp_set)
    assert values["CO2"] == 1
    assert values["CH4_NON_FOSSIL"] == 27.0
    assert values["N2O"] == 273


def test_default_gwp_set_resolves_when_id_missing() -> None:
    assert resolve_gwp_set(None)["gwp_set_id"] == "IPCC_AR6_100_YEAR_COMBUSTION"


def test_plain_language_factor_and_gwp_labels() -> None:
    assert (
        factor_reference_label("EPA_HUB_2025_SC_NATURAL_GAS")
        == "EPA Emission Factors Hub 2025 — stationary combustion, natural gas"
    )
    assert gwp_reference_label("IPCC_AR6_100_YEAR_COMBUSTION") == "IPCC AR6 — 100-year GWP"


def test_emission_factor_library_source_label_and_template_lookup() -> None:
    source_label = emission_factor_library_source_label()
    assert "Sustentra emission factor library" in source_label
    assert "v1.0.0" in source_label

    template = resolve_calculation_template("ENERGY_BASIS_STATIONARY_COMBUSTION")
    assert template is not None
    assert template.get("template_id") == "ENERGY_BASIS_STATIONARY_COMBUSTION"
    assert isinstance(template.get("steps"), list)


def test_materiality_parsing_from_audit_setup() -> None:
    audit_setup = {
        "materiality_and_thresholds": {
            "materiality_absolute": "750 tCO2e",
            "material_misstatement_percentage": "5%",
        }
    }
    assert parse_materiality_absolute(audit_setup) == 750.0
    assert parse_materiality_percent(audit_setup) == 5.0
    assert parse_leading_number("13,432.60647 tCO2e") == 13432.60647


# --- Recalculation integrity --------------------------------------------------


def test_natural_gas_recalculation_matches_prepared_record() -> None:
    records = _read_json(CALC_PATH)
    october = next(r for r in records if r.get("calculation_id") == "CALC-NG-2023-010")

    factor = resolve_emission_factor(october["factor_id"])
    basis = factor_energy_basis(factor)
    gwp = gwp_values(resolve_gwp_set(october["gwp_basis"]))

    activity = october["activity_quantity"]
    co2_kg = activity * basis["co2"]["value"]
    ch4_kg = activity * basis["ch4"]["value"] / 1000
    n2o_kg = activity * basis["n2o"]["value"] / 1000
    co2e_mt = (
        co2_kg * gwp["CO2"] + ch4_kg * gwp["CH4_NON_FOSSIL"] + n2o_kg * gwp["N2O"]
    ) / 1000

    assert co2_kg == october["co2_kg"]
    assert abs(ch4_kg - october["ch4_kg"]) < 1e-6
    assert abs(n2o_kg - october["n2o_kg"]) < 1e-6
    assert abs(co2e_mt - october["recalculated_co2e_mt"]) < 1e-3


def test_reconciliation_summary_punchline_values() -> None:
    summary = _read_json(RECON_PATH)
    assert abs(summary["reported_scope_1_mtco2e"] - 14925.1183) < 1e-3
    assert abs(summary["recalculated_scope_1_mtco2e"] - 1492.51183) < 1e-3
    assert abs(summary["absolute_difference_mtco2e"] - 13432.60647) < 1e-3
    assert summary["variance_percent"] == 900.0
