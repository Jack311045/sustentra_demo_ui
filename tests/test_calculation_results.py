from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_calculation_results_include_computed_and_not_computed() -> None:
    results = _read_json("data/demo/mock_outputs/mock_calculation_results.json")

    assert isinstance(results, list)
    computed = [item for item in results if item.get("calculation_status") == "computed"]
    not_computed = [
        item for item in results if item.get("calculation_status") == "not_computed_in_current_demo"
    ]

    assert computed
    assert not_computed


def test_october_natural_gas_calculation_has_variance() -> None:
    results = _read_json("data/demo/mock_outputs/mock_calculation_results.json")
    record = next(item for item in results if item.get("calculation_id") == "CALC-NG-2023-010")

    assert record.get("recalculated_co2e_mt") is not None
    assert record.get("workbook_co2e_mt") is not None
    assert record.get("difference_mt") is not None
    assert float(record.get("difference_mt")) > 0
    assert float(record.get("variance_percent")) > 0


def test_not_computed_records_include_reason() -> None:
    results = _read_json("data/demo/mock_outputs/mock_calculation_results.json")
    not_computed = [
        item for item in results if item.get("calculation_status") == "not_computed_in_current_demo"
    ]

    assert all(isinstance(item.get("reason"), str) and item.get("reason") for item in not_computed)


def test_reconciliation_summary_exists() -> None:
    summary = _read_json("data/demo/mock_outputs/mock_reconciliation_summary.json")

    assert "reconciliation_status" in summary
    assert "coverage_note" in summary


def test_calculation_page_handoff_references_gt_demo_gap_tickets() -> None:
    source = Path("pages/5_Calculation_and_Reconciliation.py").read_text(encoding="utf-8-sig")

    assert "GT-DEMO-GAP-003" in source
    assert "Register finding GT-DEMO-GAP-003" in source
    assert "GT-DEMO-GAP-010 remains under review pending regulatory basis confirmation." in source
