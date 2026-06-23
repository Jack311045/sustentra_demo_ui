from __future__ import annotations

import re
from datetime import date
from typing import Any

_STATUS_PASS = "pass"
_STATUS_FLAGGED = "flagged"
_STATUS_FAIL = "fail"
_STATUS_UNKNOWN = "unknown"

_MONTH_INDEX = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


# Exact auditor-facing wording keyed by (validation_id, check_id).
_EXACT_CHECK_TEXT: dict[tuple[str, str], dict[str, str]] = {
    (
        "VAL-NG-2023-010",
        "facility_match",
    ): {
        "question": "Is this bill for the Baldwinsville facility?",
        "answer": "Yes",
    },
    (
        "VAL-NG-2023-010",
        "fuel_identified",
    ): {
        "question": "Is the fuel natural gas, as expected for this source?",
        "answer": "Yes",
    },
    (
        "VAL-NG-2023-010",
        "reporting_period_check",
    ): {
        "question": "Does the service period fall inside the 2023 reporting year?",
        "answer": "Yes — October 1-31, 2023",
    },
    (
        "VAL-NG-2023-010",
        "workbook_reconciliation",
    ): {
        "question": "Does the workbook figure match the source bill?",
        "answer": "No — workbook shows 281,000 MMBtu vs 28,100 on the bill (10x)",
    },
    (
        "VAL-BLR003-2023-009",
        "fuel_identified",
    ): {
        "question": "Is the fuel correctly identified as solid biomass?",
        "answer": "Yes",
    },
    (
        "VAL-BLR003-2023-009",
        "factor_alignment",
    ): {
        "question": "Is the right emission factor applied for this fuel?",
        "answer": "No — a natural-gas factor was applied to biomass",
    },
    (
        "VAL-LAB-2023-001",
        "sampling_chain",
    ): {
        "question": "Is there enough sampling support behind the biomass figure?",
        "answer": "No — only a single lab report; weekly logs and composite preparation are missing",
    },
    (
        "VAL-NG-2023-012",
        "period_cutoff",
    ): {
        "question": "Does this bill belong entirely to 2023?",
        "answer": "No — the service period runs into 2024 and needs allocation between years",
    },
}


def normalize_validation_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "ok", "accepted"}:
        return _STATUS_PASS
    if status in {"fail", "error"}:
        return _STATUS_FAIL
    if status in {"flag", "flagged", "warning", "need_review", "needs_review"}:
        return _STATUS_FLAGGED
    return _STATUS_UNKNOWN


def validation_status_label(value: Any) -> str:
    status = normalize_validation_status(value)
    if status == _STATUS_PASS:
        return "Pass"
    if status == _STATUS_FAIL:
        return "Fail"
    if status == _STATUS_FLAGGED:
        return "Flagged"
    return "Status unavailable"


def validation_status_rank(value: Any) -> int:
    status = normalize_validation_status(value)
    if status == _STATUS_FAIL:
        return 0
    if status == _STATUS_FLAGGED:
        return 1
    if status == _STATUS_PASS:
        return 2
    return 3


def sort_validation_records(records: list[dict]) -> list[dict]:
    typed = [item for item in records if isinstance(item, dict)]
    indexed = list(enumerate(typed))
    indexed.sort(key=lambda pair: (validation_status_rank(pair[1].get("overall_status")), pair[0]))
    return [record for _, record in indexed]


def sort_validation_checks(checks: list[dict]) -> list[dict]:
    typed = [item for item in checks if isinstance(item, dict)]
    indexed = list(enumerate(typed))
    indexed.sort(key=lambda pair: (validation_status_rank(pair[1].get("status")), pair[0]))
    return [check for _, check in indexed]


def _friendly_check_label(check: dict) -> str:
    label = str(check.get("label") or check.get("check_id") or "validation check")
    text = label.replace("_", " ").replace("-", " ").strip()
    if not text:
        return "validation check"
    return text[0].upper() + text[1:]


def _fallback_question(check: dict) -> str:
    return f"Is {_friendly_check_label(check).lower()} acceptable?"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _fallback_answer(check: dict) -> str:
    status = normalize_validation_status(check.get("status"))
    explanation = _first_nonempty(check.get("explanation"), check.get("message"))
    observed = _first_nonempty(check.get("observed"))
    expected = _first_nonempty(check.get("expected"))

    if status == _STATUS_PASS:
        return f"Yes{(' — ' + explanation) if explanation else ''}"

    detail = explanation
    if not detail and observed and expected:
        detail = f"observed {observed}; expected {expected}"
    elif not detail and observed:
        detail = f"observed {observed}"
    elif not detail and expected:
        detail = f"expected {expected}"

    if status in {_STATUS_FAIL, _STATUS_FLAGGED}:
        return f"No{(' — ' + detail) if detail else ''}"

    if detail:
        return f"Status unavailable — {detail}"
    return "Status unavailable"


def _answer_tone(answer: str, status: Any) -> str:
    if str(answer).strip().lower().startswith("yes"):
        return "positive"
    normalized = normalize_validation_status(status)
    if normalized == _STATUS_FLAGGED:
        return "warning"
    if normalized == _STATUS_FAIL:
        return "negative"
    if str(answer).strip().lower().startswith("no"):
        return "negative"
    return "neutral"


def resolve_check_display(validation_id: str, check: dict) -> dict[str, str]:
    check_id = str(check.get("check_id") or "").strip()
    mapping = _EXACT_CHECK_TEXT.get((validation_id, check_id))
    if mapping:
        answer = mapping["answer"]
        return {
            "question": mapping["question"],
            "answer": answer,
            "tone": _answer_tone(answer, check.get("status")),
        }

    answer = _fallback_answer(check)
    return {
        "question": _fallback_question(check),
        "answer": answer,
        "tone": _answer_tone(answer, check.get("status")),
    }


