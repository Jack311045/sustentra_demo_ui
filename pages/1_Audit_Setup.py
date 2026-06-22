from __future__ import annotations

from copy import deepcopy

import streamlit as st

from src.api.adapters import has_meaningful_audit_setup, resolve_audit_setup
from src.api.mock_client import MockApiClient
from src.ui.state import (
    get_analysis_response,
    get_audit_setup,
    get_audit_setup_revision,
    init_session_state,
    is_audit_setup_user_saved,
    set_analysis_response,
    set_audit_setup,
)
from src.ui.workflow import build_engagement_expectation_summary, render_prepared_demo_disclosure


DEMO_OVERRIDES = {
    "duns_number": "00-123-4567",
    "reporting_threshold": "1,000 tCO2e (organizational reporting threshold)",
    "auditor_reviewer": "Sustentra prepared-demo reviewer",
}

BOUNDARY_OPTIONS = ["Facility", "Portfolio"]
CONSOLIDATION_OPTIONS = ["Operational control", "Financial control", "Equity share"]
CRITERIA_OPTIONS = ["NY Part 253", "EPA Part 98", "GHG Protocol"]
ASSURANCE_STANDARD_OPTIONS = ["ISSA 5000", "ISO 14064-3"]
ASSURANCE_LEVEL_OPTIONS = ["Limited assurance", "Reasonable assurance"]


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text or text.lower().startswith("needs confirmation"):
        return fallback
    return text


def _sanitize_choice(value: object, options: list[str], fallback: str) -> str:
    candidate = str(value or "").strip()
    if candidate in options:
        return candidate
    return fallback


def _sanitize_multi(
    values: object,
    options: list[str],
    *,
    excluded: set[str] | None = None,
) -> list[str]:
    excluded = excluded or set()
    output: list[str] = []
    if not isinstance(values, list):
        return output

    for item in values:
        candidate = str(item or "").strip()
        if not candidate:
            continue
        if candidate in excluded:
            continue
        if candidate not in options:
            continue
        if candidate in output:
            continue
        output.append(candidate)
    return output


