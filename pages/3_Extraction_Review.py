from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.ui.document_preview import render_document_preview
from src.ui.formatting import is_internal_routing_evidence, safe_text
from src.ui.state import (
    get_analysis_response,
    get_reviewed_extraction_fields,
    get_selected_evidence_id,
    init_session_state,
    set_reviewed_extraction_field,
    set_selected_evidence_id,
)
from src.ui.workflow import render_prepared_demo_disclosure


ASSET_MANIFEST_PATH = Path("data/demo/mock_outputs/evidence_assets_manifest.json")


def _status_bucket(record: dict) -> str:
    status = safe_text(record.get("ui_status") or record.get("status")).strip().lower()
    if status in {"need_review", "needs_review"}:
        return "Needs review"
    if status in {"flagged", "flagged_for_auditor_review"}:
        return "Flagged"
    if status in {"pass", "accepted_for_extraction", "accepted_supporting_evidence_only"}:
        return "Accepted"
    return "Needs review"


def _load_asset_manifest() -> dict[str, dict]:
    if not ASSET_MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    records = payload.get("assets") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return {}

    output: dict[str, dict] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        evidence_id = safe_text(item.get("evidence_id"))
        if evidence_id:
            output[evidence_id] = item
    return output


def _friendly_field_label(field_key: str) -> str:
    return field_key.replace("_", " ").strip().title()


init_session_state()
st.title("Extraction Review")
st.caption("Compare source evidence with prepared extracted fields and apply reviewer decisions.")
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

evidence_results = [
    item for item in (analysis_response.get("evidence_results") or []) if isinstance(item, dict)
]
if not evidence_results:
    st.info("No evidence records are available in the prepared dataset.")
    st.stop()

filter_option = st.selectbox(
    "Evidence filter",
    options=["All", "Needs review", "Flagged", "Accepted", "Internal routing documents"],
    index=0,
)

filtered_records = []
for record in evidence_results:
    evidence_id = safe_text(record.get("evidence_id"))
    is_internal = is_internal_routing_evidence(evidence_id)

    if filter_option == "Internal routing documents":
        if is_internal:
            filtered_records.append(record)
        continue

    if is_internal:
        continue

    status_bucket = _status_bucket(record)
    if filter_option == "All" or status_bucket == filter_option:
        filtered_records.append(record)

if not filtered_records:
    st.info("No evidence records match this filter.")
    st.stop()

record_ids = [safe_text(item.get("evidence_id")) for item in filtered_records]
selected_id = get_selected_evidence_id()
if selected_id not in record_ids:
    selected_id = record_ids[0]

selected_id = st.selectbox(
    "Select evidence",
    options=record_ids,
    index=record_ids.index(selected_id),
)
set_selected_evidence_id(selected_id)

selected_record = next(
    (record for record in filtered_records if safe_text(record.get("evidence_id")) == selected_id),
    None,
)
if not selected_record:
    st.info("Selected evidence could not be found.")
    st.stop()

is_internal_selected = is_internal_routing_evidence(selected_id)
if is_internal_selected:
    st.warning("Internal routing document")

asset_manifest = _load_asset_manifest()
selected_asset = asset_manifest.get(selected_id, {})

left_col, right_col = st.columns([11, 9])
with left_col:
    st.subheader("Original/source document")
    render_document_preview(selected_asset, selected_record)

with right_col:
    st.subheader("Extracted fields")
    extracted_fields = selected_record.get("extracted_fields")
    if not isinstance(extracted_fields, dict) or not extracted_fields:
        st.info("No extracted fields are available for this evidence item.")
    else:
        source_refs = selected_record.get("source_references") if isinstance(selected_record.get("source_references"), list) else []
        first_ref = source_refs[0] if source_refs and isinstance(source_refs[0], dict) else {}
        page_label = first_ref.get("page_number")
        snippet_label = first_ref.get("source_snippet")
        reviewed_map = get_reviewed_extraction_fields(selected_id)

        for field_key, raw_value in extracted_fields.items():
            review_state = reviewed_map.get(field_key) if isinstance(reviewed_map.get(field_key), dict) else {}
            current_status = review_state.get("status") or "Needs confirmation"

            with st.container(border=True):
                st.markdown(f"**{_friendly_field_label(field_key)}**")
                st.write(f"Value: {raw_value}")
                st.caption(f"Source: page {page_label if page_label is not None else 'N/A'}")
                if snippet_label:
                    st.caption(f"Snippet: {snippet_label}")
                st.caption(f"Review status: {current_status}")

                edit_value = st.text_input(
                    "Edit value",
                    value=str(review_state.get("edited_value") if review_state.get("edited_value") is not None else raw_value),
                    key=f"edit_{selected_id}_{field_key}",
                    label_visibility="collapsed",
                )

                action_cols = st.columns(5)
                if action_cols[0].button("Accept", key=f"accept_{selected_id}_{field_key}"):
                    set_reviewed_extraction_field(
                        selected_id,
                        field_key,
                        {"status": "Accepted", "edited_value": edit_value},
                    )
                    st.rerun()
                if action_cols[1].button("Edit", key=f"edit_save_{selected_id}_{field_key}"):
                    set_reviewed_extraction_field(
                        selected_id,
                        field_key,
                        {"status": "Edited", "edited_value": edit_value},
                    )
                    st.rerun()
                if action_cols[2].button("Reject", key=f"reject_{selected_id}_{field_key}"):
                    set_reviewed_extraction_field(
                        selected_id,
                        field_key,
                        {"status": "Rejected", "edited_value": edit_value},
                    )
                    st.rerun()
                if action_cols[3].button("Mark unclear", key=f"unclear_{selected_id}_{field_key}"):
                    set_reviewed_extraction_field(
                        selected_id,
                        field_key,
                        {"status": "Needs clarification", "edited_value": edit_value},
                    )
                    st.rerun()
                if action_cols[4].button("View source", key=f"source_{selected_id}_{field_key}"):
                    st.info(snippet_label or "Source snippet is unavailable for this field.")

    with st.expander("Advanced extraction JSON", expanded=False):
        st.json(selected_record.get("extracted_fields") or {})
