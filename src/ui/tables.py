from __future__ import annotations

import pandas as pd
import streamlit as st


def render_table(records: list[dict], empty_message: str = "No records yet.") -> None:
    if not records:
        st.info(empty_message)
        return
    st.dataframe(pd.DataFrame(records), use_container_width=True)


def _as_csv(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _severity_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("auditor_assigned") or value.get("system_suggested") or "")
    if value is None:
        return ""
    return str(value)


def render_evidence_table(evidence_results: list[dict]) -> pd.DataFrame:
    rows = []
    for record in evidence_results or []:
        if not isinstance(record, dict):
            continue
        rows.append(
            {
                "evidence_id": record.get("evidence_id"),
                "document_type": record.get("document_type"),
                "evidence_type_id": record.get("evidence_type_id"),
                "evidence_role": record.get("evidence_role"),
                "ui_status": record.get("ui_status"),
                "status": record.get("status"),
                "source_id": record.get("source_id"),
                "period_start": record.get("period_start"),
                "period_end": record.get("period_end"),
                "linked_gap_ticket_ids": _as_csv(record.get("linked_gap_ticket_ids", [])),
            }
        )

    if not rows:
        st.info("No evidence records for this filter.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df


def render_findings_table(gap_tickets: list[dict]) -> pd.DataFrame:
    rows = []
    for ticket in gap_tickets or []:
        if not isinstance(ticket, dict):
            continue
        rows.append(
            {
                "gap_ticket_id": ticket.get("gap_ticket_id"),
                "title": ticket.get("title"),
                "primary_assertion": ticket.get("primary_assertion"),
                "finding_type": ticket.get("finding_type"),
                "status": ticket.get("status"),
                "severity": _severity_text(ticket.get("severity")),
                "affected_location": ticket.get("affected_location"),
                "trigger_ids": _as_csv(ticket.get("trigger_ids", [])),
            }
        )

    if not rows:
        st.info("No findings for this filter.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df


def render_workbook_table(workbook_results: list[dict]) -> pd.DataFrame:
    rows = []
    for record in workbook_results or []:
        if not isinstance(record, dict):
            continue
        rows.append(
            {
                "sheet_name": record.get("sheet_name"),
                "cell_or_range": record.get("cell_or_range"),
                "observation_type": record.get("observation_type"),
                "displayed_value": record.get("displayed_value"),
                "related_gap_ticket_ids": _as_csv(record.get("related_gap_ticket_ids", [])),
            }
        )

    if not rows:
        st.info("No workbook observations for this filter.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df
