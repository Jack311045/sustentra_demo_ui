from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_validation_results_shape() -> None:
    results = _read_json("data/demo/mock_outputs/mock_validation_results.json")

    assert isinstance(results, list)
    assert len(results) >= 1

    for record in results:
        assert isinstance(record.get("validation_id"), str)
        assert isinstance(record.get("record_label"), str)
        assert isinstance(record.get("checks"), list)
        assert isinstance(record.get("overall_status"), str)


def test_validation_includes_pass_and_fail_checks() -> None:
    results = _read_json("data/demo/mock_outputs/mock_validation_results.json")
    statuses = []
    for record in results:
        for check in record.get("checks", []):
            if isinstance(check, dict):
                statuses.append(str(check.get("status") or "").lower())

    assert "pass" in statuses
    assert "fail" in statuses
    assert "flag" in statuses


def test_october_validation_has_reconciliation_failure() -> None:
    results = _read_json("data/demo/mock_outputs/mock_validation_results.json")
    record = next(item for item in results if item.get("validation_id") == "VAL-NG-2023-010")

    check_ids = {str(check.get("check_id")) for check in record.get("checks", []) if isinstance(check, dict)}
    assert "workbook_reconciliation" in check_ids

    mismatch_check = next(
        check
        for check in record.get("checks", [])
        if isinstance(check, dict) and check.get("check_id") == "workbook_reconciliation"
    )
    assert str(mismatch_check.get("status")) == "fail"


def test_linked_gap_ticket_ids_are_set_only_on_mapped_exception_checks() -> None:
    results = _read_json("data/demo/mock_outputs/mock_validation_results.json")

    expected_links = {
        ("VAL-NG-2023-010", "workbook_reconciliation"): "GT-DEMO-GAP-003",
        ("VAL-BLR003-2023-009", "factor_alignment"): "GT-DEMO-GAP-005",
        ("VAL-LAB-2023-001", "sampling_chain"): "GT-DEMO-GAP-006",
        ("VAL-NG-2023-012", "period_cutoff"): "GT-DEMO-GAP-009",
    }

    for record in results:
        validation_id = str(record.get("validation_id") or "")
        for check in record.get("checks", []):
            if not isinstance(check, dict):
                continue

            check_id = str(check.get("check_id") or "")
            key = (validation_id, check_id)
            linked_id = check.get("linked_gap_ticket_id")

            if key in expected_links:
                assert linked_id == expected_links[key]
            else:
                assert "linked_gap_ticket_id" not in check
