from __future__ import annotations

from datetime import datetime
import re

import streamlit as st

PREPARED_DISCLOSURE = (
    "Prepared demo workflow: some extraction, validation, calculation, and gap-analysis "
    "results are precomputed to demonstrate the intended auditor experience."
)


def parse_reporting_period_months(reporting_period: str) -> int | None:
    if not isinstance(reporting_period, str):
        return None

    text = reporting_period.strip()
    if not text:
        return None

    match = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s+(?:to|through|thru)\s+(\d{4}-\d{2}-\d{2})$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    try:
        start_date = datetime.strptime(match.group(1), "%Y-%m-%d")
        end_date = datetime.strptime(match.group(2), "%Y-%m-%d")
    except ValueError:
        return None

    if end_date < start_date:
        return None

    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1


def build_engagement_expectation_summary(
    selected_scopes: list[str],
    reporting_period: str,
    materiality_absolute: str,
) -> str:
    scopes_text = ", ".join(selected_scopes) if selected_scopes else "selected scopes"

    month_count = parse_reporting_period_months(reporting_period)
    if month_count is None:
        period_text = reporting_period or "configured reporting period"
        month_expectation = (
            f"Monthly source-record expectations follow the configured period text ({period_text})."
        )
    else:
        month_expectation = (
            f"Expected monthly source records: {month_count} per selected scope "
            f"({month_count * max(len(selected_scopes), 1)} total record slots)."
        )

    absolute_text = materiality_absolute or "750 tCO2e"
    return (
        f"Selected scopes: {scopes_text}. "
        f"{month_expectation} "
        "Checks include missing-month completeness and workbook-to-source reconciliation. "
        f"Configured absolute materiality input: {absolute_text} (prepared-demo context field)."
    )


def render_prepared_demo_disclosure() -> None:
    st.caption(PREPARED_DISCLOSURE)
