from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.ui.formatting import assertion_label, category_label, normalize_severity, severity_label, status_label


VIEW_MODE_CREATED = "Created Findings"
VIEW_MODE_ALL = "All Findings"
NOT_AVAILABLE_FALLBACK = "Not available in the current finding record."

TITLE_MAP = {
    "GT-DEMO-GAP-002": "Pilot-light emissions are omitted under a federal exemption that requires state-level review.",
    "GT-DEMO-GAP-003": "October natural gas is entered at 10x the source bill — 281,000 MMBtu in the workbook versus 28,100 on the utility bill.",
    "GT-DEMO-GAP-004": "Boilers and the diesel generator are combined into one emissions line.",
    "GT-DEMO-GAP-005": "A natural-gas emission factor was applied to solid biomass months.",
    "GT-DEMO-GAP-006": "The biomass monthly composite lacks weekly sampling support.",
    "GT-DEMO-GAP-007": "December's estimated value has no documented substitution method.",
    "GT-DEMO-GAP-008": "Billing evidence covers only part of the year.",
    "GT-DEMO-GAP-009": "A cross-year gas bill is booked entirely to 2023 without allocation.",
    "GT-DEMO-GAP-010": "The workbook GWP basis requires regulatory confirmation.",
}

CATEGORY_BY_TICKET = {
    "GT-DEMO-GAP-002": "Missing evidence",
    "GT-DEMO-GAP-003": "Data mismatch",
    "GT-DEMO-GAP-004": "Boundary or aggregation",
    "GT-DEMO-GAP-005": "Methodology or factor",
    "GT-DEMO-GAP-006": "Sampling support",
    "GT-DEMO-GAP-007": "Unsupported estimate",
    "GT-DEMO-GAP-008": "Missing evidence",
    "GT-DEMO-GAP-009": "Cutoff or allocation",
    "GT-DEMO-GAP-010": "GWP or conversion basis",
}

_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}


def _clean_ticket_id(ticket_id: Any) -> str:
    return str(ticket_id or "").strip()


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _severity_rank(value: Any) -> int:
    return _SEVERITY_RANK.get(normalize_severity(value), 99)


def resolve_effective_severity(system_severity: Any, auditor_severity: Any) -> str:
    return severity_label(auditor_severity or system_severity)


def build_gap_view(ticket: dict, created_ids: set[str], overrides: dict[str, dict]) -> dict:
    raw_ticket = deepcopy(ticket) if isinstance(ticket, dict) else {}
    ticket_id = _clean_ticket_id(raw_ticket.get("gap_ticket_id"))
    issue = _as_dict(raw_ticket.get("issue"))
    remediation = _as_dict(raw_ticket.get("remediation"))
    severity = _as_dict(raw_ticket.get("severity"))
    override = _as_dict(overrides.get(ticket_id))

    system_severity = _as_string(severity.get("system_suggested"))
    auditor_severity = _as_string(override.get("severity") or severity.get("auditor_assigned"))
    effective_severity = resolve_effective_severity(system_severity, auditor_severity)

    return {
        "id": ticket_id,
        "title": _as_string(
            override.get("auditor_title")
            or TITLE_MAP.get(ticket_id)
            or raw_ticket.get("title")
            or "Untitled finding"
        ),
        "category": _as_string(
            CATEGORY_BY_TICKET.get(ticket_id)
            or category_label(raw_ticket.get("finding_type"))
        ),
        "system_severity": severity_label(system_severity),
        "auditor_severity": severity_label(auditor_severity) if auditor_severity else "",
        "effective_severity": effective_severity,
        "status": status_label(raw_ticket.get("status")),
        "status_raw": _as_string(raw_ticket.get("status")),
        "assertion": assertion_label(raw_ticket.get("primary_assertion")),
        "assertion_raw": _as_string(raw_ticket.get("primary_assertion")),
        "observed": _as_string(override.get("observed_condition") or issue.get("observed_condition")),
        "expected": _as_string(issue.get("expected_condition")),
        "why": _as_string(override.get("why_triggered") or issue.get("why_triggered")),
        "action": _as_string(override.get("recommended_action") or remediation.get("recommended_action")),
        "created": ticket_id in created_ids,
        "ticket": raw_ticket,
        "prepared_order": 0,
    }


