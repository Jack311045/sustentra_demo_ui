from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from src.ui.formatting import safe_text, sanitize_source_snippet

try:  # python-docx is optional at import time; guarded so pages never crash.
    import docx  # type: ignore
    from docx.oxml.table import CT_Tbl  # type: ignore
    from docx.oxml.text.paragraph import CT_P  # type: ignore
    from docx.table import Table as _DocxTable  # type: ignore
    from docx.text.paragraph import Paragraph as _DocxParagraph  # type: ignore

    _DOCX_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when dependency missing
    docx = None  # type: ignore
    _DOCX_AVAILABLE = False


_CARD_STYLE = (
    "background:#ffffff;border:1px solid #d7dbe0;border-radius:8px;"
    "padding:18px 20px;color:#1f2328;font-size:0.92rem;line-height:1.55;"
    "max-height:430px;overflow:auto;box-shadow:0 1px 2px rgba(16,24,40,0.06);"
)
_TABLE_STYLE = (
    "border-collapse:collapse;min-width:760px;margin:8px 0;font-size:0.85rem;color:#1f2328;"
)
_TABLE_WRAP_STYLE = "overflow-x:auto;max-width:100%;margin:6px 0;"
_TD_STYLE = "border:1px solid #d7dbe0;padding:5px 8px;text-align:left;vertical-align:top;"
_META_STYLE = "color:#57606a;font-size:0.8rem;margin-bottom:10px;"


def _doc_meta(asset: dict, evidence_record: dict | None) -> dict:
    record = evidence_record or {}
    return {
        "display_name": safe_text(asset.get("display_name"))
        or safe_text(record.get("file_name"))
        or "Evidence document",
        "evidence_id": safe_text(asset.get("evidence_id"))
        or safe_text(record.get("evidence_id"))
        or "Unknown",
        "page_number": asset.get("page_number"),
        "section_identifier": safe_text(asset.get("section_identifier"))
        or safe_text(record.get("evidence_id")),
        "source_file": safe_text(asset.get("source_document_path")),
    }


def _meta_header_html(meta: dict) -> str:
    parts = [f"<strong>{html.escape(meta['display_name'])}</strong>"]
    tail = []
    if meta.get("source_file"):
        tail.append(html.escape(Path(meta["source_file"]).name))
    if meta.get("page_number") is not None:
        tail.append(f"Page {html.escape(str(meta['page_number']))}")
    if meta.get("section_identifier"):
        tail.append(f"Section {html.escape(str(meta['section_identifier']))}")
    if tail:
        parts.append(f"<div style='{_META_STYLE}'>{' &middot; '.join(tail)}</div>")
    return "".join(parts)


def _iter_block_items(document: Any):
    """Yield ``("para", Paragraph)`` / ``("table", Table)`` in document order."""
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield "para", _DocxParagraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield "table", _DocxTable(child, document)


def _table_rows(table: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([safe_text(cell.text).strip() for cell in row.cells])
    return rows


def _extract_docx_section(path: Path, section_identifier: str) -> list[tuple[str, Any]] | None:
    """Return in-order blocks for one ``Document ID: {id}`` section.

    Blocks are ``("para", text)`` or ``("table", rows)``. Returns ``None`` when
    the section cannot be located or python-docx is unavailable.
    """
    if not _DOCX_AVAILABLE or not section_identifier:
        return None
    try:
        document = docx.Document(str(path))  # type: ignore[union-attr]
    except Exception:
        return None

    marker = f"document id: {section_identifier.strip().lower()}"
    blocks: list[tuple[str, Any]] = []
    capturing = False
    for kind, item in _iter_block_items(document):
        if kind == "para":
            text = safe_text(item.text).strip()
            lowered = text.lower()
            if lowered.startswith("document id:"):
                if capturing:
                    break  # reached the next section
                if lowered.startswith(marker):
                    capturing = True
                continue
            if capturing and text:
                blocks.append(("para", text))
        elif kind == "table" and capturing:
            rows = _table_rows(item)
            if rows:
                blocks.append(("table", rows))

    return blocks or None


def _render_blocks_card(meta: dict, blocks: list[tuple[str, Any]]) -> None:
    body_parts: list[str] = [_meta_header_html(meta)]
    for kind, payload in blocks:
        if kind == "para":
            body_parts.append(f"<p style='margin:6px 0;'>{html.escape(str(payload))}</p>")
        elif kind == "table":
            rows = payload or []
            cells_html = []
            for r_idx, row in enumerate(rows):
                tag = "th" if r_idx == 0 else "td"
                style = _TD_STYLE + ("font-weight:600;background:#f6f8fa;" if r_idx == 0 else "")
                cols = "".join(
                    f"<{tag} style='{style}'>{html.escape(str(cell))}</{tag}>" for cell in row
                )
                cells_html.append(f"<tr>{cols}</tr>")
            table_html = f"<table style='{_TABLE_STYLE}'>{''.join(cells_html)}</table>"
            body_parts.append(f"<div style='{_TABLE_WRAP_STYLE}'>{table_html}</div>")
    st.markdown(f"<div style='{_CARD_STYLE}'>{''.join(body_parts)}</div>", unsafe_allow_html=True)


def _render_excerpt_card(meta: dict, asset: dict, note: str | None = None) -> None:
    excerpt = sanitize_source_snippet(asset.get("source_snippet"))
    body_parts = [_meta_header_html(meta)]
    if excerpt:
        body_parts.append(f"<p style='margin:6px 0;'>{html.escape(excerpt)}</p>")
    else:
        body_parts.append(
            "<p style='margin:6px 0;color:#57606a;'>No source excerpt was captured for this field.</p>"
        )
    if note:
        body_parts.append(f"<div style='{_META_STYLE}margin-top:10px;'>{html.escape(note)}</div>")
    st.markdown(f"<div style='{_CARD_STYLE}'>{''.join(body_parts)}</div>", unsafe_allow_html=True)


def render_document_preview(asset: dict | None, evidence_record: dict | None = None) -> None:
    asset = asset if isinstance(asset, dict) else {}
    meta = _doc_meta(asset, evidence_record)
    preview_type = str(asset.get("preview_type") or "source_snippet")
    source_document_path = asset.get("source_document_path")

    source_path = (
        Path(source_document_path)
        if isinstance(source_document_path, str) and source_document_path
        else None
    )
    source_exists = bool(source_path and source_path.exists() and source_path.is_file())

    # Real rendered image of the original page.
    if preview_type == "image" and source_exists:
        st.image(str(source_path), caption=meta["display_name"], use_container_width=True)
        return

    # Spreadsheet range preview as a table.
    if preview_type == "xlsx_range":
        preview_rows = asset.get("range_preview_rows")
        if isinstance(preview_rows, list) and preview_rows:
            st.caption(meta["display_name"])
            st.dataframe(preview_rows, use_container_width=True)
            return
        _render_excerpt_card(meta, asset, note="Spreadsheet range preview unavailable.")
        return

    # DOCX section: extract the matching section and render it as a document card.
    if preview_type == "docx_section":
        section_id = safe_text(asset.get("section_identifier")) or meta["evidence_id"]
        if source_exists:
            blocks = _extract_docx_section(source_path, section_id)
            if blocks:
                _render_blocks_card(meta, blocks)
                return
        note = None if _DOCX_AVAILABLE else "Rich document preview requires the python-docx package."
        _render_excerpt_card(meta, asset, note=note)
        return

    # PDF / anything else: never leave the pane empty.
    note = "Inline PDF rendering is not enabled in this demo." if preview_type == "pdf" else None
    _render_excerpt_card(meta, asset, note=note)
