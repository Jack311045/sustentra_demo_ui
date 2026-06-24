from __future__ import annotations

from typing import Any

import streamlit as st


NOT_AVAILABLE_IN_RECORD = "Not available in the current finding record."


def _check_icon(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"pass", "ok", "accepted"}:
        return "✓"
    if normalized in {"fail", "error"}:
        return "✕"
    return "⚑"


def _check_label(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"pass", "ok", "accepted"}:
        return "Pass"
    if normalized in {"fail", "error"}:
        return "Fail"
    return "Flag"


def render_reasoning_trail(checks: list[dict]) -> None:
    checks = [item for item in checks if isinstance(item, dict)]
    if not checks:
        st.info("No reasoning trail checks are available for this record.")
        return

    for check in checks:
        label = str(check.get("label") or check.get("check_id") or "Check")
        status = str(check.get("status") or check.get("outcome") or "flag")
        observed = check.get("observed")
        expected = check.get("expected")
        explanation = str(check.get("explanation") or check.get("message") or "")

        with st.container(border=True):
            st.markdown(f"**{_check_icon(status)} {label}**")
            st.caption(f"{_check_label(status)}")
            if explanation:
                st.write(explanation)
            if observed is not None:
                st.write(f"Observed: {observed}")
            if expected is not None:
                st.write(f"Expected: {expected}")


def humanize_rule_key(key: str) -> str:
    text = str(key or "").strip().replace("_", " ").replace("-", " ")
    if not text:
        return "Value"
    return text[0].upper() + text[1:]


def format_rule_values(values: Any) -> str:
    if values is None:
        return "None"
    if isinstance(values, bool):
        return "true" if values else "false"
    if isinstance(values, (int, float)):
        if isinstance(values, float) and values.is_integer():
            return f"{int(values):,}"
        return f"{values:,}" if isinstance(values, int) else f"{values:,.4f}".rstrip("0").rstrip(".")
    if isinstance(values, str):
        return values.strip()
    if isinstance(values, list):
        formatted = [format_rule_values(item) for item in values]
        return ", ".join([item for item in formatted if item])
    if isinstance(values, dict):
        parts: list[str] = []
        for raw_key, raw_value in values.items():
            parts.append(f"{humanize_rule_key(str(raw_key))}: {format_rule_values(raw_value)}")
        return "; ".join(parts)
    return str(values)


def _extract_inputs(rule_results: list[dict]) -> list[str]:
    tokens: list[str] = []
    for result in rule_results:
        snapshot = result.get("input_snapshot") if isinstance(result.get("input_snapshot"), dict) else {}
        workbook_cell = str(snapshot.get("workbook_cell") or "").strip()
        evidence_id = str(snapshot.get("evidence_id") or "").strip()
        if workbook_cell and workbook_cell not in tokens:
            tokens.append(workbook_cell)
        if evidence_id and evidence_id not in tokens:
            tokens.append(evidence_id)
    return tokens


def _extract_comparison(rule_results: list[dict]) -> tuple[str, str] | None:
    for result in rule_results:
        observed = result.get("observed") if isinstance(result.get("observed"), dict) else {}
        expected = result.get("expected") if isinstance(result.get("expected"), dict) else {}

        observed_value = (
            observed.get("workbook_quantity_mmbtu")
            or observed.get("value")
            or next(iter(observed.values()), None)
        )
        expected_value = (
            expected.get("source_bill_quantity_mmbtu")
            or expected.get("value")
            or next(iter(expected.values()), None)
        )

        if observed_value is None and expected_value is None:
            continue

        return format_rule_values(observed_value), format_rule_values(expected_value)
    return None


def _extract_difference(rule_results: list[dict]) -> str | None:
    for result in rule_results:
        output = result.get("output_snapshot") if isinstance(result.get("output_snapshot"), dict) else {}
        diff = output.get("absolute_difference_mmbtu")
        if diff is not None:
            return f"Detected a {format_rule_values(diff)} MMBtu overstatement."
        if output:
            return f"Computed output snapshot: {format_rule_values(output)}."
    return None


