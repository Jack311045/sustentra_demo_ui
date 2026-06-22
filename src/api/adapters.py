"""
Adapters convert raw backend or mock API responses into internal UI-facing models.
Streamlit pages should depend on adapted data, not raw API payloads.
"""

from __future__ import annotations

from copy import deepcopy


CONSOLIDATION_APPROACH_OPTIONS = (
    "Operational control",
    "Financial control",
    "Equity share",
)

ASSURANCE_LEVEL_OPTIONS = (
    "Limited assurance",
    "Reasonable assurance",
)

_MEANINGFUL_FIELDS = (
    ("company_and_facility_profile", "company_name"),
    ("company_and_facility_profile", "facility_name"),
    ("company_and_facility_profile", "facility_address"),
    ("company_and_facility_profile", "company_facility_identifier"),
    ("company_and_facility_profile", "industry"),
    ("company_and_facility_profile", "facility_type"),
    ("company_and_facility_profile", "reporting_period"),
    ("engagement_details", "engagement_name"),
)


def _is_meaningful_text(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if text.lower().startswith("needs confirmation"):
        return False
    return True


def has_meaningful_audit_setup(setup: object) -> bool:
    if not isinstance(setup, dict):
        return False

    for section_key, field_key in _MEANINGFUL_FIELDS:
        section = setup.get(section_key)
        if not isinstance(section, dict):
            continue
        if _is_meaningful_text(section.get(field_key)):
            return True
    return False


def _ensure_section(container: dict, key: str) -> dict:
    value = container.get(key)
    if not isinstance(value, dict):
        value = {}
    container[key] = value
    return value


def _append_warning(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def normalize_audit_setup(setup: dict | None) -> dict:
    normalized = deepcopy(setup) if isinstance(setup, dict) else {}

    raw_warnings = normalized.get("_normalization_warnings")
    warnings: list[str] = []
    if isinstance(raw_warnings, list):
        for item in raw_warnings:
            if isinstance(item, str) and item.strip():
                warnings.append(item.strip())

    _ensure_section(normalized, "company_and_facility_profile")
    reporting_boundary = _ensure_section(normalized, "reporting_boundary")
    regulation = _ensure_section(normalized, "regulation_and_verification")
    materiality = _ensure_section(normalized, "materiality_and_thresholds")
    _ensure_section(normalized, "engagement_details")
    _ensure_section(normalized, "methodology_defaults")

    raw_consolidation = reporting_boundary.get("consolidation_approach")
    has_valid_consolidation = (
        isinstance(raw_consolidation, str)
        and raw_consolidation in CONSOLIDATION_APPROACH_OPTIONS
    )
    legacy_operational = bool(reporting_boundary.get("operational_control"))
    legacy_ownership = bool(reporting_boundary.get("ownership_control"))

    if has_valid_consolidation:
        consolidation = raw_consolidation
    elif legacy_operational:
        consolidation = "Operational control"
    elif legacy_ownership:
        consolidation = "Operational control"
        _append_warning(
            warnings,
            "Legacy ownership_control without operational_control mapped to Operational control as migration fallback.",
        )
    else:
        consolidation = "Operational control"
        _append_warning(
            warnings,
            "Missing consolidation controls defaulted to Operational control.",
        )

    reporting_boundary["consolidation_approach"] = consolidation
    reporting_boundary.pop("ownership_control", None)
    reporting_boundary.pop("operational_control", None)

    raw_primary = regulation.get("primary_regulation")
    primary_regulation = str(raw_primary).strip() if isinstance(raw_primary, str) else ""
    if not primary_regulation:
        primary_regulation = "NY Part 253"
    regulation["primary_regulation"] = primary_regulation

    frameworks = regulation.get("additional_frameworks")
    cleaned_frameworks: list[str] = []
    if isinstance(frameworks, list):
        for item in frameworks:
            if not isinstance(item, str):
                continue
            framework = item.strip()
            if not framework:
                continue
            if framework == primary_regulation:
                continue
            if framework not in cleaned_frameworks:
                cleaned_frameworks.append(framework)
    regulation["additional_frameworks"] = cleaned_frameworks

    raw_assurance_level = regulation.get("assurance_level")
    has_valid_assurance_level = (
        isinstance(raw_assurance_level, str)
        and raw_assurance_level in ASSURANCE_LEVEL_OPTIONS
    )
    if has_valid_assurance_level:
        assurance_level = raw_assurance_level
    else:
        assurance_level = "Limited assurance"
        if isinstance(raw_assurance_level, str) and raw_assurance_level.strip():
            _append_warning(
                warnings,
                "Unsupported assurance_level detected and replaced with Limited assurance.",
            )
    regulation["assurance_level"] = assurance_level

    if not isinstance(regulation.get("verification_standard"), str):
        regulation["verification_standard"] = "ISSA 5000"

    raw_absolute = materiality.get("materiality_absolute")
    if isinstance(raw_absolute, str) and raw_absolute.strip():
        materiality_absolute = raw_absolute.strip()
    else:
        materiality_absolute = "750 tCO2e"
    materiality["materiality_absolute"] = materiality_absolute

    if warnings:
        normalized["_normalization_warnings"] = warnings
    else:
        normalized.pop("_normalization_warnings", None)

    return normalized


def resolve_audit_setup(
    *,
    session_setup: object,
    response_setup: object,
    prepared_setup: object,
    session_is_user_saved: bool,
) -> dict:
    selected: object | None = None

    if session_is_user_saved and has_meaningful_audit_setup(session_setup):
        selected = session_setup
    elif has_meaningful_audit_setup(response_setup):
        selected = response_setup
    elif has_meaningful_audit_setup(session_setup):
        selected = session_setup
    elif has_meaningful_audit_setup(prepared_setup):
        selected = prepared_setup
    else:
        return {}

    normalized = normalize_audit_setup(deepcopy(selected) if isinstance(selected, dict) else {})
    return normalized if has_meaningful_audit_setup(normalized) else {}


def adapt_analysis_response(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    adapted = dict(raw)
    raw_setup = adapted.get("audit_setup")
    if has_meaningful_audit_setup(raw_setup):
        adapted["audit_setup"] = normalize_audit_setup(raw_setup)
    else:
        adapted["audit_setup"] = {}
    adapted.setdefault("uploaded_demo_files", {})
    adapted.setdefault("summary", {})
    adapted.setdefault("evidence_results", [])
    adapted.setdefault("validation_results", [])
    adapted.setdefault("calculation_results", [])
    adapted.setdefault("reconciliation_summary", {})
    adapted.setdefault("workbook_results", [])
    adapted.setdefault("gap_tickets", [])
    adapted.setdefault("chat_suggestions", [])
    adapted.setdefault("errors", [])
    adapted.setdefault("warnings", [])
    return adapted
