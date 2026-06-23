from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.validation import (
    derive_monthly_evidence_coverage,
    format_monthly_coverage_banner,
    mapped_check_pairs,
    normalize_validation_status,
    resolve_check_display,
    sort_validation_checks,
    sort_validation_records,
    trace_note_for_check,
)

PAGE_4 = Path("pages/4_Validation.py")
GAP_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")
CLEAN_PATH = Path("data/demo/mock_outputs/mock_analysis_response_clean_path.json")
AUDIT_SETUP_PATH = Path("data/demo/mock_outputs/mock_audit_setup.json")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _page_source() -> str:
    return PAGE_4.read_text(encoding="utf-8-sig")


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
    for expander in at.expander:
        label = getattr(expander, "label", None)
        if isinstance(label, str) and label.strip():
            parts.append(label)
    return "\n".join(parts)


def _run_page4(analysis_response: dict) -> AppTest:
    at = AppTest.from_file(str(PAGE_4), default_timeout=30)
    at.session_state["analysis_response"] = analysis_response
    at.session_state["audit_setup"] = _read_json(AUDIT_SETUP_PATH)
    at.run()
    return at


def test_page4_compiles() -> None:
    py_compile.compile(str(PAGE_4), doraise=True)


def test_page4_does_not_use_id_selectbox_or_main_table() -> None:
    source = _page_source()
    assert "st.selectbox(" not in source
    assert "render_validation_table" not in source


def test_page4_has_no_needs_confirmation_placeholder() -> None:
    assert "Needs confirmation" not in _page_source()


def test_page4_does_not_mutate_analysis_response() -> None:
    identifiers = _page_identifiers()
    for token in (
        "set_analysis_response",
        "MockApiClient",
        "adapt_analysis_response",
        "set_selected_validation_id",
    ):
        assert token not in identifiers


def test_status_normalization_case_insensitive() -> None:
    assert normalize_validation_status("PASS") == "pass"
    assert normalize_validation_status("Flag") == "flagged"
    assert normalize_validation_status("FaIl") == "fail"


def test_record_sort_is_exception_first_with_prepared_order_tiebreak() -> None:
    records = _read_json(GAP_PATH)["validation_results"]
    sorted_records = sort_validation_records(records)
    labels = [record["record_label"] for record in sorted_records]
    assert labels == [
        "BLR-003 September biomass record",
        "October natural gas bill",
        "Biomass sampling support",
        "December cross-year bill",
    ]


def test_check_sort_is_exception_first() -> None:
    records = _read_json(GAP_PATH)["validation_results"]
    october = next(record for record in records if record["validation_id"] == "VAL-NG-2023-010")
    sorted_checks = sort_validation_checks(october["checks"])
    assert sorted_checks[0]["check_id"] == "workbook_reconciliation"


def test_exact_mappings_resolve_with_tuple_keys() -> None:
    pairs = mapped_check_pairs()
    assert ("VAL-NG-2023-010", "fuel_identified") in pairs
    assert ("VAL-BLR003-2023-009", "fuel_identified") in pairs

    ng_fuel = resolve_check_display("VAL-NG-2023-010", {"check_id": "fuel_identified", "status": "pass"})
    blr_fuel = resolve_check_display("VAL-BLR003-2023-009", {"check_id": "fuel_identified", "status": "pass"})
    assert ng_fuel["question"] == "Is the fuel natural gas, as expected for this source?"
    assert blr_fuel["question"] == "Is the fuel correctly identified as solid biomass?"


def test_october_mapping_contains_activity_mismatch_only() -> None:
    mapped = resolve_check_display(
        "VAL-NG-2023-010",
        {"check_id": "workbook_reconciliation", "status": "fail"},
    )
    answer = mapped["answer"]
    assert "281,000" in answer
    assert "28,100" in answer
    assert "tCO2e" not in answer
    assert "variance" not in answer.lower()
    assert "materiality" not in answer.lower()
    assert "GAP-003" not in answer


def test_unknown_check_uses_fallback_without_crashing() -> None:
    display = resolve_check_display(
        "VAL-FUTURE-001",
        {
            "check_id": "unknown_rule",
            "label": "Data lineage",
            "status": "flag",
            "observed": "Link missing",
            "expected": "Trace present",
            "explanation": "Needs follow-up",
        },
    )
    assert display["question"].startswith("Is ")
    assert display["answer"]
    assert "Status unavailable" not in display["answer"]


def test_monthly_coverage_derivation_and_banner() -> None:
    gap = _read_json(GAP_PATH)
    setup = _read_json(AUDIT_SETUP_PATH)
    coverage = derive_monthly_evidence_coverage(gap, setup)

    assert coverage["received_count"] == 12
    assert coverage["expected_count"] == 12
    assert coverage["fully_within_count"] == 11
    assert coverage["cross_year_count"] == 1

    banner = format_monthly_coverage_banner(coverage)
    assert "12 / 12" in banner
    assert "11 fully within 2023" in banner
    assert "1 bill require cutoff allocation" in banner


def test_trace_notes_from_audit_setup() -> None:
    setup = _read_json(AUDIT_SETUP_PATH)
    facility_note = trace_note_for_check("facility_match", setup)
    period_note = trace_note_for_check("period_cutoff", setup)
    method_note = trace_note_for_check("factor_alignment", setup)

    assert facility_note == (
        "From engagement setup: selected facility is Anheuser-Busch Baldwinsville Brewery."
    )
    assert period_note == "From engagement setup: reporting period is 2023-01-01 to 2023-12-31."
    assert "Scope 1 stationary combustion" in (method_note or "")


def test_page4_gap_path_renders_cards_exception_first() -> None:
    at = _run_page4(_read_json(GAP_PATH))
    assert len(at.exception) == 0

    # Four top-level validation cards should appear in exception-first order.
    expected = [
        "BLR-003 September biomass record",
        "October natural gas bill",
        "Biomass sampling support",
        "December cross-year bill",
    ]
    labels = [exp.label for exp in at.expander if exp.label in expected]
    assert labels[:4] == expected

    rendered_text = _collect_rendered_text(at)
    assert "Validation records" in rendered_text
    assert "Pass" in rendered_text
    assert "Flagged" in rendered_text
    assert "Fail" in rendered_text
    assert "Monthly evidence coverage: 12 / 12 bills received" in rendered_text
    assert "Needs confirmation" not in rendered_text


def test_page4_clean_path_shows_graceful_no_validation_message() -> None:
    at = _run_page4(_read_json(CLEAN_PATH))
    assert len(at.exception) == 0
    rendered_text = _collect_rendered_text(at)
    assert "No validation results are available in this prepared dataset." in rendered_text


def test_page4_keeps_advanced_json_collapsed_entry() -> None:
    source = _page_source()
    assert "Advanced validation JSON" in source
    assert "expanded=False" in source
