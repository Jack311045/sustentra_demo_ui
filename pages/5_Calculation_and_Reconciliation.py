"""Calculation & Reconciliation (Page 5).

All of Act 2: an independent human-review gate, dynamic formula/factor/GWP
resolution from the canonical libraries, a visible recalculation trail, the
reconciliation punchline, and explicit handoff into Gap Analysis.

This page is read-only with respect to ``analysis_response`` -- it never calls
``set_analysis_response``/``MockApiClient``/``adapt_analysis_response`` and never
mutates the prepared data. The gate is derived from ``reviewed_extraction_fields``
each rerun; there is no persisted ``review_complete``.
"""

from __future__ import annotations

import streamlit as st

from src.ui.components import render_audit_setup_context
from src.ui.extraction_review import get_extraction_review_progress
from src.ui.formatting import safe_text
from src.ui.libraries import (
    factor_energy_basis,
    gwp_values,
    parse_materiality_absolute,
    parse_materiality_percent,
    resolve_emission_factor,
    resolve_formulas,
    resolve_gwp_set,
)
from src.ui.state import (
    get_analysis_response,
    get_audit_setup,
    get_reviewed_extraction_fields,
    get_selected_calculation_id,
    get_selected_workbook_location,
    init_session_state,
    set_selected_calculation_id,
    set_selected_gap_ticket_id,
)
from src.ui.tables import render_calculation_table
from src.ui.workflow import render_prepared_demo_disclosure


NOT_COMPUTED = "not_computed_in_current_demo"


def _switch_to(page: str, fallback: str) -> None:
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(page)
    else:
        st.info(fallback)


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        text = f"{value:,.5f}".rstrip("0").rstrip(".")
        return text or "0"
    return safe_text(value)


def _num(value):
    return value if isinstance(value, (int, float)) else None


init_session_state()
st.title("Calculation & Reconciliation")
st.caption("Recalculate auditor-approved evidence and reconcile against the workbook-reported totals.")
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

audit_setup = get_audit_setup()
render_audit_setup_context(audit_setup)

# --- Independent human-review gate (derived) ----------------------------------
progress = get_extraction_review_progress(analysis_response, get_reviewed_extraction_fields())
if not progress["is_complete"]:
    st.warning(
        "Calculation is locked until extraction review is complete. "
        f"{progress['unconfirmed_fields']} field(s) still need a decision."
    )
    if st.button("Return to Extraction Review", type="primary"):
        _switch_to(
            "pages/3_Extraction_Review.py",
            "Open Extraction Review from the sidebar to finish the review.",
        )
    st.stop()

approved_count = progress["approved_record_count"]
st.success(f"Recalculated from {approved_count} auditor-approved evidence item(s).")
st.caption(
    "Prepared-demo values are shown as recorded; no live recomputation runs in this environment. "
    "Formula logic, emission factors, and GWP values are resolved from the canonical libraries."
)

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

st.subheader("Calculation records")
render_calculation_table(calculation_results)

calculation_ids = [str(item.get("calculation_id")) for item in calculation_results if item.get("calculation_id")]
selected_calculation_id = get_selected_calculation_id()
if selected_calculation_id not in calculation_ids:
    selected_calculation_id = calculation_ids[0]

# Honor a workbook deep-link from another page.
selected_workbook_location = get_selected_workbook_location()
if isinstance(selected_workbook_location, dict):
    desired_sheet = safe_text(selected_workbook_location.get("sheet_name")).strip().lower()
    desired_cell = safe_text(selected_workbook_location.get("cell_or_range")).strip().lower()
    for item in calculation_results:
        loc = item.get("workbook_location") if isinstance(item.get("workbook_location"), dict) else {}
        sheet = safe_text(loc.get("sheet_name")).strip().lower()
        cell = safe_text(loc.get("cell_or_range")).strip().lower()
        if desired_sheet and desired_cell and sheet == desired_sheet and cell == desired_cell:
            selected_calculation_id = str(item.get("calculation_id"))
            break

selected_calculation_id = st.selectbox(
    "Select calculation record",
    options=calculation_ids,
    index=calculation_ids.index(selected_calculation_id),
)
set_selected_calculation_id(selected_calculation_id)