def build_gap_views(
    tickets: list[dict],
    created_ids: set[str],
    overrides: dict[str, dict],
    *,
    excluded_ids: set[str] | None = None,
) -> list[dict]:
    blocked = {"GT-DEMO-GAP-001"}
    if isinstance(excluded_ids, set):
        blocked |= {_clean_ticket_id(item) for item in excluded_ids if _clean_ticket_id(item)}

    views: list[dict] = []
    for index, ticket in enumerate(tickets):
        if not isinstance(ticket, dict):
            continue
        ticket_id = _clean_ticket_id(ticket.get("gap_ticket_id"))
        if not ticket_id or ticket_id in blocked:
            continue
        view = build_gap_view(ticket, created_ids, overrides)
        view["prepared_order"] = index
        views.append(view)
    return views


def derive_summary_counts(gap_views: list[dict]) -> dict[str, int]:
    counts = {
        "total": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "informational": 0,
        "created": 0,
    }
    for view in gap_views:
        if not isinstance(view, dict):
            continue
        counts["total"] += 1
        if bool(view.get("created")):
            counts["created"] += 1

        system_severity = normalize_severity(view.get("system_severity"))
        if system_severity in counts:
            counts[system_severity] += 1
    return counts


def gap_filter_options(gap_views: list[dict]) -> dict[str, list[str]]:
    severities = sorted({str(view.get("effective_severity") or "") for view in gap_views if str(view.get("effective_severity") or "")}, key=lambda item: _severity_rank(item))
    statuses = sorted({str(view.get("status") or "") for view in gap_views if str(view.get("status") or "")})
    categories = sorted({str(view.get("category") or "") for view in gap_views if str(view.get("category") or "")})
    assertions = sorted({str(view.get("assertion") or "") for view in gap_views if str(view.get("assertion") or "")})

    return {
        "severity": ["All", *severities],
        "status": ["All", *statuses],
        "category": ["All", *categories],
        "audit_objective": ["All", *assertions],
    }


def apply_gap_filters(
    gap_views: list[dict],
    *,
    view_mode: str,
    severity_filter: str,
    status_filter: str,
    category_filter: str,
    audit_objective_filter: str,
) -> list[dict]:
    filtered: list[dict] = []
    for view in gap_views:
        if not isinstance(view, dict):
            continue

        if view_mode == VIEW_MODE_CREATED and not bool(view.get("created")):
            continue
        if severity_filter != "All" and str(view.get("effective_severity") or "") != severity_filter:
            continue
        if status_filter != "All" and str(view.get("status") or "") != status_filter:
            continue
        if category_filter != "All" and str(view.get("category") or "") != category_filter:
            continue
        if audit_objective_filter != "All" and str(view.get("assertion") or "") != audit_objective_filter:
            continue

        filtered.append(view)

    return filtered


def sort_gap_views(gap_views: list[dict]) -> list[dict]:
    typed = [view for view in gap_views if isinstance(view, dict)]
    return sorted(
        typed,
        key=lambda view: (
            0 if bool(view.get("created")) else 1,
            _severity_rank(view.get("effective_severity")),
            int(view.get("prepared_order") or 0),
            _clean_ticket_id(view.get("id")),
        ),
    )


def ensure_selected_gap_id(gap_views: list[dict], selected_id: str | None) -> str | None:
    ids = [_clean_ticket_id(item.get("id")) for item in gap_views if isinstance(item, dict)]
    ids = [item for item in ids if item]
    selected = _clean_ticket_id(selected_id)
    if selected and selected in ids:
        return selected
    if ids:
        return ids[0]
    return None


def find_gap_view(gap_views: list[dict], ticket_id: str | None) -> dict | None:
    selected = _clean_ticket_id(ticket_id)
    if not selected:
        return None
    for view in gap_views:
        if not isinstance(view, dict):
            continue
        if _clean_ticket_id(view.get("id")) == selected:
            return view
    return None
