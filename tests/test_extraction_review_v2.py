"""Tests for the Extraction Review v2.1 redesign (Page 3).

Covers the new pure helpers (friendly value formatting, source-snippet
sanitization, one-shot bulk acceptance, completed-record progress), the DOCX
section preview extraction, manifest section identifiers, and the static
contract of the redesigned page (no ``st.rerun``, no wrap-style injection, no
five-column action row, callbacks instead of inline mutation).

These tests deliberately avoid importing the Streamlit page or ``src.ui.state``
(which require a Streamlit runtime). They exercise the pure helpers and validate
the page source statically.
"""

from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.ui.extraction_review import (
    UNCONFIRMED_STATUS,
    build_bulk_accept_update,
    get_extraction_review_progress,
    record_display_name,
    record_period_label,
    resolve_field_source_reference,
)
from src.ui.formatting import format_display_value, sanitize_source_snippet

PAGE_3 = Path("pages/3_Extraction_Review.py")
MANIFEST_PATH = Path("data/demo/mock_outputs/evidence_assets_manifest.json")
GAP_PATH = Path("data/demo/mock_outputs/mock_analysis_response_gap_path.json")
DOCX_PATH = Path("data/demo/inputs/evidence/Evidence_Pack_Generated_Review_Pack_Nora.docx")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _record(ui_status: str = "pass") -> dict:
    return {
        "evidence_id": "EV-TEST-001",
        "ui_status": ui_status,
        "extracted_fields": {"usage_value": 100, "period": "October"},
    }


# --- format_display_value -----------------------------------------------------


def test_format_display_value_lists_have_no_brackets_or_quotes() -> None:
    out = format_display_value(["BLR-001", "BLR-002", "GEN-001"])
    assert out == "BLR-001, BLR-002, GEN-001"
    assert "[" not in out and "'" not in out and '"' not in out


def test_format_display_value_bool_and_none() -> None:
    assert format_display_value(True) == "Yes"
    assert format_display_value(False) == "No"
    assert format_display_value(None) == ""


def test_format_display_value_numbers_are_readable() -> None:
    assert format_display_value(28100) == "28,100"
    assert format_display_value(1492.5) == "1,492.5"
    assert format_display_value(100.0) == "100"


def test_format_display_value_dict_is_label_value() -> None:
    out = format_display_value({"sheet_name": "Natural Gas", "cell_or_range": "D12"})
    assert out == "Sheet name: Natural Gas; Cell or range: D12"


def test_format_display_value_str_unchanged() -> None:
    assert format_display_value("Natural Gas") == "Natural Gas"


# --- sanitize_source_snippet --------------------------------------------------


def test_sanitize_strips_leading_evidence_token_and_normalizes() -> None:
    raw = "EV-AGG-2023-001 groups BLR-001, BLR-002, GEN-001 for 2023 annual roll-up."
    assert (
        sanitize_source_snippet(raw)
        == "This worksheet groups BLR-001, BLR-002, and GEN-001 for the 2023 annual roll-up."
    )


def test_sanitize_preserves_unit_identifiers() -> None:
    out = sanitize_source_snippet("EV-AGG-2023-001 groups BLR-001, BLR-002, GEN-001 for 2023 annual roll-up.")
    for unit in ("BLR-001", "BLR-002", "GEN-001"):
        assert unit in out


def test_sanitize_leaves_normal_text_untouched() -> None:
    text = "January natural gas statement; usage 32,400 MMBtu."
    assert sanitize_source_snippet(text) == text


def test_sanitize_handles_empty() -> None:
    assert sanitize_source_snippet(None) == ""
    assert sanitize_source_snippet("") == ""


# --- build_bulk_accept_update -------------------------------------------------


def test_bulk_accept_only_unconfirmed_by_default() -> None:
    records = [_record("pass")]
    updated = build_bulk_accept_update({}, records)
    assert updated["EV-TEST-001"]["usage_value"]["status"] == "Accepted"
    assert updated["EV-TEST-001"]["period"]["status"] == "Accepted"


