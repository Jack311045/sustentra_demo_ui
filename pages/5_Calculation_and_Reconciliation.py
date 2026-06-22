from __future__ import annotations

import streamlit as st

from src.ui.state import (
    get_analysis_response,
    get_selected_calculation_id,
    get_selected_workbook_location,
    init_session_state,
    set_selected_calculation_id,
)
from src.ui.tables import render_calculation_table
from src.ui.workflow import render_prepared_demo_disclosure, render_workflow_progress


def _summary_number(value) -> str:
    if value is None:
        return "Needs confirmation"
    return str(value)


init_session_state()
st.title("Calculation & Reconciliation")
st.caption("Trace evidence-to-calculation flow and compare recalculated totals with workbook-reported values.")
render_workflow_progress(current_step=5)
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

calculation_results = [
    item for item in (analysis_response.get("calculation_results") or []) if isinstance(item, dict)
]
reconciliation_summary = (
    analysis_response.get("reconciliation_summary")
    if isinstance(analysis_response.get("reconciliation_summary"), dict)
    else {}
)

if not calculation_results:
    st.info("No calculation results are available in this prepared dataset.")
    st.stop()

summary_cols = st.columns(6)
summary_cols[0].metric("Reported Scope 1", _summary_number(reconciliation_summary.get("reported_scope_1_mtco2e")))
summary_cols[1].metric("Recalculated Scope 1", _summary_number(reconciliation_summary.get("recalculated_scope_1_mtco2e")))
summary_cols[2].metric("Absolute difference", _summary_number(reconciliation_summary.get("absolute_difference_mtco2e")))
summary_cols[3].metric("Variance %", _summary_number(reconciliation_summary.get("variance_percent")))
summary_cols[4].metric("Materiality threshold", _summary_number(reconciliation_summary.get("materiality_threshold_percent")))
summary_cols[5].metric("Reconciliation status", _summary_number(reconciliation_summary.get("reconciliation_status")))

st.subheader("Calculation path")
st.caption(
    "Source evidence -> extracted activity -> normalized activity -> selected factor -> gas-level calculation "
    "-> GWP conversion -> recalculated result -> workbook result -> variance/materiality"
)

render_calculation_table(calculation_results)

calculation_ids = [str(item.get("calculation_id")) for item in calculation_results if item.get("calculation_id")]
if not calculation_ids:
    st.info("Calculation IDs are missing from the prepared dataset.")
    st.stop()

selected_calculation_id = get_selected_calculation_id()
if selected_calculation_id not in calculation_ids:
    selected_calculation_id = calculation_ids[0]

selected_workbook_location = get_selected_workbook_location()
if isinstance(selected_workbook_location, dict):
    desired_sheet = str(selected_workbook_location.get("sheet_name") or "").strip().lower()
    desired_cell = str(selected_workbook_location.get("cell_or_range") or "").strip().lower()
    for item in calculation_results:
        if not isinstance(item, dict):
            continue
        loc = item.get("workbook_location") if isinstance(item.get("workbook_location"), dict) else {}
        sheet = str(loc.get("sheet_name") or "").strip().lower()
        cell = str(loc.get("cell_or_range") or "").strip().lower()
        if desired_sheet and desired_cell and sheet == desired_sheet and cell == desired_cell:
            selected_calculation_id = str(item.get("calculation_id"))
            break

selected_calculation_id = st.selectbox(
    "Select calculation record",
    options=calculation_ids,
    index=calculation_ids.index(selected_calculation_id),
)
set_selected_calculation_id(selected_calculation_id)

selected_record = next(
    (item for item in calculation_results if str(item.get("calculation_id")) == selected_calculation_id),
    None,
)
if not selected_record:
    st.info("Selected calculation record could not be found.")
    st.stop()

status = selected_record.get("calculation_status") or selected_record.get("status")
if status == "not_computed_in_current_demo":
    st.warning(selected_record.get("reason") or "Calculation not computed in current demo.")
else:
    st.success(f"Calculation status: {status or 'computed'}")

st.subheader(str(selected_record.get("source_or_fuel") or selected_calculation_id))

left_col, right_col = st.columns(2)
with left_col:
    st.write(f"**Linked evidence IDs:** {selected_record.get('linked_evidence_ids') or []}")
    workbook_location = selected_record.get("workbook_location") if isinstance(selected_record.get("workbook_location"), dict) else {}
    st.write(f"**Workbook sheet/cell:** {workbook_location.get('sheet_name')}!{workbook_location.get('cell_or_range')}")
    st.write(f"**Activity value:** {selected_record.get('activity_quantity')}")
    st.write(f"**Normalization:** {selected_record.get('normalization_note') or 'Needs confirmation'}")
    st.write(f"**Formula/check IDs:** {selected_record.get('formula_ids') or []}")
with right_col:
    st.write(f"**Factor ID:** {selected_record.get('factor_id') or 'Needs confirmation'}")
    st.write(f"**Factor source/version:** {selected_record.get('factor_source') or 'Needs confirmation'}")
    st.write(f"**CO2 (kg):** {selected_record.get('co2_kg')}")
    st.write(f"**CH4 (kg):** {selected_record.get('ch4_kg')}")
    st.write(f"**N2O (kg):** {selected_record.get('n2o_kg')}")
    st.write(f"**Biogenic CO2 (kg):** {selected_record.get('biogenic_co2_kg')}")
    st.write(f"**GWP basis:** {selected_record.get('gwp_basis') or 'Needs confirmation'}")

st.write(f"**Recalculated CO2e (mt):** {selected_record.get('recalculated_co2e_mt')}")
st.write(f"**Workbook-reported CO2e (mt):** {selected_record.get('workbook_co2e_mt')}")
st.write(f"**Variance (mt):** {selected_record.get('difference_mt')}")
st.write(f"**Variance (%)**: {selected_record.get('variance_percent')}")
st.write(f"**Materiality result:** {selected_record.get('materiality_result') or 'Needs confirmation'}")

with st.expander("Advanced calculation JSON", expanded=False):
    st.json(selected_record)