def _parse_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    year, month, day = (int(part) for part in text.split("-"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_reporting_period_bounds(audit_setup: dict | None) -> tuple[date | None, date | None, str]:
    setup = audit_setup if isinstance(audit_setup, dict) else {}
    company = setup.get("company_and_facility_profile") if isinstance(setup.get("company_and_facility_profile"), dict) else {}
    details = setup.get("engagement_details") if isinstance(setup.get("engagement_details"), dict) else {}

    text = str(company.get("reporting_period") or details.get("reporting_period") or "").strip()
    if not text:
        return None, None, ""

    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})", text)
    if not match:
        return None, None, text

    start = _parse_date(match.group(1))
    end = _parse_date(match.group(2))
    return start, end, text


def _month_key(record: dict) -> int | None:
    extracted = record.get("extracted_fields") if isinstance(record.get("extracted_fields"), dict) else {}
    month_label = str(extracted.get("billing_month_label") or "").strip().lower()
    if month_label in _MONTH_INDEX:
        return _MONTH_INDEX[month_label]

    period_start = _parse_date(record.get("period_start"))
    if period_start:
        return period_start.month
    return None


def _looks_like_natural_gas_bill(record: dict) -> bool:
    extracted = record.get("extracted_fields") if isinstance(record.get("extracted_fields"), dict) else {}
    fuel = str(extracted.get("fuel_or_service_type") or extracted.get("fuel_type") or "").strip().lower()
    doc = str(record.get("document_type") or record.get("evidence_type_name") or "").strip().lower()
    evidence_type = str(record.get("evidence_type_id") or "").strip().upper()

    if evidence_type == "J2-001":
        return True
    if "natural gas" in fuel:
        return True
    return "natural gas" in doc and "bill" in doc


def derive_monthly_evidence_coverage(analysis_response: dict | None, audit_setup: dict | None) -> dict[str, Any]:
    response = analysis_response if isinstance(analysis_response, dict) else {}
    evidence = [item for item in (response.get("evidence_results") or []) if isinstance(item, dict)]

    ng_records = [record for record in evidence if _looks_like_natural_gas_bill(record)]
    reporting_start, reporting_end, reporting_text = _parse_reporting_period_bounds(audit_setup)

    received_months = {month for month in (_month_key(record) for record in ng_records) if month is not None}

    fully_within = 0
    cross_year = 0
    if reporting_start and reporting_end:
        for record in ng_records:
            start = _parse_date(record.get("period_start"))
            end = _parse_date(record.get("period_end"))
            if not start or not end:
                continue
            if start >= reporting_start and end <= reporting_end:
                fully_within += 1
            elif not (end < reporting_start or start > reporting_end):
                cross_year += 1

    expected_months = 0
    if reporting_start and reporting_end:
        expected_months = (reporting_end.year - reporting_start.year) * 12 + (reporting_end.month - reporting_start.month) + 1

    return {
        "received_count": len(received_months),
        "expected_count": expected_months,
        "fully_within_count": fully_within,
        "cross_year_count": cross_year,
        "reporting_period_text": reporting_text,
        "reporting_start": reporting_start,
        "reporting_end": reporting_end,
        "has_natural_gas_records": bool(ng_records),
    }


def format_monthly_coverage_banner(coverage: dict[str, Any]) -> str:
    received = int(coverage.get("received_count") or 0)
    expected = int(coverage.get("expected_count") or 0)
    fully = int(coverage.get("fully_within_count") or 0)
    cross = int(coverage.get("cross_year_count") or 0)
    start = coverage.get("reporting_start")
    end = coverage.get("reporting_end")

    if not coverage.get("has_natural_gas_records"):
        return "Monthly evidence coverage could not be derived because no natural-gas utility evidence records were found."

    if expected <= 0:
        return (
            f"Monthly evidence coverage: {received} bills received. "
            "Reporting-period boundaries are unavailable for cutoff classification."
        )

    if isinstance(start, date) and isinstance(end, date) and start.year == end.year:
        scope_text = str(start.year)
    elif coverage.get("reporting_period_text"):
        scope_text = str(coverage.get("reporting_period_text"))
    else:
        scope_text = "the reporting period"

    bill_word = "bill" if cross == 1 else "bills"
    return (
        f"Monthly evidence coverage: {received} / {expected} bills received · "
        f"{fully} fully within {scope_text} · "
        f"{cross} {bill_word} require cutoff allocation"
    )


def trace_note_for_check(check_id: str, audit_setup: dict | None) -> str | None:
    setup = audit_setup if isinstance(audit_setup, dict) else {}
    company = setup.get("company_and_facility_profile") if isinstance(setup.get("company_and_facility_profile"), dict) else {}
    regulation = setup.get("regulation_and_verification") if isinstance(setup.get("regulation_and_verification"), dict) else {}
    _, _, reporting_text = _parse_reporting_period_bounds(setup)

    if check_id == "facility_match":
        facility = str(company.get("facility_name") or "selected facility").strip()
        return f"From engagement setup: selected facility is {facility}."

    if check_id in {"reporting_period_check", "period_cutoff"}:
        if reporting_text:
            return f"From engagement setup: reporting period is {reporting_text}."
        return "From engagement setup: reporting period is unavailable."

    if check_id in {"factor_alignment", "fuel_identified", "sampling_chain"}:
        source_scope = str(regulation.get("source_categories") or "Scope 1 stationary combustion").strip()
        return f"From engagement setup: {source_scope} methodology is in scope."

    return None


def mapped_check_pairs() -> set[tuple[str, str]]:
    return set(_EXACT_CHECK_TEXT.keys())
