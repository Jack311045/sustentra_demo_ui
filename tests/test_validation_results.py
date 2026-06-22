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