def _hydrate_widgets_from_setup(setup: dict, revision: int) -> None:
    if st.session_state.get("audit_setup_widgets_revision") == revision:
        return

    company = (
        setup.get("company_and_facility_profile")
        if isinstance(setup.get("company_and_facility_profile"), dict)
        else {}
    )
    boundary = (
        setup.get("reporting_boundary")
        if isinstance(setup.get("reporting_boundary"), dict)
        else {}
    )
    regulation = (
        setup.get("regulation_and_verification")
        if isinstance(setup.get("regulation_and_verification"), dict)
        else {}
    )
    materiality = (
        setup.get("materiality_and_thresholds")
        if isinstance(setup.get("materiality_and_thresholds"), dict)
        else {}
    )
    engagement = (
        setup.get("engagement_details")
        if isinstance(setup.get("engagement_details"), dict)
        else {}
    )
    methodology = (
        setup.get("methodology_defaults")
        if isinstance(setup.get("methodology_defaults"), dict)
        else {}
    )

    primary = _sanitize_choice(regulation.get("primary_regulation"), CRITERIA_OPTIONS, "NY Part 253")
    additional = _sanitize_multi(
        regulation.get("additional_frameworks"),
        CRITERIA_OPTIONS,
        excluded={primary},
    )

    st.session_state["audit_company_name"] = _text(company.get("company_name"))
    st.session_state["audit_facility_name"] = _text(company.get("facility_name"))
    st.session_state["audit_facility_address"] = _text(company.get("facility_address"))
    st.session_state["audit_industry"] = _text(company.get("industry"))
    st.session_state["audit_facility_type"] = _text(company.get("facility_type"))
    st.session_state["audit_reporting_period"] = _text(company.get("reporting_period"))
    st.session_state["audit_company_facility_identifier"] = _text(company.get("company_facility_identifier"))
    st.session_state["audit_duns_number"] = _text(company.get("duns_number"), DEMO_OVERRIDES["duns_number"])

    st.session_state["audit_scope_1"] = bool(boundary.get("scope_1", True))
    st.session_state["audit_scope_2"] = bool(boundary.get("scope_2", False))
    st.session_state["audit_scope_3"] = bool(boundary.get("scope_3", False))
    st.session_state["audit_boundary_type"] = _sanitize_choice(
        boundary.get("boundary_type"),
        BOUNDARY_OPTIONS,
        "Facility",
    )
    st.session_state["audit_consolidation_approach"] = _sanitize_choice(
        boundary.get("consolidation_approach"),
        CONSOLIDATION_OPTIONS,
        "Operational control",
    )

    st.session_state["audit_primary_criteria"] = primary
    st.session_state["audit_additional_criteria"] = additional
    st.session_state["audit_assurance_standard"] = _sanitize_choice(
        regulation.get("verification_standard"),
        ASSURANCE_STANDARD_OPTIONS,
        "ISSA 5000",
    )
    st.session_state["audit_assurance_level"] = _sanitize_choice(
        regulation.get("assurance_level"),
        ASSURANCE_LEVEL_OPTIONS,
        "Limited assurance",
    )
    st.session_state["audit_source_categories"] = _text(regulation.get("source_categories"))

    st.session_state["audit_reporting_threshold"] = _text(
        materiality.get("reporting_threshold"),
        DEMO_OVERRIDES["reporting_threshold"],
    )
    st.session_state["audit_materiality_percentage"] = _text(
        materiality.get("material_misstatement_percentage"),
        "5%",
    )
    st.session_state["audit_materiality_absolute"] = _text(
        materiality.get("materiality_absolute"),
        "750 tCO2e",
    )
    st.session_state["audit_key_source_categories"] = _text(materiality.get("key_source_categories"))
    st.session_state["audit_missing_data_threshold"] = _text(materiality.get("missing_data_threshold"))

    st.session_state["audit_engagement_name"] = _text(engagement.get("engagement_name"))
    st.session_state["audit_engagement_reporting_period"] = _text(engagement.get("reporting_period"))
    st.session_state["audit_auditor_reviewer"] = _text(
        engagement.get("auditor_reviewer"),
        DEMO_OVERRIDES["auditor_reviewer"],
    )
    st.session_state["audit_scope_description"] = _text(engagement.get("scope_description"))
    st.session_state["audit_verification_objective"] = _text(engagement.get("verification_objective"))

    st.session_state["audit_method_by_fuel"] = _text(methodology.get("method_tier_by_fuel_type"))
    st.session_state["audit_emission_factor_source"] = _text(methodology.get("emission_factor_source"))
    st.session_state["audit_gwp_basis"] = _text(methodology.get("gwp_basis"))
    st.session_state["audit_unit_normalization"] = _text(methodology.get("unit_normalization_defaults"))
    st.session_state["audit_biogenic_treatment"] = _text(methodology.get("biogenic_fossil_treatment"))

    st.session_state["audit_setup_widgets_revision"] = revision


init_session_state()
st.title("Audit Setup")
st.caption(
    "Confirm the engagement profile. These choices drive evidence intake, validation, and gap analysis downstream."
)
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
response_setup = analysis_response.get("audit_setup") if isinstance(analysis_response, dict) else None
prepared_setup = MockApiClient().load_audit_setup()

if not has_meaningful_audit_setup(prepared_setup):
    st.error(
        "Prepared Audit Setup could not be loaded. "
        "Check data/demo/mock_outputs/mock_audit_setup.json."
    )
    st.stop()

current_setup = resolve_audit_setup(
    session_setup=get_audit_setup(),
    response_setup=response_setup,
    prepared_setup=prepared_setup,
    session_is_user_saved=is_audit_setup_user_saved(),
)

set_audit_setup(
    current_setup,
    user_saved=is_audit_setup_user_saved(),
    increment_revision=True,
)

current_setup = get_audit_setup()

if not has_meaningful_audit_setup(current_setup):
    st.error(
        "Prepared Audit Setup could not be loaded. "
        "Check data/demo/mock_outputs/mock_audit_setup.json."
    )
    st.stop()

_hydrate_widgets_from_setup(current_setup, get_audit_setup_revision())

normalization_warnings = current_setup.get("_normalization_warnings")
if isinstance(normalization_warnings, list):
    for warning in normalization_warnings:
        if isinstance(warning, str) and warning.strip():
            st.caption(f"Developer warning: {warning}")

st.subheader("Company and facility profile")
col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input("Company name", key="audit_company_name")
    facility_name = st.text_input("Facility name", key="audit_facility_name")
    facility_address = st.text_area("Address", key="audit_facility_address", height=90)
    industry = st.text_input("Industry", key="audit_industry")
    facility_type = st.text_input("Facility type", key="audit_facility_type")
    reporting_period = st.text_input("Reporting period", key="audit_reporting_period")

