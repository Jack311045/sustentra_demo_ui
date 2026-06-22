from __future__ import annotations

import streamlit as st

from src.api.mock_client import MockApiClient
from src.ui.state import get_analysis_response, get_audit_setup, init_session_state, set_audit_setup
from src.ui.workflow import render_prepared_demo_disclosure, render_workflow_progress


def _default_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "Needs confirmation"


init_session_state()
st.title("Audit Setup")
st.caption("Configure the engagement profile before evidence intake and review.")
render_workflow_progress(current_step=1)
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
current_setup = get_audit_setup()

if not current_setup:
    if analysis_response and isinstance(analysis_response.get("audit_setup"), dict):
        set_audit_setup(analysis_response.get("audit_setup") or {})
    else:
        set_audit_setup(MockApiClient().load_audit_setup())
    current_setup = get_audit_setup()

company_profile = current_setup.get("company_and_facility_profile", {})
reporting_boundary = current_setup.get("reporting_boundary", {})
regulation_standards = current_setup.get("regulation_and_verification", {})
materiality = current_setup.get("materiality_and_thresholds", {})
engagement = current_setup.get("engagement_details", {})
methodology = current_setup.get("methodology_defaults", {})

st.subheader("Company and facility profile")
col1, col2 = st.columns(2)
with col1:
    company_name = st.text_input("Company name", value=_default_text(company_profile.get("company_name")))
    facility_name = st.text_input("Facility name", value=_default_text(company_profile.get("facility_name")))
    facility_address = st.text_area("Address", value=_default_text(company_profile.get("facility_address")), height=90)
    company_facility_identifier = st.text_input(
        "Company/facility identifier",
        value=_default_text(company_profile.get("company_facility_identifier")),
    )
with col2:
    duns_number = st.text_input("DUNS", value=_default_text(company_profile.get("duns_number")))
    industry = st.text_input("Industry", value=_default_text(company_profile.get("industry")))
    facility_type = st.text_input("Facility type", value=_default_text(company_profile.get("facility_type")))
    reporting_period = st.text_input("Reporting period", value=_default_text(company_profile.get("reporting_period")))

st.subheader("Reporting boundary")
boundary_col1, boundary_col2 = st.columns(2)
with boundary_col1:
    scope_1 = st.checkbox("Scope 1", value=bool(reporting_boundary.get("scope_1", True)))
    scope_2 = st.checkbox("Scope 2", value=bool(reporting_boundary.get("scope_2", False)))
    scope_3 = st.checkbox("Scope 3", value=bool(reporting_boundary.get("scope_3", False)))
with boundary_col2:
    boundary_type = st.selectbox(
        "Boundary type",
        options=["Facility", "Portfolio"],
        index=0 if str(reporting_boundary.get("boundary_type", "Facility")) == "Facility" else 1,
    )
    ownership_control = st.checkbox("Ownership control", value=bool(reporting_boundary.get("ownership_control", True)))
    operational_control = st.checkbox(
        "Operational control",
        value=bool(reporting_boundary.get("operational_control", True)),
    )

st.subheader("Regulation and verification standards")
framework_options = ["NY Part 253", "EPA Part 98", "ISO 14064-3", "ISSA 5000"]
selected_primary = st.selectbox(
    "Primary regulation",
    options=framework_options,
    index=framework_options.index(regulation_standards.get("primary_regulation", "NY Part 253"))
    if regulation_standards.get("primary_regulation", "NY Part 253") in framework_options
    else 0,
)
selected_frameworks = st.multiselect(
    "Additional frameworks",
    options=framework_options,
    default=[
        item
        for item in regulation_standards.get("additional_frameworks", [])
        if item in framework_options
    ],
)
verification_standard = st.text_input(
    "Verification/assurance standard",
    value=_default_text(regulation_standards.get("verification_standard")),
)
source_categories = st.text_area(
    "Source categories",
    value=_default_text(regulation_standards.get("source_categories")),
    help="Use concise categories that are already supported by the prepared demo.",
)

