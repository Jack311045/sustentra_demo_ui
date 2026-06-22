from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui.formatting import assertion_label, category_label, severity_label, status_label


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


def render_validation_table(validation_results: list[dict]) -> pd.DataFrame:
    rows = []
    for record in validation_results or []:
        if not isinstance(record, dict):
            continue
        checks = record.get("checks") if isinstance(record.get("checks"), list) else []
        pass_count = 0
        fail_count = 0
        flag_count = 0
        for check in checks:
            if not isinstance(check, dict):
                continue
            status = str(check.get("status") or check.get("outcome") or "").lower()
            if status == "pass":
                pass_count += 1
            elif status == "fail":
                fail_count += 1
            else:
                flag_count += 1

        rows.append(
            {
                "validation_id": record.get("validation_id"),
                "record_label": record.get("record_label"),
                "evidence_id": record.get("evidence_id"),
                "overall_status": status_label(record.get("overall_status")),
                "pass_checks": pass_count,
                "fail_checks": fail_count,
                "flag_checks": flag_count,
                "next_check": record.get("next_check"),
            }
        )

    if not rows:
        st.info("No validation records for this filter.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df


def render_calculation_table(calculation_results: list[dict]) -> pd.DataFrame:
    rows = []
    for record in calculation_results or []:
        if not isinstance(record, dict):
            continue

        rows.append(
            {
                "calculation_id": record.get("calculation_id"),
                "source_or_fuel": record.get("source_or_fuel"),
                "activity_quantity": record.get("activity_quantity"),
                "activity_unit": record.get("activity_unit"),
                "factor_id": record.get("factor_id"),
                "recalculated_co2e_mt": record.get("recalculated_co2e_mt"),
                "workbook_co2e_mt": record.get("workbook_co2e_mt"),
                "difference_mt": record.get("difference_mt"),
                "status": status_label(record.get("status") or record.get("calculation_status")),
            }
        )

    if not rows:
        st.info("No calculation records are available.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df


def render_gap_overview_table(gap_tickets: list[dict]) -> pd.DataFrame:
    rows = []
    for ticket in gap_tickets or []:
        if not isinstance(ticket, dict):
            continue
        rows.append(
            {
                "gap_ticket_id": ticket.get("gap_ticket_id"),
                "title": ticket.get("auditor_title") or ticket.get("title"),
                "severity": severity_label(ticket.get("severity")),
                "category": category_label(ticket.get("auditor_category") or ticket.get("finding_type")),
                "audit_objective": assertion_label(ticket.get("primary_assertion")),
                "status": status_label(ticket.get("status")),
            }
        )

    if not rows:
        st.info("No gap tickets available.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    return df