id_col1, id_col2 = st.columns(2)
with id_col1:
    company_facility_identifier = st.text_input(
        "Company/facility identifier",
        key="audit_company_facility_identifier",
    )
with id_col2:
    duns_number = st.text_input("DUNS", key="audit_duns_number")

st.subheader("Reporting boundary")
boundary_col1, boundary_col2 = st.columns(2)
with boundary_col1:
    st.markdown("**Scopes in engagement**")
    scope_1 = st.checkbox("Scope 1", key="audit_scope_1")
    scope_2 = st.checkbox("Scope 2", key="audit_scope_2")
    scope_3 = st.checkbox("Scope 3", key="audit_scope_3")
with boundary_col2:
    boundary_type = st.selectbox(
        "Boundary type",
        options=BOUNDARY_OPTIONS,
        key="audit_boundary_type",
    )
    consolidation_approach = st.selectbox(
        "Consolidation approach",
        options=CONSOLIDATION_OPTIONS,
        key="audit_consolidation_approach",
        help="GHG Protocol requires a single consolidation approach per inventory.",
    )

st.subheader("Reporting criteria and assurance standard")
criteria_col1, criteria_col2 = st.columns(2)
with criteria_col1:
    st.markdown("**Reporting criteria**")
    selected_primary = st.selectbox(
        "Primary criteria",
        options=CRITERIA_OPTIONS,
        key="audit_primary_criteria",
    )
    selected_frameworks = st.multiselect(
        "Additional criteria",
        options=CRITERIA_OPTIONS,
        key="audit_additional_criteria",
    )

with criteria_col2:
    st.markdown("**Assurance standard**")
    verification_standard = st.selectbox(
        "Assurance standard",
        options=ASSURANCE_STANDARD_OPTIONS,
        key="audit_assurance_standard",
    )
    assurance_level = st.selectbox(
        "Assurance level",
        options=ASSURANCE_LEVEL_OPTIONS,
        key="audit_assurance_level",
    )

if selected_primary in selected_frameworks:
    selected_frameworks = [item for item in selected_frameworks if item != selected_primary]
    st.session_state["audit_additional_criteria"] = selected_frameworks

source_categories = st.text_area(
    "Source categories",
    key="audit_source_categories",
    help="Use concise categories that are already supported by the prepared demo.",
)

st.subheader("Materiality and thresholds")
mat_col1, mat_col2 = st.columns(2)
with mat_col1:
    reporting_threshold = st.text_input("Reporting threshold", key="audit_reporting_threshold")
    material_misstatement = st.text_input(
        "Material misstatement percentage",
        key="audit_materiality_percentage",
    )
    materiality_absolute = st.text_input(
        "Material misstatement (absolute)",
        key="audit_materiality_absolute",
    )
with mat_col2:
    key_source_categories = st.text_area(
        "Key source categories",
        key="audit_key_source_categories",
        height=90,
    )
    missing_data_threshold = st.text_input(
        "Missing-data threshold",
        key="audit_missing_data_threshold",
    )

st.subheader("Engagement details")
eng_col1, eng_col2 = st.columns(2)
with eng_col1:
    engagement_name = st.text_input("Engagement name", key="audit_engagement_name")
    engagement_reporting_period = st.text_input(
        "Engagement reporting period",
        key="audit_engagement_reporting_period",
    )
    auditor_reviewer = st.text_input("Auditor/reviewer", key="audit_auditor_reviewer")
with eng_col2:
    scope_description = st.text_area(
        "Scope description",
        key="audit_scope_description",
        height=90,
    )
    verification_objective = st.text_area(
        "Verification objective",
        key="audit_verification_objective",
        height=90,
    )

st.subheader("Methodology defaults")
method_col1, method_col2 = st.columns(2)
with method_col1:
    method_by_fuel = st.text_area(
        "Method/tier by fuel type",
        key="audit_method_by_fuel",
        height=110,
    )
    emission_factor_source = st.text_input(
        "Emission-factor source",
        key="audit_emission_factor_source",
    )
    gwp_basis = st.text_input("GWP basis", key="audit_gwp_basis")