st.subheader("Materiality and thresholds")
mat_col1, mat_col2 = st.columns(2)
with mat_col1:
    reporting_threshold = st.text_input(
        "Reporting threshold",
        value=_default_text(materiality.get("reporting_threshold")),
    )
    material_misstatement = st.text_input(
        "Material misstatement percentage",
        value=_default_text(materiality.get("material_misstatement_percentage")),
    )
with mat_col2:
    key_source_categories = st.text_area(
        "Key source categories",
        value=_default_text(materiality.get("key_source_categories")),
        height=90,
    )
    missing_data_threshold = st.text_input(
        "Missing-data threshold",
        value=_default_text(materiality.get("missing_data_threshold")),
    )

st.subheader("Engagement details")
eng_col1, eng_col2 = st.columns(2)
with eng_col1:
    engagement_name = st.text_input("Engagement name", value=_default_text(engagement.get("engagement_name")))
    engagement_reporting_period = st.text_input(
        "Engagement reporting period",
        value=_default_text(engagement.get("reporting_period")),
    )
    auditor_reviewer = st.text_input("Auditor/reviewer", value=_default_text(engagement.get("auditor_reviewer")))
with eng_col2:
    scope_description = st.text_area(
        "Scope description",
        value=_default_text(engagement.get("scope_description")),
        height=90,
    )
    verification_objective = st.text_area(
        "Verification objective",
        value=_default_text(engagement.get("verification_objective")),
        height=90,
    )

st.subheader("Methodology defaults")
method_col1, method_col2 = st.columns(2)
with method_col1:
    method_by_fuel = st.text_area(
        "Method/tier by fuel type",
        value=_default_text(methodology.get("method_tier_by_fuel_type")),
        height=110,
    )
    emission_factor_source = st.text_input(
        "Emission-factor source",
        value=_default_text(methodology.get("emission_factor_source")),
    )
    gwp_basis = st.text_input("GWP basis", value=_default_text(methodology.get("gwp_basis")))
with method_col2:
    unit_normalization_defaults = st.text_area(
        "Unit normalization defaults",
        value=_default_text(methodology.get("unit_normalization_defaults")),
        height=110,
    )
    biogenic_fossil_treatment = st.text_area(
        "Biogenic/fossil treatment",
        value=_default_text(methodology.get("biogenic_fossil_treatment")),
        height=110,
    )

updated_setup = {
    "company_and_facility_profile": {
        "company_name": company_name,
        "facility_name": facility_name,
        "facility_address": facility_address,
        "company_facility_identifier": company_facility_identifier,
        "duns_number": duns_number,
        "industry": industry,
        "facility_type": facility_type,
        "reporting_period": reporting_period,
    },
    "reporting_boundary": {
        "scope_1": scope_1,
        "scope_2": scope_2,
        "scope_3": scope_3,
        "boundary_type": boundary_type,
        "ownership_control": ownership_control,
        "operational_control": operational_control,
    },
    "regulation_and_verification": {
        "primary_regulation": selected_primary,
        "additional_frameworks": selected_frameworks,
        "verification_standard": verification_standard,
        "source_categories": source_categories,
    },
    "materiality_and_thresholds": {
        "reporting_threshold": reporting_threshold,
        "material_misstatement_percentage": material_misstatement,
        "key_source_categories": key_source_categories,
        "missing_data_threshold": missing_data_threshold,
    },
    "engagement_details": {
        "engagement_name": engagement_name,
        "reporting_period": engagement_reporting_period,
        "auditor_reviewer": auditor_reviewer,
        "scope_description": scope_description,
        "verification_objective": verification_objective,
    },
    "methodology_defaults": {
        "method_tier_by_fuel_type": method_by_fuel,
        "emission_factor_source": emission_factor_source,
        "gwp_basis": gwp_basis,
        "unit_normalization_defaults": unit_normalization_defaults,
        "biogenic_fossil_treatment": biogenic_fossil_treatment,
    },
}

set_audit_setup(updated_setup)
if st.button("Save audit setup", type="primary"):
    st.success("Audit setup saved in session state for this demo run.")

with st.expander("Advanced setup JSON", expanded=False):
    st.json(updated_setup)
