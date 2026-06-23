"""Derived helpers for the Extraction Review (Page 3) human-review gate.

This module intentionally contains no persisted "review_complete" flag. All
progress and gate state is derived from ``reviewed_extraction_fields`` on every
rerun. It also never writes ``analysis_response``; it only reads the prepared
demo data and the reviewer overlay.

Field confidence buckets are a non-destructive projection: ``extracted_fields``
are never mutated. When prepared data does not carry an explicit
``field_confidence`` block, buckets are derived from each record's ``ui_status``
with ``score=None`` and ``basis="prepared_demo"``.
"""

from __future__ import annotations

from typing import Any

from src.ui.formatting import is_internal_routing_evidence, safe_text


# Reviewer decision vocabulary.
UNCONFIRMED_STATUS = "Unconfirmed"
ACCEPTED_STATUS = "Accepted"
EDITED_STATUS = "Edited"
REJECTED_STATUS = "Rejected"
NEEDS_CLARIFICATION_STATUS = "Needs clarification"

# A field counts toward the gate once it carries any final decision.
FINAL_REVIEW_STATUSES = frozenset(
    {ACCEPTED_STATUS, EDITED_STATUS, REJECTED_STATUS, NEEDS_CLARIFICATION_STATUS}
)
# Only Accepted/Edited fields flow forward as auditor-approved inputs.
APPROVED_REVIEW_STATUSES = frozenset({ACCEPTED_STATUS, EDITED_STATUS})

_STATUS_ALIASES = {
    "unconfirmed": UNCONFIRMED_STATUS,
    "needs confirmation": UNCONFIRMED_STATUS,
    "accepted": ACCEPTED_STATUS,
    "accept": ACCEPTED_STATUS,
    "edited": EDITED_STATUS,
    "edit": EDITED_STATUS,
    "rejected": REJECTED_STATUS,
    "reject": REJECTED_STATUS,
    "needs clarification": NEEDS_CLARIFICATION_STATUS,
    "mark unclear": NEEDS_CLARIFICATION_STATUS,
    "unclear": NEEDS_CLARIFICATION_STATUS,
}

# Confidence buckets, ordered worst-to-best for precedence comparisons.
BUCKET_FAIL = "fail"
BUCKET_NEEDS_REVIEW = "needs_review"
BUCKET_PASS = "pass"

BUCKET_LABELS = {
    BUCKET_PASS: "Pass",
    BUCKET_NEEDS_REVIEW: "Needs review",
    BUCKET_FAIL: "Fail",
}

# Lower rank == worse condition (takes precedence when aggregating a record).
_BUCKET_RANK = {BUCKET_FAIL: 0, BUCKET_NEEDS_REVIEW: 1, BUCKET_PASS: 2}

_UI_STATUS_TO_BUCKET = {
    "pass": BUCKET_PASS,
    "accepted_for_extraction": BUCKET_PASS,
    "accepted_supporting_evidence_only": BUCKET_PASS,
    "need_review": BUCKET_NEEDS_REVIEW,
    "needs_review": BUCKET_NEEDS_REVIEW,
    "flagged": BUCKET_FAIL,
    "flagged_for_auditor_review": BUCKET_FAIL,
    "fail": BUCKET_FAIL,
}


def normalize_review_status(value: Any) -> str:
    """Map an arbitrary stored/displayed status to the canonical vocabulary."""
    text = safe_text(value).strip()
    if not text:
        return UNCONFIRMED_STATUS
    return _STATUS_ALIASES.get(text.lower(), text)


def bucket_from_ui_status(ui_status: Any, fallback_status: Any = None) -> str:
    key = safe_text(ui_status).strip().lower()
    if key in _UI_STATUS_TO_BUCKET:
        return _UI_STATUS_TO_BUCKET[key]
    fallback = safe_text(fallback_status).strip().lower()
    return _UI_STATUS_TO_BUCKET.get(fallback, BUCKET_NEEDS_REVIEW)


def get_field_confidence(record: dict, field_key: str) -> dict:
    """Return the additive confidence projection for a single field.

    Prefers an explicit ``field_confidence`` block if present in the prepared
    data; otherwise derives a bucket from the record ``ui_status``. The
    extracted value is never read or mutated here.
    """
    record = record if isinstance(record, dict) else {}
    explicit = record.get("field_confidence")
    if isinstance(explicit, dict):
        entry = explicit.get(field_key)
        if isinstance(entry, dict):
            bucket = safe_text(entry.get("bucket")).strip().lower()
            if bucket in _BUCKET_RANK:
                return {
                    "bucket": bucket,
                    "score": entry.get("score"),
                    "basis": entry.get("basis") or "prepared_demo",
                }

    bucket = bucket_from_ui_status(record.get("ui_status"), record.get("status"))
    return {"bucket": bucket, "score": None, "basis": "prepared_demo"}


def field_confidence_bucket(record: dict, field_key: str) -> str:
    return get_field_confidence(record, field_key).get("bucket", BUCKET_NEEDS_REVIEW)


def record_confidence_bucket(record: dict) -> str:
    """Worst-condition bucket across a record's extracted fields."""
    record = record if isinstance(record, dict) else {}
    extracted = record.get("extracted_fields")
    if not isinstance(extracted, dict) or not extracted:
        return bucket_from_ui_status(record.get("ui_status"), record.get("status"))

    worst = BUCKET_PASS
    for field_key in extracted:
        bucket = field_confidence_bucket(record, field_key)
        if _BUCKET_RANK.get(bucket, 1) < _BUCKET_RANK.get(worst, 2):
            worst = bucket
    return worst


