from __future__ import annotations

from typing import Any


ASSERTION_LABELS = {
    "accuracy_valuation": "Accuracy",
    "occurrence_existence": "Existence and occurrence",
    "completeness": "Completeness",
    "cutoff": "Cutoff",
    "classification": "Classification",
    "presentation": "Presentation",
}


CATEGORY_LABELS = {
    "missing_record_or_source": "Missing evidence",
    "quantity_or_value_mismatch": "Data mismatch",
    "aggregation_error": "Boundary or aggregation",
    "emission_factor_mismatch": "Methodology or factor",
    "sampling_chain_failure": "Sampling support",
    "unsupported_estimate_or_substitution": "Unsupported estimate",
    "cutoff_or_period_allocation": "Cutoff or allocation",
    "gwp_basis_mismatch": "GWP or conversion basis",
}


STATUS_LABELS = {
    "candidate": "Open",
    "flagged": "Flagged",
    "need_review": "Needs review",
    "pass": "Accepted",
    "accepted_for_extraction": "Accepted",
    "accepted_supporting_evidence_only": "Accepted",
    "flagged_for_auditor_review": "Flagged",
    "resolved": "Resolved",
}


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}


def safe_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_severity(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("auditor_assigned") or value.get("system_suggested")
    else:
        raw = value
    text = safe_text(raw).strip().lower()
    return text or "informational"


def severity_label(value: Any) -> str:
    severity = normalize_severity(value)
    if severity == "critical":
        return "Critical"
    if severity == "high":
        return "High"
    if severity == "medium":
        return "Medium"
    if severity == "low":
        return "Low"
    return "Informational"


def severity_rank(value: Any) -> int:
    return SEVERITY_ORDER.get(normalize_severity(value), 99)


def status_label(value: Any) -> str:
    key = safe_text(value).strip().lower()
    return STATUS_LABELS.get(key, safe_text(value) or "Unknown")


def assertion_label(value: Any) -> str:
    key = safe_text(value).strip().lower()
    return ASSERTION_LABELS.get(key, safe_text(value) or "Audit objective")


def category_label(value: Any) -> str:
    key = safe_text(value).strip().lower()
    return CATEGORY_LABELS.get(key, safe_text(value) or "General")


def format_bytes(num_bytes: Any) -> str:
    try:
        value = int(num_bytes)
    except (TypeError, ValueError):
        return "Unknown size"

    units = ["bytes", "KB", "MB", "GB"]
    amount = float(value)
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(amount)} {units[unit_index]}"
    return f"{amount:.1f} {units[unit_index]}"


def format_value_with_unit(value: Any, unit: Any) -> str:
    value_text = safe_text(value)
    unit_text = safe_text(unit)
    if value_text and unit_text:
        return f"{value_text} {unit_text}"
    return value_text or "N/A"


def is_internal_routing_evidence(evidence_id: Any) -> bool:
    return safe_text(evidence_id).strip().upper() == "EV-PACK-INDEX-2023-000"
