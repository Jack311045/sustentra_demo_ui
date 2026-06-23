"""Extraction Review (Page 3).

Extraction-review half of Act 1 plus the hard human-review gate. This page is
strictly read-only with respect to ``analysis_response`` -- it never calls
``set_analysis_response``/``MockApiClient``/``adapt_analysis_response`` and never
mutates the prepared extraction. All reviewer decisions live in the
``reviewed_extraction_fields`` overlay, and review progress / the proceed gate
are derived on every rerun (there is no persisted ``review_complete``).
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
    field_confidence_bucket,
    get_extraction_review_progress,
    get_field_review_status,
    get_internal_routing_records,
    get_reviewable_evidence_records,
    passing_field_keys,
    record_confidence_bucket,
    resolve_field_source_reference,
)
from src.ui.formatting import safe_text
from src.ui.state import (
    add_auditor_extraction_field,
    get_analysis_response,
    get_extraction_review_bulk_acknowledged,
    get_focused_source_field,
    get_reviewed_extraction_fields,
    get_selected_evidence_id,
    init_session_state,
    open_workbook_location,
    set_extraction_review_bulk_acknowledged,
    set_focused_source_field,
    set_reviewed_extraction_field,
    set_selected_evidence_id,
)
from src.ui.workflow import render_prepared_demo_disclosure


ASSET_MANIFEST_PATH = Path("data/demo/mock_outputs/evidence_assets_manifest.json")

_BUCKET_COLOR = {BUCKET_PASS: "green", BUCKET_NEEDS_REVIEW: "orange", BUCKET_FAIL: "red"}


def _inject_button_style() -> None:
    # Prevent mid-word wrapping inside action buttons.
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button p { white-space: nowrap; }
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


def _confidence_badge(bucket: str) -> str:
    color = _BUCKET_COLOR.get(bucket, "gray")
    return f":{color}[{BUCKET_LABELS.get(bucket, 'Needs review')}]"


def _find_linked_calculation(analysis_response: dict, evidence_id: str) -> dict | None:
    for calc in analysis_response.get("calculation_results") or []:
        if not isinstance(calc, dict):
            continue
        linked = calc.get("linked_evidence_ids") or []
        if isinstance(linked, list) and evidence_id in linked:
            return calc
    return None


init_session_state()
_inject_button_style()
st.title("Extraction Review")
st.caption("Confirm prepared extracted fields against the source evidence before any calculation runs.")
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

reviewable_records = get_reviewable_evidence_records(analysis_response)
if not reviewable_records:
    st.info("No reviewable evidence records are available in the prepared dataset.")
    st.stop()

reviewed_all = get_reviewed_extraction_fields()
progress = get_extraction_review_progress(analysis_response, reviewed_all)
group_counts = progress["group_counts"]

# --- Review progress + confidence groups --------------------------------------
st.subheader("Review progress")
prog_cols = st.columns(3)
prog_cols[0].metric("Fields to review", progress["total_fields"])
prog_cols[1].metric("Confirmed", progress["confirmed_fields"])
prog_cols[2].metric("Remaining", progress["unconfirmed_fields"])
if progress["total_fields"]:
    st.progress(progress["confirmed_fields"] / progress["total_fields"])

group_cols = st.columns(3)
group_cols[0].metric("Pass", group_counts.get(BUCKET_PASS, 0))
group_cols[1].metric("Needs review", group_counts.get(BUCKET_NEEDS_REVIEW, 0))
group_cols[2].metric("Fail", group_counts.get(BUCKET_FAIL, 0))

# Group reviewable records by worst-condition bucket.
grouped: dict[str, list[dict]] = {BUCKET_PASS: [], BUCKET_NEEDS_REVIEW: [], BUCKET_FAIL: []}
for record in reviewable_records:
    grouped[record_confidence_bucket(record)].append(record)

record_ids = [safe_text(item.get("evidence_id")) for item in reviewable_records]
selected_id = get_selected_evidence_id()
if selected_id not in record_ids:
    selected_id = record_ids[0]
    set_selected_evidence_id(selected_id)

st.subheader("Evidence by extraction confidence")
for bucket in (BUCKET_FAIL, BUCKET_NEEDS_REVIEW, BUCKET_PASS):
    records = grouped[bucket]
    label = BUCKET_LABELS[bucket]
    with st.expander(f"{label} ({len(records)})", expanded=bucket != BUCKET_PASS):
        if not records:
            st.caption("No evidence in this group.")
            continue
        for record in records:
            evidence_id = safe_text(record.get("evidence_id"))
            doc_type = safe_text(record.get("document_type")) or evidence_id
            is_selected = evidence_id == selected_id
            button_label = f"{'● ' if is_selected else ''}{evidence_id} — {doc_type}"
            if st.button(button_label, key=f"select_{bucket}_{evidence_id}", use_container_width=True):
                set_selected_evidence_id(evidence_id)
                set_focused_source_field(None, None)
                st.rerun()

internal_records = get_internal_routing_records(analysis_response)
if internal_records:
    with st.expander(f"Internal routing documents ({len(internal_records)})", expanded=False):
        st.caption("Routing/index documents are excluded from review counts and the proceed gate.")
        for record in internal_records:
            st.write(f"- {safe_text(record.get('evidence_id'))}: {safe_text(record.get('document_type'))}")

# --- Selected record detail ---------------------------------------------------
selected_record = next(
    (r for r in reviewable_records if safe_text(r.get("evidence_id")) == selected_id),
    None,
)
if not selected_record:
    st.info("Select an evidence record above to begin review.")
    st.stop()

asset_manifest = _load_asset_manifest()
selected_asset = asset_manifest.get(selected_id, {})
reviewed_map = get_reviewed_extraction_fields(selected_id)
focused = get_focused_source_field()
focused_field = focused.get("field_key") if focused.get("evidence_id") == selected_id else None

st.divider()
st.subheader(f"{selected_id} — {safe_text(selected_record.get('document_type'))}")

left_col, right_col = st.columns([11, 9])
with left_col:
    st.markdown("**Original / source document**")
    if focused_field:
        ref = resolve_field_source_reference(selected_record, selected_asset, focused_field)
        page = ref.get("page_number")
        with st.container(border=True):
            st.markdown(f"Highlighting **{_friendly_field_label(focused_field)}**")
            if page is not None:
                st.caption(f"Source page {page}")
            if ref.get("source_snippet"):
                st.info(ref["source_snippet"])
    render_document_preview(selected_asset, selected_record)

with right_col:
    st.markdown("**Extracted fields**")
    extracted_fields = selected_record.get("extracted_fields")
    if not isinstance(extracted_fields, dict) or not extracted_fields:
        st.info("No extracted fields are available for this evidence item.")
    else:
        for field_key, raw_value in extracted_fields.items():
            bucket = field_confidence_bucket(selected_record, field_key)
            status = get_field_review_status(reviewed_map, field_key)
            entry = reviewed_map.get(field_key) if isinstance(reviewed_map.get(field_key), dict) else {}
            current_value = entry.get("edited_value") if entry.get("edited_value") is not None else raw_value

            with st.container(border=True):
                header_cols = st.columns([3, 2])
                header_cols[0].markdown(f"**{_friendly_field_label(field_key)}**")
                header_cols[1].markdown(_confidence_badge(bucket))
                st.write(f"Value: {current_value}")
                if status == UNCONFIRMED_STATUS:
                    st.caption("Review status: Unconfirmed")
                else:
                    st.caption(f"Review status: {status}")

                edit_value = st.text_input(
                    "Edit value",
                    value=safe_text(current_value),
                    key=f"edit_{selected_id}_{field_key}",
                    label_visibility="collapsed",
                )

                action_cols = st.columns(5)
                if action_cols[0].button("Accept", key=f"accept_{selected_id}_{field_key}", use_container_width=True):
                    set_reviewed_extraction_field(selected_id, field_key, {"status": "Accepted"})
                    st.rerun()
                if action_cols[1].button("Edit", key=f"editsave_{selected_id}_{field_key}", use_container_width=True):
                    set_reviewed_extraction_field(
                        selected_id, field_key, {"status": "Edited", "edited_value": edit_value}
                    )
                    st.rerun()
                if action_cols[2].button("Reject", key=f"reject_{selected_id}_{field_key}", use_container_width=True):
                    set_reviewed_extraction_field(selected_id, field_key, {"status": "Rejected"})
                    st.rerun()
                if action_cols[3].button("Mark unclear", key=f"unclear_{selected_id}_{field_key}", use_container_width=True):
                    set_reviewed_extraction_field(selected_id, field_key, {"status": "Needs clarification"})
                    st.rerun()
                if action_cols[4].button("View source", key=f"source_{selected_id}_{field_key}", use_container_width=True):
                    set_focused_source_field(selected_id, field_key)
                    st.rerun()

    # Bulk confirmation of passing fields.
    passing_keys = passing_field_keys(selected_record)
    if passing_keys:
        st.markdown("**Bulk confirmation**")
        ack = st.checkbox(
            f"I have reviewed the {len(passing_keys)} passing field(s) and confirm them.",
            value=get_extraction_review_bulk_acknowledged(),
            key=f"bulk_ack_{selected_id}",
        )
        set_extraction_review_bulk_acknowledged(ack)
        if st.button("Confirm all passing fields", disabled=not ack, key=f"bulk_confirm_{selected_id}"):
            for field_key in passing_keys:
                set_reviewed_extraction_field(selected_id, field_key, {"status": "Accepted"})
            set_extraction_review_bulk_acknowledged(False)
            st.rerun()

    # Auditor-added field (overlay only).
    with st.expander("+ Add field", expanded=False):
        new_key = st.text_input("Field name", key=f"addkey_{selected_id}")
        new_value = st.text_input("Field value", key=f"addval_{selected_id}")
        if st.button("Add field", key=f"addbtn_{selected_id}"):
            clean_key = safe_text(new_key).strip().lower().replace(" ", "_")
            if clean_key:
                add_auditor_extraction_field(selected_id, clean_key, new_value)
                st.rerun()
            else:
                st.warning("Enter a field name to add an auditor field.")

# Neutral workbook link (no mismatch framing, no gap trigger here).
linked_calc = _find_linked_calculation(analysis_response, selected_id)
if linked_calc:
    location = linked_calc.get("workbook_location") if isinstance(linked_calc.get("workbook_location"), dict) else {}
    sheet = safe_text(location.get("sheet_name"))
    cell = safe_text(location.get("cell_or_range"))
    if sheet and cell:
        st.caption(
            f"Linked calculation {safe_text(linked_calc.get('calculation_id'))} → workbook {sheet}!{cell}"
        )
        if st.button("View linked workbook cell", key=f"wb_{selected_id}"):
            open_workbook_location({"sheet_name": sheet, "cell_or_range": cell})

with st.expander("Advanced extraction JSON", expanded=False):
    st.json(selected_record.get("extracted_fields") or {})

# --- Hard human-review gate (derived) -----------------------------------------
st.divider()
progress = get_extraction_review_progress(analysis_response, get_reviewed_extraction_fields())
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
):
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page("pages/5_Calculation_and_Reconciliation.py")
    else:
        st.info("Open Calculation & Reconciliation from the sidebar to continue.")
