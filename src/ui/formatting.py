from __future__ import annotations

import re
from typing import Any


# Leading implementation-style evidence token, e.g. "EV-AGG-2023-001 ".
_LEADING_EVIDENCE_TOKEN = re.compile(r"^\s*EV-[A-Z0-9]+(?:-[A-Z0-9]+)*\s+", re.IGNORECASE)
# Real equipment/unit identifiers we must preserve, e.g. BLR-001, GEN-001.
_UNIT_ID = r"[A-Z]{2,4}-\d{2,3}"


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


def _format_number(value: float) -> str:
    """Readable number: thousands separators, no trailing zeros for floats."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    # float
    if value == int(value) and abs(value) < 1e16:
        return f"{int(value):,}"
    text = f"{value:,.5f}".rstrip("0").rstrip(".")
    return text or "0"


def format_display_value(value: Any) -> str:
    """Render a prepared/reviewed value as readable, auditor-friendly text.

    Pure helper (no Streamlit). Intentionally separate from ``safe_text`` so
    unrelated pages keep their existing behavior.

    - None -> empty string
    - bool -> Yes / No
    - str -> unchanged
    - int / float -> readable number (thousands separators, trimmed decimals)
    - list / tuple -> comma-separated formatted items (no brackets/quotes)
    - dict -> "Label: value" pairs joined with "; "
    - nested values -> formatted recursively
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return _format_number(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return ", ".join(format_display_value(item) for item in items)
    if isinstance(value, dict):
        pairs = []
        for key, item in value.items():
            label = safe_text(key).replace("_", " ").strip()
            label = label[:1].upper() + label[1:] if label else label
            pairs.append(f"{label}: {format_display_value(item)}")
        return "; ".join(pairs)
    return safe_text(value)


def sanitize_source_snippet(value: Any) -> str:
    """Convert implementation-style snippet text into normal document language.

    - Strips a leading evidence token such as ``EV-AGG-2023-001``.
    - Preserves real equipment/unit identifiers (e.g. ``BLR-001``, ``GEN-001``).
    - Normalizes the known aggregation phrasing into a readable sentence.
    """
    text = safe_text(value).strip()
    if not text:
        return ""

    had_leading_token = bool(_LEADING_EVIDENCE_TOKEN.match(text))
    text = _LEADING_EVIDENCE_TOKEN.sub("", text).strip()

    # If a leading evidence token was removed and the sentence now begins with a
    # bare verb like "groups ...", give it a human subject.
    if had_leading_token and re.match(r"^groups\b", text, re.IGNORECASE):
        text = "This worksheet " + text[:1].lower() + text[1:]

    # Oxford "and" before the final unit id in a comma list: "A, B, C for" -> "A, B, and C for".
    text = re.sub(
        rf"(,\s*)({_UNIT_ID})(\s+for\b)",
        r"\1and \2\3",
        text,
    )
    # "for 2023 annual roll-up" -> "for the 2023 annual roll-up".
    text = re.sub(r"\bfor\s+((?:19|20)\d{2})\s+annual\s+roll-?up", r"for the \1 annual roll-up", text)

    return text.strip()