record = next(
    (item for item in calculation_results if str(item.get("calculation_id")) == selected_calculation_id),
    None,
)
if not record:
    st.info("Selected calculation record could not be found.")
    st.stop()

status = record.get("calculation_status") or record.get("status")
st.subheader(safe_text(record.get("source_or_fuel")) or selected_calculation_id)

if status == NOT_COMPUTED:
    reason = safe_text(record.get("reason")) or "Required validated input is unavailable in the current demo."
    st.warning(f"Not computed in current demo: {reason}")
    st.caption(
        "This record is intentionally left uncomputed because a validated method input is missing; "
        "it is routed to Gap Analysis rather than producing an unsupported number."
    )

# --- Dynamic formula / factor / GWP resolution --------------------------------
st.markdown("### Methodology (resolved from libraries)")

formula_ids = record.get("formula_ids") if isinstance(record.get("formula_ids"), list) else []
formulas = resolve_formulas([str(fid) for fid in formula_ids])
if formulas:
    for formula in formulas:
        with st.container(border=True):
            st.markdown(f"**{safe_text(formula.get('formula_id'))} — {safe_text(formula.get('formula_name'))}**")
            logic = safe_text(formula.get("formula_logic"))
            if logic:
                st.code(logic, language="text")
else:
    st.caption("No formula records were referenced for this calculation.")

factor_id = safe_text(record.get("factor_id"))
factor = resolve_emission_factor(factor_id)
gwp_basis_id = safe_text(record.get("gwp_basis")) or None
gwp_set = resolve_gwp_set(gwp_basis_id)
gwp_map = gwp_values(gwp_set)

factor_col, gwp_col = st.columns(2)
with factor_col:
    st.markdown("**Emission factor**")
    if factor:
        basis = factor_energy_basis(factor)
        st.caption(f"{safe_text(factor.get('fuel_name'))} ({factor_id})")
        for gas in ("co2", "ch4", "n2o"):
            entry = basis.get(gas) or {}
            if entry.get("value") is not None:
                st.write(f"{gas.upper()}: {entry['value']} {safe_text(entry.get('unit'))}")
    else:
        st.caption(f"Factor '{factor_id}' is not resolvable for this record (validated method required).")
with gwp_col:
    st.markdown("**GWP basis**")
    if gwp_set:
        st.caption(safe_text(gwp_set.get("gwp_set_id")))
        for key in ("CO2", "CH4_NON_FOSSIL", "N2O"):
            if key in gwp_map:
                st.write(f"{key}: {gwp_map[key]}")
    else:
        st.caption("GWP basis is not resolvable for this record.")

# --- Recalculation trail (computed records only) ------------------------------
if status != NOT_COMPUTED and factor:
    st.markdown("### Recalculation trail")
    activity = _num(record.get("activity_quantity"))
    basis = factor_energy_basis(factor)
    co2_f = _num((basis.get("co2") or {}).get("value"))
    ch4_f = _num((basis.get("ch4") or {}).get("value"))
    n2o_f = _num((basis.get("n2o") or {}).get("value"))
    gwp_co2 = _num(gwp_map.get("CO2"))
    gwp_ch4 = _num(gwp_map.get("CH4_NON_FOSSIL"))
    gwp_n2o = _num(gwp_map.get("N2O"))

    if None not in (activity, co2_f, ch4_f, n2o_f, gwp_co2, gwp_ch4, gwp_n2o):
        co2_kg = activity * co2_f
        ch4_kg = activity * ch4_f / 1000
        n2o_kg = activity * n2o_f / 1000
        co2e_kg = co2_kg * gwp_co2 + ch4_kg * gwp_ch4 + n2o_kg * gwp_n2o
        co2e_mt = co2e_kg / 1000

        st.markdown(
            "Source evidence → extracted activity → normalized activity → selected factor → "
            "gas-level mass → GWP conversion → recalculated CO2e."
        )
        st.code(
            "\n".join(
                [
                    f"activity            = {activity:,.2f} {safe_text(record.get('activity_unit'))}",
                    f"CO2 (kg)            = {activity:,.2f} * {co2_f} = {co2_kg:,.2f}",
                    f"CH4 (kg)            = {activity:,.2f} * {ch4_f} / 1000 = {ch4_kg:,.4f}",
                    f"N2O (kg)            = {activity:,.2f} * {n2o_f} / 1000 = {n2o_kg:,.4f}",
                    f"CO2e (kg)           = {co2_kg:,.2f}*{gwp_co2} + {ch4_kg:,.4f}*{gwp_ch4} + {n2o_kg:,.4f}*{gwp_n2o}",
                    f"                    = {co2e_kg:,.5f}",
                    f"CO2e (metric tons)  = {co2e_kg:,.5f} / 1000 = {co2e_mt:,.5f}",
                ]
            ),
            language="text",
        )

        prepared = _num(record.get("recalculated_co2e_mt"))
        if prepared is not None and abs(prepared - co2e_mt) <= 1e-3:
            st.success(
                f"Recalculated total {co2e_mt:,.5f} tCO2e matches the prepared record "
                f"({prepared:,.5f} tCO2e)."
            )
        elif prepared is not None:
            st.error(
                f"Recalculated total {co2e_mt:,.5f} tCO2e differs from the prepared record "
                f"({prepared:,.5f} tCO2e)."
            )

    trail_cols = st.columns(3)
    trail_cols[0].metric("Recalculated CO2e (mt)", _fmt(record.get("recalculated_co2e_mt")))
    trail_cols[1].metric("Workbook CO2e (mt)", _fmt(record.get("workbook_co2e_mt")))
    trail_cols[2].metric("Variance (mt)", _fmt(record.get("difference_mt")))