def test_bulk_accept_preserves_existing_decisions() -> None:
    records = [_record("pass")]
    existing = {
        "EV-TEST-001": {
            "usage_value": {"status": "Rejected"},
            "period": {"status": "Edited", "edited_value": "Oct 2023"},
        }
    }
    updated = build_bulk_accept_update(existing, records)
    assert updated["EV-TEST-001"]["usage_value"]["status"] == "Rejected"
    assert updated["EV-TEST-001"]["period"]["status"] == "Edited"
    assert updated["EV-TEST-001"]["period"]["edited_value"] == "Oct 2023"


def test_bulk_accept_preserves_auditor_added_fields() -> None:
    records = [_record("pass")]
    existing = {
        "EV-TEST-001": {
            "extra_note": {"status": "Edited", "edited_value": "x", "auditor_added": True},
        }
    }
    updated = build_bulk_accept_update(existing, records)
    assert updated["EV-TEST-001"]["extra_note"]["auditor_added"] is True
    assert updated["EV-TEST-001"]["usage_value"]["status"] == "Accepted"


def test_progress_complete_after_bulk_accept() -> None:
    response = {"evidence_results": [_record("pass")]}
    updated = build_bulk_accept_update({}, response["evidence_results"])
    progress = get_extraction_review_progress(response, updated)
    assert progress["is_complete"] is True
    assert progress["completed_record_count"] == 1
    assert "EV-TEST-001" in progress["completed_record_ids"]


def test_progress_completed_record_count_partial() -> None:
    response = {"evidence_results": [_record("pass")]}
    reviewed = {"EV-TEST-001": {"usage_value": {"status": "Accepted"}}}
    progress = get_extraction_review_progress(response, reviewed)
    assert progress["completed_record_count"] == 0


# --- record labels ------------------------------------------------------------


def test_record_display_name_prefers_asset_display_name() -> None:
    record = {"evidence_id": "EV-X", "document_type": "Utility Bill"}
    assert record_display_name(record, {"display_name": "Natural Gas Bill"}) == "Natural Gas Bill"
    assert record_display_name(record, {}) == "Utility Bill"


def test_record_period_label_from_period_bounds() -> None:
    record = {"period_start": "2023-10-01", "period_end": "2023-10-31"}
    assert "2023-10-01" in record_period_label(record)
    assert "2023-10-31" in record_period_label(record)


# --- source reference sanitization --------------------------------------------


def test_resolve_field_source_reference_sanitizes_snippet() -> None:
    record = {
        "evidence_id": "EV-AGG-2023-001",
        "source_references": [
            {
                "page_number": 12,
                "source_snippet": "EV-AGG-2023-001 groups BLR-001, BLR-002, GEN-001 for 2023 annual roll-up.",
            }
        ],
    }
    ref = resolve_field_source_reference(record, {}, "aggregated_total")
    assert not ref["source_snippet"].startswith("EV-AGG")
    assert "and GEN-001" in ref["source_snippet"]
    assert ref["section_identifier"] == "EV-AGG-2023-001"


# --- DOCX section preview extraction ------------------------------------------


def test_docx_section_extraction_returns_blocks() -> None:
    from src.ui.document_preview import _DOCX_AVAILABLE, _extract_docx_section

    if not _DOCX_AVAILABLE or not DOCX_PATH.exists():
        return  # environment without python-docx or sample doc; preview falls back gracefully
    blocks = _extract_docx_section(DOCX_PATH, "EV-NG-2023-010")
    assert blocks, "October natural gas section should resolve to document blocks"
    kinds = {kind for kind, _ in blocks}
    assert "para" in kinds


def test_docx_section_extraction_missing_returns_none() -> None:
    from src.ui.document_preview import _DOCX_AVAILABLE, _extract_docx_section

    if not _DOCX_AVAILABLE or not DOCX_PATH.exists():
        return
    assert _extract_docx_section(DOCX_PATH, "EV-DOES-NOT-EXIST-999") is None


