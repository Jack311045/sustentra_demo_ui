from __future__ import annotations

from pathlib import Path

import streamlit as st


def _show_unavailable(asset: dict, evidence_record: dict | None) -> None:
    display_name = asset.get("display_name") or (evidence_record or {}).get("file_name") or "Unknown document"
    evidence_id = asset.get("evidence_id") or (evidence_record or {}).get("evidence_id") or "Unknown"
    page_number = asset.get("page_number")
    section_identifier = asset.get("section_identifier")
    source_snippet = asset.get("source_snippet")

    st.write(f"**Document name:** {display_name}")
    st.write(f"**Evidence ID:** {evidence_id}")
    if page_number is not None:
        st.caption(f"Page: {page_number}")
    if section_identifier:
        st.caption(f"Section: {section_identifier}")
    if source_snippet:
        st.write(source_snippet)
    st.caption("Original preview unavailable in current demo")


def render_document_preview(asset: dict | None, evidence_record: dict | None = None) -> None:
    asset = asset if isinstance(asset, dict) else {}
    preview_type = str(asset.get("preview_type") or "source_snippet")
    source_document_path = asset.get("source_document_path")

    source_path = Path(source_document_path) if isinstance(source_document_path, str) and source_document_path else None
    source_exists = bool(source_path and source_path.exists() and source_path.is_file())

    if preview_type == "image" and source_exists:
        st.image(str(source_path), caption=asset.get("display_name") or source_path.name, use_container_width=True)
        return

    if preview_type == "xlsx_range":
        preview_rows = asset.get("range_preview_rows")
        if isinstance(preview_rows, list) and preview_rows:
            st.dataframe(preview_rows, use_container_width=True)
            return
        _show_unavailable(asset, evidence_record)
        return

    if preview_type == "docx_section":
        if asset.get("source_snippet"):
            st.write(asset.get("source_snippet"))
            if source_exists:
                st.caption(f"Source file: {source_path.name}")
            return
        _show_unavailable(asset, evidence_record)
        return

    if preview_type == "pdf" and source_exists:
        st.caption(f"Source file: {source_path.name}")
        _show_unavailable(asset, evidence_record)
        return

    _show_unavailable(asset, evidence_record)