with method_col2:
    unit_normalization_defaults = st.text_area(
        "Unit normalization defaults",
        key="audit_unit_normalization",
        height=110,
    )
    biogenic_fossil_treatment = st.text_area(
        "Biogenic/fossil treatment",
        key="audit_biogenic_treatment",
        height=110,
    )

selected_scopes = [
    name
    for name, enabled in (("Scope 1", scope_1), ("Scope 2", scope_2), ("Scope 3", scope_3))
    if enabled
]
with st.container(border=True):
    st.markdown("**What this engagement expects**")
    st.caption(
        build_engagement_expectation_summary(
            selected_scopes=selected_scopes,
            reporting_period=reporting_period,
            materiality_absolute=materiality_absolute,
        )
    )

cleaned_frameworks = _sanitize_multi(
    selected_frameworks,
    CRITERIA_OPTIONS,
    excluded={selected_primary},
)

updated_setup = deepcopy(current_setup)
updated_setup.pop("_normalization_warnings", None)

existing_company = (
    updated_setup.get("company_and_facility_profile")
    if isinstance(updated_setup.get("company_and_facility_profile"), dict)
    else {}
)
existing_company.update(
    {
        "company_name": company_name,
        "facility_name": facility_name,
        "facility_address": facility_address,
        "company_facility_identifier": company_facility_identifier,
        "duns_number": duns_number,
        "industry": industry,
        "facility_type": facility_type,
        "reporting_period": reporting_period,
    }
)
updated_setup["company_and_facility_profile"] = existing_company

existing_boundary = (
    updated_setup.get("reporting_boundary")
    if isinstance(updated_setup.get("reporting_boundary"), dict)
    else {}
)
existing_boundary.update(
    {
        "scope_1": scope_1,
        "scope_2": scope_2,
        "scope_3": scope_3,
        "boundary_type": boundary_type,
        "consolidation_approach": consolidation_approach,
    }
)
updated_setup["reporting_boundary"] = existing_boundary

existing_regulation = (
    updated_setup.get("regulation_and_verification")
    if isinstance(updated_setup.get("regulation_and_verification"), dict)
    else {}
)
existing_regulation.update(
    {
        "primary_regulation": selected_primary,
        "additional_frameworks": cleaned_frameworks,
        "verification_standard": verification_standard,
        "assurance_level": assurance_level,
        "source_categories": source_categories,
    }
)
updated_setup["regulation_and_verification"] = existing_regulation

existing_materiality = (
    updated_setup.get("materiality_and_thresholds")
    if isinstance(updated_setup.get("materiality_and_thresholds"), dict)
    else {}
)
existing_materiality.update(
    {
        "reporting_threshold": reporting_threshold,
        "material_misstatement_percentage": material_misstatement,
        "materiality_absolute": materiality_absolute,
        "key_source_categories": key_source_categories,
        "missing_data_threshold": missing_data_threshold,
    }
)
updated_setup["materiality_and_thresholds"] = existing_materiality

existing_engagement = (
    updated_setup.get("engagement_details")
    if isinstance(updated_setup.get("engagement_details"), dict)
    else {}
)
existing_engagement.update(
    {
        "engagement_name": engagement_name,
        "reporting_period": engagement_reporting_period,
        "auditor_reviewer": auditor_reviewer,
        "scope_description": scope_description,
        "verification_objective": verification_objective,
    }
)
updated_setup["engagement_details"] = existing_engagement

existing_methodology = (
    updated_setup.get("methodology_defaults")
    if isinstance(updated_setup.get("methodology_defaults"), dict)
    else {}
)
existing_methodology.update(
    {
        "method_tier_by_fuel_type": method_by_fuel,
        "emission_factor_source": emission_factor_source,
        "gwp_basis": gwp_basis,
        "unit_normalization_defaults": unit_normalization_defaults,
        "biogenic_fossil_treatment": biogenic_fossil_treatment,
    }
)
updated_setup["methodology_defaults"] = existing_methodology

if st.button("Save audit setup", type="primary"):
    set_audit_setup(
        updated_setup,
        user_saved=True,
        increment_revision=True,
    )

    latest_response = get_analysis_response()
    if isinstance(latest_response, dict):
        updated_response = deepcopy(latest_response)
        updated_response["audit_setup"] = deepcopy(updated_setup)
        set_analysis_response(updated_response)

    st.success("Audit setup saved in session state for this demo run.")

with st.expander("Advanced setup JSON", expanded=False):
    st.json(updated_setup)