# --- manifest -----------------------------------------------------------------


def test_manifest_section_identifiers_match_evidence_ids() -> None:
    payload = _read_json(MANIFEST_PATH)
    for asset in payload["assets"]:
        assert asset["section_identifier"] == asset["evidence_id"]


def test_manifest_snippets_have_no_leading_evidence_token() -> None:
    payload = _read_json(MANIFEST_PATH)
    for asset in payload["assets"]:
        snippet = asset.get("source_snippet") or ""
        assert not snippet.strip().upper().startswith("EV-"), asset["evidence_id"]


def test_gap_path_agg_snippet_is_sanitized() -> None:
    raw = GAP_PATH.read_text(encoding="utf-8-sig")
    assert "EV-AGG-2023-001 groups" not in raw
    assert "This worksheet groups BLR-001, BLR-002, and GEN-001 for the 2023 annual roll-up." in raw


# --- Page 3 static contract ---------------------------------------------------


def _page_source() -> str:
    return PAGE_3.read_text(encoding="utf-8-sig")


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


def _top_level_st_calls() -> list[ast.Call]:
    tree = ast.parse(_page_source())
    calls: list[ast.Call] = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        func = call.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "st":
            calls.append(call)
    return calls


def _main_pane_columns_call() -> ast.Call | None:
    tree = ast.parse(_page_source())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        func = call.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "st"
            and func.attr == "columns"
        ):
            continue

        if not node.targets:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Tuple):
            continue
        names = [elt.id for elt in target.elts if isinstance(elt, ast.Name)]
        if names == ["left_col", "source_col", "fields_col"]:
            return call
    return None


