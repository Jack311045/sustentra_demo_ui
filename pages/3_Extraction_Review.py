"""Extraction Review (Page 3).

Compact, auditor-friendly three-pane review workspace plus the hard
human-review gate. This page is strictly read-only with respect to
``analysis_response`` -- it never calls
``set_analysis_response``/``MockApiClient``/``adapt_analysis_response`` and never
mutates the prepared extraction. All reviewer decisions live in the
``reviewed_extraction_fields`` overlay, and review progress / the proceed gate
are derived on every rerun (there is no persisted ``review_complete``).

Interaction is fragment-scoped and driven entirely by ``on_click`` callbacks, so
no ``st.rerun()`` is used anywhere on this page.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.ui.document_preview import render_document_preview
from src.ui.extraction_review import (
    BUCKET_FAIL,
    BUCKET_LABELS,
    BUCKET_NEEDS_REVIEW,
    BUCKET_PASS,
    UNCONFIRMED_STATUS,
    build_bulk_accept_update,
    get_extraction_review_progress,
    get_field_review_status,
    get_internal_routing_records,
    get_reviewable_evidence_records,
    record_confidence_bucket,
    record_display_name,
    record_period_label,
    resolve_field_source_reference,
)
from src.ui.formatting import format_display_value, safe_text
from src.ui.state import (
    add_auditor_extraction_field,
    get_analysis_response,
    get_focused_source_field,
    get_reviewed_extraction_fields,
    get_selected_evidence_id,
    init_session_state,
    open_workbook_location,
    set_focused_source_field,
    set_reviewed_extraction_field,
    set_reviewed_extraction_fields,
    set_selected_evidence_id,
)
from src.ui.workflow import render_prepared_demo_disclosure


ASSET_MANIFEST_PATH = Path("data/demo/mock_outputs/evidence_assets_manifest.json")
PANE_HEIGHT = 620
MAX_WORKSPACE_WIDTH_PX = 1800

_BUCKET_EMOJI = {BUCKET_PASS: "\U0001f7e2", BUCKET_NEEDS_REVIEW: "\U0001f7e0", BUCKET_FAIL: "\U0001f534"}
_STATUS_COLOR = {
    "Accepted": "green",
    "Edited": "green",
    "Rejected": "red",
    "Needs clarification": "orange",
    UNCONFIRMED_STATUS: "gray",
}


def _inject_page3_layout_style() -> None:
    """Scope layout tweaks to Page 3 to maximize desktop usability."""
    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] .main .block-container {{
            max-width: {MAX_WORKSPACE_WIDTH_PX}px;
            padding-left: 1.1rem;
            padding-right: 1.1rem;
            padding-top: 1rem;
        }}

        [data-testid="stAppViewContainer"] div[data-testid="stButton"] > button,
        [data-testid="stAppViewContainer"] div[data-testid="stButton"] > button p {{
            white-space: normal;
            word-break: normal;
            overflow-wrap: normal;
            line-height: 1.25;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load_asset_manifest() -> dict[str, dict]:
    if not ASSET_MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = payload.get("assets") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return {}
    output: dict[str, dict] = {}
    for item in records:
        if isinstance(item, dict) and safe_text(item.get("evidence_id")):
            output[safe_text(item["evidence_id"])] = item
    return output


def _friendly_field_label(field_key: str) -> str:
    return safe_text(field_key).replace("_", " ").strip().title() or "Field"


def _status_chip(status: str) -> str:
    color = _STATUS_COLOR.get(status, "gray")
    return f":{color}[{status}]"


def _confidence_badge(bucket: str) -> str:
    emoji = _BUCKET_EMOJI.get(bucket, _BUCKET_EMOJI[BUCKET_NEEDS_REVIEW])
    return f"{emoji} {BUCKET_LABELS.get(bucket, BUCKET_LABELS[BUCKET_NEEDS_REVIEW])}"


def _find_linked_calculation(analysis_response: dict, evidence_id: str) -> dict | None:
    for calc in analysis_response.get("calculation_results") or []:
        if not isinstance(calc, dict):
            continue
        linked = calc.get("linked_evidence_ids") or []
        if isinstance(linked, list) and evidence_id in linked:
            return calc
    return None


def _unconfirmed_field_count(records: list[dict], reviewed_all: dict) -> int:
    total = 0
    for record in records:
        evidence_id = safe_text(record.get("evidence_id"))
        reviewed_map = reviewed_all.get(evidence_id) if isinstance(reviewed_all.get(evidence_id), dict) else {}
        for field_key in record.get("extracted_fields") or {}:
            if get_field_review_status(reviewed_map, field_key) == UNCONFIRMED_STATUS:
                total += 1
    return total


# --- Callbacks (mutate overlay only; fragment reruns automatically) -----------
def _cb_select_record(evidence_id: str) -> None:
    set_selected_evidence_id(evidence_id)
    set_focused_source_field(None, None)


def _cb_set_status(evidence_id: str, field_key: str, status: str) -> None:
    set_reviewed_extraction_field(evidence_id, field_key, {"status": status})


def _cb_focus_source(evidence_id: str, field_key: str) -> None:
    set_focused_source_field(evidence_id, field_key)


def _cb_start_edit(evidence_id: str, field_key: str) -> None:
    st.session_state[f"editing_{evidence_id}_{field_key}"] = True


def _cb_cancel_edit(evidence_id: str, field_key: str) -> None:
    st.session_state[f"editing_{evidence_id}_{field_key}"] = False


def _cb_save_edit(evidence_id: str, field_key: str, input_key: str) -> None:
    new_value = st.session_state.get(input_key, "")
    set_reviewed_extraction_field(
        evidence_id, field_key, {"status": "Edited", "edited_value": new_value}
    )
    st.session_state[f"editing_{evidence_id}_{field_key}"] = False


def _cb_bulk_accept(records: list[dict]) -> None:
    current = get_reviewed_extraction_fields()
    updated = build_bulk_accept_update(current, records, only_unconfirmed=True)
    set_reviewed_extraction_fields(updated)


def _cb_add_field(evidence_id: str, key_input: str, value_input: str) -> None:
    clean_key = safe_text(st.session_state.get(key_input, "")).strip().lower().replace(" ", "_")
    if not clean_key:
        st.session_state["_add_field_error"] = "Enter a field name to add an auditor field."
        return
    st.session_state.pop("_add_field_error", None)
    add_auditor_extraction_field(evidence_id, clean_key, st.session_state.get(value_input, ""))


# --- Field cards --------------------------------------------------------------
def _render_field_card(
    evidence_id: str,
    field_key: str,
    raw_value: object,
    reviewed_map: dict,
    *,
    auditor_added: bool = False,
) -> None:
    status = get_field_review_status(reviewed_map, field_key)
    entry = reviewed_map.get(field_key) if isinstance(reviewed_map.get(field_key), dict) else {}
    current_value = entry.get("edited_value") if entry.get("edited_value") is not None else raw_value
    editing = bool(st.session_state.get(f"editing_{evidence_id}_{field_key}", False))
    input_key = f"editinput_{evidence_id}_{field_key}"

    with st.container(border=True):
        header = st.columns([3, 2])
        suffix = " \u00b7 auditor added" if auditor_added else ""
        header[0].markdown(f"**{_friendly_field_label(field_key)}**{suffix}")
        header[1].markdown(_status_chip(status))

        if editing:
            st.text_input(
                "Edit value",
                value=safe_text(current_value),
                key=input_key,
                label_visibility="collapsed",
            )
            edit_cols = st.columns(2)
            edit_cols[0].button(
                "Save",
                key=f"save_{evidence_id}_{field_key}",
                type="primary",
                use_container_width=True,
                on_click=_cb_save_edit,
                args=(evidence_id, field_key, input_key),
            )
            edit_cols[1].button(
                "Cancel",
                key=f"canceledit_{evidence_id}_{field_key}",
                use_container_width=True,
                on_click=_cb_cancel_edit,
                args=(evidence_id, field_key),
            )
            return

        display_value = format_display_value(current_value)
        st.write(display_value if display_value else "\u2014")

        action_cols = st.columns(3)
        action_cols[0].button(
            "Accept",
            key=f"accept_{evidence_id}_{field_key}",
            type="primary",
            use_container_width=True,
            on_click=_cb_set_status,
            args=(evidence_id, field_key, "Accepted"),
        )
        action_cols[1].button(
            "Edit",
            key=f"edit_{evidence_id}_{field_key}",
            use_container_width=True,
            on_click=_cb_start_edit,
            args=(evidence_id, field_key),
        )
        action_cols[2].button(
            "Reject",
            key=f"reject_{evidence_id}_{field_key}",
            use_container_width=True,
            on_click=_cb_set_status,
            args=(evidence_id, field_key, "Rejected"),
        )

        popover = getattr(st, "popover", None)
        more_ctx = popover("More", use_container_width=True) if callable(popover) else st.expander("More")
        with more_ctx:
            st.button(
                "Mark unclear",
                key=f"unclear_{evidence_id}_{field_key}",
                use_container_width=True,
                on_click=_cb_set_status,
                args=(evidence_id, field_key, "Needs clarification"),
            )
            st.button(
                "View source",
                key=f"viewsrc_{evidence_id}_{field_key}",
                use_container_width=True,
                on_click=_cb_focus_source,
                args=(evidence_id, field_key),
            )


def _render_left_group(
    bucket: str,
    records: list[dict],
    selected_id: str,
    asset_manifest: dict,
) -> None:
    label = BUCKET_LABELS[bucket]
    emoji = _BUCKET_EMOJI[bucket]
    expanded = bucket != BUCKET_PASS
    with st.expander(f"{emoji} {label} ({len(records)})", expanded=expanded):
        if not records:
            st.caption("No evidence in this group.")
            return

        for record in records:
            evidence_id = safe_text(record.get("evidence_id"))
            period = record_period_label(record)
            name = record_display_name(record, asset_manifest.get(evidence_id, {}))
            row_label = name
            st.button(
                row_label,
                key=f"select_{bucket}_{evidence_id}",
                type="primary" if evidence_id == selected_id else "secondary",
                use_container_width=True,
                on_click=_cb_select_record,
                args=(evidence_id,),
            )
            meta_bits = [evidence_id]
            if period:
                meta_bits.append(period)
            st.caption(" | ".join(meta_bits))


def _render_bulk_toolbar(grouped: dict[str, list[dict]], reviewed_all: dict) -> None:
    st.markdown("**Category bulk actions**")
    pass_count = _unconfirmed_field_count(grouped.get(BUCKET_PASS, []), reviewed_all)
    needs_count = _unconfirmed_field_count(grouped.get(BUCKET_NEEDS_REVIEW, []), reviewed_all)
    fail_count = _unconfirmed_field_count(grouped.get(BUCKET_FAIL, []), reviewed_all)

    col_pass, col_needs, col_fail = st.columns(3, gap="small")

    col_pass.button(
        f"Confirm all Pass fields ({pass_count})",
        key="toolbar_bulk_pass",
        disabled=pass_count == 0,
        use_container_width=True,
        on_click=_cb_bulk_accept,
        args=(grouped.get(BUCKET_PASS, []),),
    )

    popover = getattr(st, "popover", None)
    with col_needs:
        if callable(popover):
            with st.popover(f"Accept all Needs-review fields ({needs_count})", use_container_width=True):
                st.caption("Requires explicit reviewer acknowledgement.")
                needs_ack = st.checkbox("I have reviewed these needs-review fields.", key="toolbar_ack_needs")
                st.button(
                    "Apply to Needs-review",
                    key="toolbar_apply_needs",
                    disabled=needs_count == 0 or not needs_ack,
                    use_container_width=True,
                    on_click=_cb_bulk_accept,
                    args=(grouped.get(BUCKET_NEEDS_REVIEW, []),),
                )
        else:
            with st.expander(f"Accept all Needs-review fields ({needs_count})", expanded=False):
                needs_ack = st.checkbox("I have reviewed these needs-review fields.", key="toolbar_ack_needs_fallback")
                st.button(
                    "Apply to Needs-review",
                    key="toolbar_apply_needs_fallback",
                    disabled=needs_count == 0 or not needs_ack,
                    use_container_width=True,
                    on_click=_cb_bulk_accept,
                    args=(grouped.get(BUCKET_NEEDS_REVIEW, []),),
                )

    with col_fail:
        if callable(popover):
            with st.popover(f"Accept all Fail fields ({fail_count})", use_container_width=True):
                st.caption("Requires explicit reviewer acknowledgement.")
                fail_ack = st.checkbox("I have reviewed these fail fields.", key="toolbar_ack_fail")
                st.button(
                    "Apply to Fail",
                    key="toolbar_apply_fail",
                    disabled=fail_count == 0 or not fail_ack,
                    use_container_width=True,
                    on_click=_cb_bulk_accept,
                    args=(grouped.get(BUCKET_FAIL, []),),
                )
        else:
            with st.expander(f"Accept all Fail fields ({fail_count})", expanded=False):
                fail_ack = st.checkbox("I have reviewed these fail fields.", key="toolbar_ack_fail_fallback")
                st.button(
                    "Apply to Fail",
                    key="toolbar_apply_fail_fallback",
                    disabled=fail_count == 0 or not fail_ack,
                    use_container_width=True,
                    on_click=_cb_bulk_accept,
                    args=(grouped.get(BUCKET_FAIL, []),),
                )


def _render_workspace() -> None:
    analysis_response = get_analysis_response()
    reviewable_records = get_reviewable_evidence_records(analysis_response)
    asset_manifest = _load_asset_manifest()
    reviewed_all = get_reviewed_extraction_fields()
    progress = get_extraction_review_progress(analysis_response, reviewed_all)

    record_ids = [safe_text(item.get("evidence_id")) for item in reviewable_records]
    selected_id = get_selected_evidence_id()
    if selected_id not in record_ids:
        selected_id = record_ids[0]
        set_selected_evidence_id(selected_id)

    selected_record = next(
        (r for r in reviewable_records if safe_text(r.get("evidence_id")) == selected_id),
        reviewable_records[0],
    )
    selected_asset = asset_manifest.get(selected_id, {})
    reviewed_map = get_reviewed_extraction_fields(selected_id)
    focused = get_focused_source_field()
    focused_field = focused.get("field_key") if focused.get("evidence_id") == selected_id else None

    # Compact progress strip.
    metric_cols = st.columns(4)
    metric_cols[0].metric("Fields", progress["total_fields"])
    metric_cols[1].metric("Decided", progress["confirmed_fields"])
    metric_cols[2].metric("Remaining", progress["unconfirmed_fields"])
    metric_cols[3].metric(
        "Evidence items",
        f"{progress['completed_record_count']}/{progress['reviewable_record_count']}",
    )
    if progress["total_fields"]:
        st.progress(progress["confirmed_fields"] / progress["total_fields"])

    # Record-level confidence badge (shown once).
    selected_bucket = record_confidence_bucket(selected_record)
    selected_period = record_period_label(selected_record)
    header_line = f"**{record_display_name(selected_record, selected_asset)}** \u2014 {_confidence_badge(selected_bucket)}"
    if selected_period:
        header_line += f" \u00b7 {selected_period}"
    st.markdown(header_line)

    grouped: dict[str, list[dict]] = {BUCKET_FAIL: [], BUCKET_NEEDS_REVIEW: [], BUCKET_PASS: []}
    for record in reviewable_records:
        grouped[record_confidence_bucket(record)].append(record)
    internal_records = get_internal_routing_records(analysis_response)

    _render_bulk_toolbar(grouped, reviewed_all)

    left_col, source_col, fields_col = st.columns([2.5, 5.5, 5.5], gap="medium")

    # --- Left rail: confidence groups -----------------------------------------
    with left_col:
        with st.container(height=PANE_HEIGHT, border=True):
            st.markdown("**Evidence by confidence**")
            for bucket in (BUCKET_FAIL, BUCKET_NEEDS_REVIEW, BUCKET_PASS):
                _render_left_group(bucket, grouped[bucket], selected_id, asset_manifest)
            if internal_records:
                with st.expander(f"Internal routing ({len(internal_records)})", expanded=False):
                    st.caption("Routing/index documents are read-only and excluded from the gate.")
                    for record in internal_records:
                        st.write(
                            f"- {safe_text(record.get('evidence_id'))}: "
                            f"{safe_text(record.get('document_type'))}"
                        )

    # --- Source pane ----------------------------------------------------------
    with source_col:
        with st.container(height=PANE_HEIGHT, border=True):
            st.markdown("**Source evidence**")
            if focused_field:
                ref = resolve_field_source_reference(selected_record, selected_asset, focused_field)
                with st.container(border=True):
                    st.caption("Focused source reference")
                    st.markdown(f"**{_friendly_field_label(focused_field)}**")
                    if ref.get("page_number") is not None:
                        st.caption(f"Page {ref['page_number']}")
                    if ref.get("source_snippet"):
                        st.write(ref["source_snippet"])
            render_document_preview(selected_asset, selected_record)

    # --- Fields pane ----------------------------------------------------------
    with fields_col:
        with st.container(height=PANE_HEIGHT, border=True):
            st.markdown("**Extracted fields**")
            extracted_fields = selected_record.get("extracted_fields")
            if not isinstance(extracted_fields, dict) or not extracted_fields:
                st.info("No extracted fields are available for this evidence item.")
            else:
                for field_key, raw_value in extracted_fields.items():
                    _render_field_card(selected_id, field_key, raw_value, reviewed_map)

            # Auditor-added overlay fields (not part of the prepared extraction).
            prepared_keys = set(extracted_fields) if isinstance(extracted_fields, dict) else set()
            auditor_keys = [
                key
                for key, entry in reviewed_map.items()
                if isinstance(entry, dict) and entry.get("auditor_added") and key not in prepared_keys
            ]
            if auditor_keys:
                st.caption("Auditor-added fields")
                for field_key in auditor_keys:
                    base_value = reviewed_map[field_key].get("edited_value")
                    _render_field_card(
                        selected_id, field_key, base_value, reviewed_map, auditor_added=True
                    )

            # Neutral workbook link (no mismatch/gap framing on this page).
            linked_calc = _find_linked_calculation(analysis_response, selected_id)
            if linked_calc:
                location = (
                    linked_calc.get("workbook_location")
                    if isinstance(linked_calc.get("workbook_location"), dict)
                    else {}
                )
                sheet = safe_text(location.get("sheet_name"))
                cell = safe_text(location.get("cell_or_range"))
                if sheet and cell:
                    st.caption(f"Linked to workbook: {sheet}!{cell}")
                    st.button(
                        "Open workbook location",
                        key=f"wb_{selected_id}",
                        on_click=open_workbook_location,
                        args=({"sheet_name": sheet, "cell_or_range": cell},),
                    )

            with st.expander("+ Add field", expanded=False):
                key_input = f"addkey_{selected_id}"
                val_input = f"addval_{selected_id}"
                st.text_input("Field name", key=key_input)
                st.text_input("Field value", key=val_input)
                st.button(
                    "Add field",
                    key=f"addbtn_{selected_id}",
                    on_click=_cb_add_field,
                    args=(selected_id, key_input, val_input),
                )
                if st.session_state.get("_add_field_error"):
                    st.warning(st.session_state["_add_field_error"])

    # --- Hard human-review gate (derived) -------------------------------------
    st.divider()
    if progress["is_complete"]:
        st.success("All reviewable fields have a decision. You can proceed to Calculation & Reconciliation.")
    else:
        st.warning(
            f"{progress['unconfirmed_fields']} field(s) still need a decision before you can proceed."
        )

    if st.button(
        "Proceed to Calculation & Reconciliation",
        type="primary",
        disabled=not progress["is_complete"],
        key="proceed_to_calculation",
    ):
        switch_page = getattr(st, "switch_page", None)
        if callable(switch_page):
            try:
                switch_page("pages/5_Calculation_and_Reconciliation.py")
            except Exception:
                st.info("Open Calculation & Reconciliation from the sidebar to continue.")
        else:
            st.info("Open Calculation & Reconciliation from the sidebar to continue.")


init_session_state()
_inject_page3_layout_style()
st.title("Extraction Review")
st.caption("Confirm prepared extracted fields against the source evidence before any calculation runs.")
render_prepared_demo_disclosure()

_analysis_response = get_analysis_response()
if not _analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

if not get_reviewable_evidence_records(_analysis_response):
    st.info("No reviewable evidence records are available in the prepared dataset.")
    st.stop()

_fragment = getattr(st, "fragment", None)
_workspace = _fragment(_render_workspace) if callable(_fragment) else _render_workspace
_workspace()