def _extract_outcome(rule_results: list[dict]) -> str:
    for result in rule_results:
        outcome = str(result.get("outcome") or "").strip().lower()
        if outcome in {"fail", "error"}:
            return "Raised the finding for auditor review."
        if outcome in {"flag", "flagged", "warning"}:
            return "Flagged the finding for auditor review."
        if outcome in {"pass", "ok", "accepted"}:
            return "No finding was raised by this rule evaluation."
    return "Captured the rule outcome for auditor review."


def build_ai_reasoning_steps(rule_results: list[dict]) -> list[str]:
    typed = [item for item in rule_results if isinstance(item, dict)]
    if not typed:
        return [
            "Pulled the available finding inputs.",
            "Compared observed and expected values from the rule output.",
            "Calculated the rule output and difference.",
            "Raised the finding for auditor review.",
        ]

    steps: list[str] = []

    inputs = _extract_inputs(typed)
    if inputs:
        steps.append(f"Pulled {', '.join(inputs)}.")
    else:
        steps.append("Pulled the available finding inputs.")

    comparison = _extract_comparison(typed)
    if comparison:
        observed_value, expected_value = comparison
        if observed_value and expected_value:
            steps.append(f"Compared {observed_value} against {expected_value}.")
        else:
            steps.append("Compared observed and expected values from the rule output.")
    else:
        steps.append("Compared observed and expected values from the rule output.")

    difference_step = _extract_difference(typed)
    if difference_step:
        steps.append(difference_step)
    else:
        steps.append("Calculated the rule output and difference.")

    steps.append(_extract_outcome(typed))
    return steps


def render_ai_reasoning(rule_results: list[dict]) -> None:
    steps = build_ai_reasoning_steps(rule_results)
    st.caption("How the system reached this finding")
    for index, step in enumerate(steps, start=1):
        st.write(f"{index}. {step}")


def render_evidence_trace(evidence_refs: list[dict]) -> None:
    evidence_refs = [item for item in evidence_refs if isinstance(item, dict)]
    if not evidence_refs:
        st.caption("No linked evidence is available for this finding.")
        return

    for evidence in evidence_refs:
        evidence_id = evidence.get("evidence_id") or "Unknown evidence"
        relationship = evidence.get("relationship_to_gap") or "linked evidence"
        source_locations = evidence.get("source_locations") if isinstance(evidence.get("source_locations"), list) else []

        with st.container(border=True):
            st.write(f"**{evidence_id}** ({relationship})")
            if source_locations:
                first = source_locations[0] if isinstance(source_locations[0], dict) else {}
                page = first.get("page_number")
                snippet = first.get("source_snippet")
                if page is not None:
                    st.caption(f"Source page: {page}")
                if snippet:
                    st.write(snippet)


def render_regulatory_basis(citations: list[dict]) -> None:
    citations = [item for item in citations if isinstance(item, dict)]
    if not citations:
        st.caption("No regulatory citation is available for this finding.")
        return

    for citation in citations:
        authority = citation.get("authority") or "Authority"
        citation_code = citation.get("citation") or "Citation"
        summary = citation.get("requirement_summary") or "Regulatory summary"
        applicability = citation.get("applicability_explanation") or NOT_AVAILABLE_IN_RECORD

        with st.container(border=True):
            st.write(f"**{authority} {citation_code}**")
            st.write(f"Regulatory summary: {summary}")
            st.caption(f"Applicability: {applicability}")


def summarize_workbook_trace(location: dict[str, Any] | None) -> str:
    if not isinstance(location, dict):
        return "No workbook location is linked to this finding."
    sheet = location.get("sheet_name")
    cell = location.get("cell_or_range")
    if sheet and cell:
        return f"{sheet}!{cell}"
    return "No workbook location is linked to this finding."
