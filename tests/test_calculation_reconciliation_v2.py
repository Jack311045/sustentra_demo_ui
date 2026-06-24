from __future__ import annotations

import ast
import json
import py_compile
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.extraction_review import get_reviewable_evidence_records

PAGE_5 = Path("pages/5_Calculation_and_Reconciliation.py")
GAP_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _page_source() -> str:
    return PAGE_5.read_text(encoding="utf-8-sig")


def _page_identifiers() -> set[str]:
    tree = ast.parse(_page_source())
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.alias):
            identifiers.add((node.asname or node.name).split(".")[0])
    return identifiers


def _collect_rendered_text(at: AppTest) -> str:
    parts: list[str] = []
    for group in ("markdown", "caption", "text", "success", "warning", "error", "info"):
        for item in getattr(at, group):
            value = getattr(item, "value", None)
            if isinstance(value, str) and value.strip():
                parts.append(value)
    for metric in at.metric:
        parts.append(str(metric.label))
        parts.append(str(metric.value))
    for button in at.button:
        if isinstance(button.label, str) and button.label.strip():
            parts.append(button.label)
    for expander in at.expander:
        label = getattr(expander, "label", None)
        if isinstance(label, str) and label.strip():
            parts.append(label)
    return "\n".join(parts)


def _completed_review_overlay(analysis_response: dict) -> dict:
    overlay: dict = {}
    for record in get_reviewable_evidence_records(analysis_response):
        evidence_id = str(record.get("evidence_id") or "")
        extracted = record.get("extracted_fields") if isinstance(record.get("extracted_fields"), dict) else {}
        if not evidence_id or not extracted:
            continue
        overlay[evidence_id] = {field_key: {"status": "Accepted"} for field_key in extracted}
    return overlay


def _run_page5() -> tuple[AppTest, dict]:
    response = _read_json(GAP_PATH)
    at = AppTest.from_file(str(PAGE_5), default_timeout=45)
    at.session_state["analysis_response"] = deepcopy(response)
    at.session_state["audit_setup"] = deepcopy(response.get("audit_setup") or {})
    at.session_state["reviewed_extraction_fields"] = _completed_review_overlay(response)
    at.run()
    return at, response


def _metrics_map(at: AppTest) -> dict[str, str]:
    return {metric.label: str(metric.value) for metric in at.metric}


def _click_by_key(at: AppTest, key: str) -> AppTest:
    for button in at.button:
        if getattr(button, "key", "") == key:
            button.click().run()
            return at
    raise AssertionError(f"Expected button key '{key}'")


def test_page5_compiles() -> None:
    py_compile.compile(str(PAGE_5), doraise=True)


def test_page5_keeps_safety_contracts() -> None:
    source = _page_source()
    identifiers = _page_identifiers()

    for forbidden in ("set_analysis_response", "MockApiClient", "adapt_analysis_response"):
        assert forbidden not in identifiers

    assert "review_complete" not in identifiers
    assert "review_complete" not in source
    assert "get_extraction_review_progress" in source
    assert "Return to Extraction Review" in source
    assert "resolve_emission_factor" in source
    assert "resolve_formulas" in source
    assert "resolve_gwp_set" in source


def test_queue_counts_are_derived_not_hardcoded() -> None:
    at, response = _run_page5()
    assert len(at.exception) == 0

    results = [item for item in (response.get("calculation_results") or []) if isinstance(item, dict)]
    expected_attempted = len(results)
    expected_computed = len(
        [
            item
            for item in results
            if str(item.get("calculation_status") or "").strip().lower() == "computed"
        ]
    )
    expected_held = len(
        [
            item
            for item in results
            if str(item.get("calculation_status") or "").strip().lower() == "not_computed_in_current_demo"
        ]
    )

    metrics = _metrics_map(at)
    assert metrics.get("Attempted") == str(expected_attempted)
    assert metrics.get("Computed") == str(expected_computed)
    assert metrics.get("Held") == str(expected_held)

    rendered_text = _collect_rendered_text(at)
    assert (
        f"{expected_attempted} records attempted · {expected_computed} computed · "
        f"{expected_held} held for validated input"
    ) in rendered_text

    source = _page_source()
    assert "3 records attempted" not in source
    assert "1 computed" not in source
    assert "2 held for validated input" not in source


def test_held_records_render_before_computed_and_use_specific_reasons() -> None:
    at, _ = _run_page5()
    rendered_text = _collect_rendered_text(at)

    assert "BLR-003 biomass activity" in rendered_text
    assert "Natural gas — December cross-year period" in rendered_text
    assert "Ready to recalculate" in rendered_text

    assert rendered_text.index("BLR-003 biomass activity") < rendered_text.index("Ready to recalculate")

    assert (
        "Held — requires validated biomass heat-content conversion and a biomass-aligned emission factor "
        "before MMBtu normalization."
    ) in rendered_text
    assert (
        "Held — requires allocation of the service period between the 2023 and 2024 reporting years."
    ) in rendered_text
    assert "Needs confirmation" not in rendered_text


