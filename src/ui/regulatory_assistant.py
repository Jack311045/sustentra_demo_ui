from __future__ import annotations

import re
from typing import Any

UNKNOWN_REVIEWED_SET_MESSAGE = (
    "I do not have a reviewed answer for that question in the current verified regulatory set. "
    "Select one of the reviewed questions below or consult the cited regulation before relying on an answer."
)

GAP010_REVIEW_NOTICE = (
    "This regulatory interpretation is under source review and is not included in the verified assistant knowledge set."
)

_BASIS_TRAILER_RE = re.compile(r"\(\s*Basis\s*:\s*(?P<basis>.*?)\)\s*$", re.IGNORECASE | re.DOTALL)
_PLAIN_BASIS_TRAILER_RE = re.compile(r"\bBasis\s*:\s*(?P<basis>.*?)\s*$", re.IGNORECASE | re.DOTALL)
_CITATION_TOKEN_RE = re.compile(
    r"\d+\s+NYCRR\s+\d+(?:(?:-\d+(?:\.\d+)*)|(?:\.\d+))?(?:\([a-z0-9]+\))*|"
    r"(?:§\s*)?\d{3}(?:(?:-\d+(?:\.\d+)*)|(?:\.\d+))?(?:\([a-z0-9]+\))*",
    re.IGNORECASE,
)


def _is_confirmed_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not text.lower().startswith("needs confirmation")


def _expand_parenthetical_and(part: str) -> list[str]:
    match = re.match(
        r"^(?P<prefix>.+?)\((?P<first>\d+)\)\s+and\s+\((?P<second>\d+)\)$",
        part.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    prefix = match.group("prefix").strip()
    first = match.group("first")
    second = match.group("second")

    if not prefix:
        return []

    return [f"{prefix}({first})", f"{prefix}({second})"]


def _extract_citation_tokens(part: str) -> list[str]:
    tokens = [token.strip() for token in _CITATION_TOKEN_RE.findall(part) if token.strip()]
    cleaned: list[str] = []
    for token in tokens:
        normalized = re.sub(r"\s+", " ", token).strip()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _split_basis_entries(basis_raw: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(basis_raw or "")).strip().strip(".")
    if not normalized:
        return []

    parts = [part.strip().strip(".") for part in normalized.split(";") if part.strip()]
    entries: list[str] = []

    for part in parts:
        expanded = _expand_parenthetical_and(part)
        if expanded:
            entries.extend(expanded)
            continue

        extracted = _extract_citation_tokens(part)
        if extracted:
            entries.extend(extracted)
        else:
            entries.append(part)

    deduped: list[str] = []
    for entry in entries:
        if entry not in deduped:
            deduped.append(entry)
    return deduped


def parse_basis_clause(answer_text: str) -> tuple[str, list[str]]:
    text = str(answer_text or "").strip()
    if not text:
        return "", []

    match = _BASIS_TRAILER_RE.search(text)
    if match:
        body = text[: match.start()].rstrip()
        citations = _split_basis_entries(match.group("basis") or "")
        return body, citations

    plain_match = _PLAIN_BASIS_TRAILER_RE.search(text)
    if not plain_match:
        return text, []

    body = text[: plain_match.start()].rstrip().rstrip(".")
    citations = _split_basis_entries(plain_match.group("basis") or "")
    return body, citations


def resolve_curated_answer(chat_suggestions: list[dict], question: str) -> str | None:
    if not isinstance(question, str) or not question.strip():
        return None

    for item in chat_suggestions:
        if not isinstance(item, dict):
            continue
        candidate_question = str(item.get("question") or "")
        if candidate_question == question:
            return str(item.get("mock_answer") or "")

    return None


def build_audit_context_lines(audit_setup: dict, analysis_response: dict) -> list[str]:
    profile = audit_setup.get("company_and_facility_profile") if isinstance(audit_setup, dict) else {}
    boundary = audit_setup.get("reporting_boundary") if isinstance(audit_setup, dict) else {}
    regulation = audit_setup.get("regulation_and_verification") if isinstance(audit_setup, dict) else {}
    engagement = analysis_response.get("engagement") if isinstance(analysis_response, dict) else {}

    facts: list[tuple[str, Any]] = [
        ("Facility", (profile.get("facility_name") if isinstance(profile, dict) else None) or (engagement.get("facility_name") if isinstance(engagement, dict) else None)),
        ("Reporting period", profile.get("reporting_period") if isinstance(profile, dict) else None),
        ("Primary regulation", regulation.get("primary_regulation") if isinstance(regulation, dict) else None),
        ("Consolidation approach", boundary.get("consolidation_approach") if isinstance(boundary, dict) else None),
        ("Assurance standard", regulation.get("verification_standard") if isinstance(regulation, dict) else None),
        ("Assurance level", regulation.get("assurance_level") if isinstance(regulation, dict) else None),
    ]

    lines: list[str] = []
    for label, value in facts:
        if _is_confirmed_text(value):
            lines.append(f"{label}: {str(value).strip()};")

    return lines