def is_reviewable_record(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if is_internal_routing_evidence(record.get("evidence_id")):
        return False
    extracted = record.get("extracted_fields")
    return isinstance(extracted, dict) and bool(extracted)


def get_reviewable_evidence_records(analysis_response: dict | None) -> list[dict]:
    """Evidence records eligible for review (excludes internal routing docs)."""
    if not isinstance(analysis_response, dict):
        return []
    records = analysis_response.get("evidence_results")
    if not isinstance(records, list):
        return []
    return [item for item in records if is_reviewable_record(item)]


def get_internal_routing_records(analysis_response: dict | None) -> list[dict]:
    if not isinstance(analysis_response, dict):
        return []
    records = analysis_response.get("evidence_results")
    if not isinstance(records, list):
        return []
    return [
        item
        for item in records
        if isinstance(item, dict) and is_internal_routing_evidence(item.get("evidence_id"))
    ]


def get_field_review_status(reviewed_map: dict | None, field_key: str) -> str:
    if not isinstance(reviewed_map, dict):
        return UNCONFIRMED_STATUS
    entry = reviewed_map.get(field_key)
    if isinstance(entry, dict):
        return normalize_review_status(entry.get("status"))
    return UNCONFIRMED_STATUS


def get_effective_field_value(reviewed_map: dict | None, field_key: str, raw_value: Any) -> Any:
    """Edited reviewer value when an edit was saved, else the prepared value."""
    if isinstance(reviewed_map, dict):
        entry = reviewed_map.get(field_key)
        if isinstance(entry, dict):
            status = normalize_review_status(entry.get("status"))
            edited = entry.get("edited_value")
            if status == EDITED_STATUS and edited is not None:
                return edited
    return raw_value


def get_effective_extraction_fields(record: dict, reviewed_map: dict | None) -> dict:
    """Prepared extracted fields with reviewer edits overlaid (read-only copy)."""
    record = record if isinstance(record, dict) else {}
    extracted = record.get("extracted_fields")
    if not isinstance(extracted, dict):
        return {}
    return {
        field_key: get_effective_field_value(reviewed_map, field_key, raw_value)
        for field_key, raw_value in extracted.items()
    }


def is_record_approved(record: dict, reviewed_map: dict | None) -> bool:
    """A record is approved only if every field is Accepted or Edited."""
    record = record if isinstance(record, dict) else {}
    extracted = record.get("extracted_fields")
    if not isinstance(extracted, dict) or not extracted:
        return False
    for field_key in extracted:
        if get_field_review_status(reviewed_map, field_key) not in APPROVED_REVIEW_STATUSES:
            return False
    return True


def get_extraction_review_progress(
    analysis_response: dict | None,
    reviewed_all: dict | None,
) -> dict:
    """Derive review progress and the hard gate from session overlay each rerun."""
    reviewable = get_reviewable_evidence_records(analysis_response)
    reviewed_all = reviewed_all if isinstance(reviewed_all, dict) else {}

    total_fields = 0
    confirmed_fields = 0
    group_counts = {BUCKET_PASS: 0, BUCKET_NEEDS_REVIEW: 0, BUCKET_FAIL: 0}
    approved_records: list[str] = []

    for record in reviewable:
        evidence_id = safe_text(record.get("evidence_id"))
        reviewed_map = reviewed_all.get(evidence_id) if isinstance(reviewed_all.get(evidence_id), dict) else {}
        extracted = record.get("extracted_fields") or {}

        for field_key in extracted:
            total_fields += 1
            if get_field_review_status(reviewed_map, field_key) in FINAL_REVIEW_STATUSES:
                confirmed_fields += 1

        bucket = record_confidence_bucket(record)
        group_counts[bucket] = group_counts.get(bucket, 0) + 1

        if is_record_approved(record, reviewed_map):
            approved_records.append(evidence_id)

    is_complete = total_fields > 0 and confirmed_fields == total_fields

    return {
        "reviewable_record_count": len(reviewable),
        "total_fields": total_fields,
        "confirmed_fields": confirmed_fields,
        "unconfirmed_fields": max(total_fields - confirmed_fields, 0),
        "group_counts": group_counts,
        "approved_record_ids": approved_records,
        "approved_record_count": len(approved_records),
        "is_complete": is_complete,
    }


def passing_field_keys(record: dict) -> list[str]:
    """Field keys whose confidence bucket is pass (used for bulk confirmation)."""
    record = record if isinstance(record, dict) else {}
    extracted = record.get("extracted_fields")
    if not isinstance(extracted, dict):
        return []
    return [key for key in extracted if field_confidence_bucket(record, key) == BUCKET_PASS]


def resolve_field_source_reference(record: dict, asset: dict | None, field_key: str) -> dict:
    """Best-effort source location (page + snippet) for a field highlight."""
    record = record if isinstance(record, dict) else {}
    asset = asset if isinstance(asset, dict) else {}

    page_number: Any = None
    snippet: Any = None

    refs = record.get("source_references")
    if isinstance(refs, list) and refs and isinstance(refs[0], dict):
        page_number = refs[0].get("page_number")
        snippet = refs[0].get("source_snippet")

    if page_number is None:
        page_number = asset.get("page_number")
    if not snippet:
        snippet = asset.get("source_snippet")

    return {
        "field_key": field_key,
        "page_number": page_number,
        "source_snippet": snippet,
        "section_identifier": asset.get("section_identifier"),
    }