def test_held_validation_actions_set_selected_validation_id() -> None:
    at, _ = _run_page5()
    assert len(at.exception) == 0

    at = _click_by_key(at, "held_validation_CALC-BLR003-2023-009_VAL-BLR003-2023-009")
    assert len(at.exception) == 0
    assert "selected_validation_id" in at.session_state
    assert at.session_state["selected_validation_id"] == "VAL-BLR003-2023-009"

    at = _run_page5()[0]
    at = _click_by_key(at, "held_validation_CALC-BLR003-2023-009_VAL-LAB-2023-001")
    assert len(at.exception) == 0
    assert "selected_validation_id" in at.session_state
    assert at.session_state["selected_validation_id"] == "VAL-LAB-2023-001"

    at = _run_page5()[0]
    at = _click_by_key(at, "held_validation_CALC-NG-2023-012_VAL-NG-2023-012")
    assert len(at.exception) == 0
    assert "selected_validation_id" in at.session_state
    assert at.session_state["selected_validation_id"] == "VAL-NG-2023-012"


def test_run_recalculation_reveals_five_steps_and_keeps_prepared_data_unchanged() -> None:
    at, response = _run_page5()
    baseline_response = deepcopy(response)

    before = _collect_rendered_text(at)
    assert "Step 1 — Activity" not in before
    assert "Step 2 — Emission factor" not in before
    assert "Step 3 — Per-gas emissions" not in before
    assert "Step 4 — GWP conversion" not in before
    assert "Step 5 — Recalculated result" not in before
    assert "This variance maps to finding GT-DEMO-GAP-003." not in before

    run_button = next(button for button in at.button if button.label == "Run recalculation")
    run_button.click().run()
    assert len(at.exception) == 0

    after = _collect_rendered_text(at)
    for required in (
        "Step 1 — Activity",
        "Step 2 — Emission factor",
        "Step 3 — Per-gas emissions",
        "Step 4 — GWP conversion",
        "Step 5 — Recalculated result",
        "1,492.5 tCO2e",
        "This variance maps to finding GT-DEMO-GAP-003.",
    ):
        assert required in after

    prepared_october = next(
        item
        for item in baseline_response["calculation_results"]
        if item.get("calculation_id") == "CALC-NG-2023-010"
    )
    active_october = next(
        item
        for item in at.session_state["analysis_response"]["calculation_results"]
        if item.get("calculation_id") == "CALC-NG-2023-010"
    )
    assert active_october["recalculated_co2e_mt"] == prepared_october["recalculated_co2e_mt"]
    assert active_october["workbook_co2e_mt"] == prepared_october["workbook_co2e_mt"]
    assert active_october["difference_mt"] == prepared_october["difference_mt"]
    assert at.session_state["analysis_response"] == baseline_response


def test_primary_view_uses_plain_language_and_advanced_contains_raw_ids() -> None:
    at, _ = _run_page5()
    before = _collect_rendered_text(at)
    assert "EPA_HUB_2025_SC_NATURAL_GAS" not in before
    assert "IPCC_AR6_100_YEAR_COMBUSTION" not in before
    assert "R-001" not in before
    assert "R-002" not in before

    run_button = next(button for button in at.button if button.label == "Run recalculation")
    run_button.click().run()

    rendered_text = _collect_rendered_text(at)
    assert "EPA Emission Factors Hub 2025" in rendered_text
    assert "Stationary combustion — natural gas" in rendered_text
    assert "IPCC AR6 — 100-year GWP" in rendered_text

    source = _page_source()
    assert "Advanced calculation details" in source
    assert "Raw factor ID" in source
    assert "Raw GWP ID" in source
    assert "Raw formula/reconciliation rule IDs" in source


def test_materiality_and_gap_handoff_appear_after_reveal_and_use_audit_setup_thresholds() -> None:
    at, _ = _run_page5()
    before = _collect_rendered_text(at)
    assert "Relative variance:" not in before
    assert "Absolute difference:" not in before
    assert "Register finding GT-DEMO-GAP-003" not in before

    run_button = next(button for button in at.button if button.label == "Run recalculation")
    run_button.click().run()
    assert len(at.exception) == 0

    after = _collect_rendered_text(at)
    assert "Relative variance: 900% versus the 5% threshold — breached." in after
    assert "Absolute difference: 13,432.6 tCO2e versus the 750 tCO2e threshold — breached." in after
    assert "Register finding GT-DEMO-GAP-003" in after

    gap_button = next(button for button in at.button if button.label == "Register finding GT-DEMO-GAP-003")
    gap_button.click().run()
    assert len(at.exception) == 0
    assert "selected_gap_ticket_id" in at.session_state
    assert at.session_state["selected_gap_ticket_id"] == "GT-DEMO-GAP-003"
    assert "created_gap_ticket_ids" in at.session_state
    assert "GT-DEMO-GAP-003" in at.session_state["created_gap_ticket_ids"]