def _num(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise AssertionError("Expected numeric literal")


def test_page_compiles() -> None:
    py_compile.compile(str(PAGE_3), doraise=True)


def test_page_has_no_rerun_or_wrap_style() -> None:
    identifiers = _page_identifiers()
    assert "rerun" not in identifiers, "Page 3 must not call st.rerun()"
    assert "_inject_button_style" not in identifiers
    assert "white-space: nowrap" not in _page_source()


def test_page_uses_three_pane_layout_and_no_five_column_action_row() -> None:
    source = _page_source()
    call = _main_pane_columns_call()
    assert call is not None, "Expected the main three-pane st.columns assignment"

    assert call.args and isinstance(call.args[0], ast.List)
    weights = [_num(elt) for elt in call.args[0].elts]
    assert len(weights) == 3

    total = sum(weights)
    left_share = weights[0] / total
    source_share = weights[1] / total
    fields_share = weights[2] / total

    assert 0.18 <= left_share <= 0.21
    assert 0.39 <= source_share <= 0.41
    assert 0.39 <= fields_share <= 0.41
    assert abs(source_share - fields_share) < 0.01

    gap_kw = next((kw for kw in call.keywords if kw.arg == "gap"), None)
    assert gap_kw is not None
    assert isinstance(gap_kw.value, ast.Constant)
    assert gap_kw.value.value == "small"

    assert "st.columns(5)" not in source


def test_page_has_scoped_width_treatment() -> None:
    source = _page_source()
    assert 'data-testid="stMainBlockContainer"' in source
    assert "section.main .block-container" in source
    assert "max-width: none" in source
    assert "max-width: 1800" not in source
    assert "MAX_WORKSPACE_WIDTH_PX" not in source
    assert "_inject_page3_layout_style" in source


def test_page_has_set_page_config_wide_as_first_top_level_streamlit_call() -> None:
    calls = _top_level_st_calls()
    assert calls, "Expected top-level streamlit calls"

    first = calls[0]
    assert isinstance(first.func, ast.Attribute)
    assert first.func.attr == "set_page_config"

    kwargs = {kw.arg: kw.value for kw in first.keywords if kw.arg}
    assert "layout" in kwargs
    assert isinstance(kwargs["layout"], ast.Constant)
    assert kwargs["layout"].value == "wide"


def test_page_uses_callbacks_for_field_actions() -> None:
    source = _page_source()
    assert "on_click=_cb_set_status" in source
    assert "on_click=_cb_select_record" in source
    assert "on_click=_cb_bulk_accept" in source
    assert "st.popover" in source or "popover(" in source


def test_page_has_toolbar_bulk_actions_and_risky_acks() -> None:
    source = _page_source()
    assert "Category bulk actions" in source
    assert "Confirm all Pass fields" in source
    assert "Accept all Needs-review fields" in source
    assert "Accept all Fail fields" in source
    assert "toolbar_ack_needs" in source
    assert "toolbar_ack_fail" in source
    assert "toolbar_ack_pass" not in source


def test_page_keeps_hard_gate_navigation_behavior() -> None:
    source = _page_source()
    assert "Proceed to Calculation & Reconciliation" in source
    assert "pages/5_Calculation_and_Reconciliation.py" in source


def test_left_rail_is_selector_only_no_bulk_copy() -> None:
    source = _page_source()
    assert "_render_left_group" in source
    assert "I have reviewed these {label.lower()} fields" not in source


def test_page_has_uploaded_evidence_overview_and_no_raw_id_caption_metadata() -> None:
    source = _page_source()
    assert "def _page_count" in source
    assert "def _humanize_id" in source
    assert "def _build_evidence_overview_rows" in source
    assert 'with st.expander("Uploaded evidence"' in source
    assert "st.dataframe(overview_rows" in source
    assert "meta_bits = [evidence_id]" not in source


def _run_page3_apptest() -> AppTest:
    response = _read_json(GAP_PATH)
    at = AppTest.from_file(str(PAGE_3), default_timeout=30)
    at.session_state["analysis_response"] = response
    at.run()
    return at


def test_page3_apptest_initial_render_no_exception() -> None:
    at = _run_page3_apptest()
    assert len(at.exception) == 0
    assert len(at.metric) >= 4
    labels = {metric.label for metric in at.metric}
    assert {"Fields", "Decided", "Remaining", "Evidence items"}.issubset(labels)


def test_page3_apptest_individual_accept_callback() -> None:
    at = _run_page3_apptest()
    accept_buttons = [button for button in at.button if button.label == "Accept"]
    assert accept_buttons, "Expected at least one field-level Accept button"
    accept_buttons[0].click().run()
    assert len(at.exception) == 0
    reviewed = at.session_state["reviewed_extraction_fields"] if "reviewed_extraction_fields" in at.session_state else None
    assert isinstance(reviewed, dict) and reviewed


def test_page3_apptest_bulk_and_record_selection_callbacks() -> None:
    at = _run_page3_apptest()

    pass_bulk = next((button for button in at.button if button.key == "toolbar_bulk_pass"), None)
    assert pass_bulk is not None
    if not pass_bulk.disabled:
        pass_bulk.click().run()
        assert len(at.exception) == 0

    selected_before = at.session_state["selected_evidence_id"] if "selected_evidence_id" in at.session_state else None
    selectable = [button for button in at.button if str(button.key).startswith("select_") and not button.disabled]
    assert selectable, "Expected selectable evidence rows"
    target = next((button for button in selectable if button.key and selected_before not in str(button.key)), selectable[0])
    target.click().run()
    assert len(at.exception) == 0
    selected_after = at.session_state["selected_evidence_id"] if "selected_evidence_id" in at.session_state else None
    assert selected_after != selected_before or len(selectable) == 1


def test_page_does_not_mutate_analysis_response() -> None:
    identifiers = _page_identifiers()
    for token in ("set_analysis_response", "MockApiClient", "adapt_analysis_response"):
        assert token not in identifiers
    assert "review_complete" not in identifiers