# --- Reconciliation punchline -------------------------------------------------
st.markdown("### Reconciliation")
reported = _num(reconciliation_summary.get("reported_scope_1_mtco2e"))
recalculated = _num(reconciliation_summary.get("recalculated_scope_1_mtco2e"))
abs_diff = _num(reconciliation_summary.get("absolute_difference_mtco2e"))
variance_pct = _num(reconciliation_summary.get("variance_percent"))

materiality_pct = parse_materiality_percent(audit_setup)
materiality_abs = parse_materiality_absolute(audit_setup)

recon_cols = st.columns(4)
recon_cols[0].metric("Reported Scope 1 (mt)", _fmt(reported))
recon_cols[1].metric("Recalculated Scope 1 (mt)", _fmt(recalculated))
recon_cols[2].metric("Absolute difference (mt)", _fmt(abs_diff))
recon_cols[3].metric("Variance %", f"{variance_pct:g}%" if variance_pct is not None else "—")

threshold_bits = []
if materiality_pct is not None:
    threshold_bits.append(f"{materiality_pct:g}% relative")
if materiality_abs is not None:
    threshold_bits.append(f"{materiality_abs:g} tCO2e absolute")
threshold_text = " and ".join(threshold_bits) if threshold_bits else "the configured materiality thresholds"

exceeds_pct = variance_pct is not None and materiality_pct is not None and abs(variance_pct) > materiality_pct
exceeds_abs = abs_diff is not None and materiality_abs is not None and abs(abs_diff) > materiality_abs
if exceeds_pct or exceeds_abs:
    st.error(
        f"The reconciliation variance exceeds {threshold_text}. This is a material difference "
        "requiring a gap finding."
    )
else:
    st.info(f"Materiality thresholds applied from Audit Setup: {threshold_text}.")

# --- Gap handoff --------------------------------------------------------------
st.markdown("### Findings handoff")
gap_col1, gap_col2 = st.columns(2)
with gap_col1:
    st.markdown("**GAP-003 — October natural-gas overstatement**")
    st.caption("The workbook records 10x the source-bill quantity for October; routed to Gap Analysis.")
    if st.button("Open GAP-003 in Gap Analysis", type="primary"):
        set_selected_gap_ticket_id("GT-DEMO-GAP-003")
        _switch_to(
            "pages/6_Gap_Analysis.py",
            "Open Gap Analysis from the sidebar to review GAP-003.",
        )
with gap_col2:
    st.markdown("**GAP-010 — Workbook GWP basis**")
    st.caption("The workbook applies a GWP basis that differs from the engagement requirement.")
    if st.button("Open GAP-010 in Gap Analysis"):
        set_selected_gap_ticket_id("GT-DEMO-GAP-010")
        _switch_to(
            "pages/6_Gap_Analysis.py",
            "Open Gap Analysis from the sidebar to review GAP-010.",
        )

with st.expander("Advanced calculation JSON", expanded=False):
    st.json(record)
