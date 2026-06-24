"""Calculation & Reconciliation (Page 5).

Narrative auditor workflow for prepared calculation/reconciliation outputs. This
page is read-only with respect to ``analysis_response`` and uses only the
session overlay for UI interactions (for example, reveal-state toggles).
"""

from __future__ import annotations

import streamlit as st

from src.ui.components import render_audit_setup_context
from src.ui.extraction_review import get_extraction_review_progress
from src.ui.formatting import safe_text
from src.ui.libraries import (
    emission_factor_library_source_label,
    factor_energy_basis,
    factor_reference_label,
    gwp_reference_label,
    gwp_values,
    parse_materiality_absolute,
    parse_materiality_percent,
    resolve_calculation_template,
    resolve_formulas,
    resolve_emission_factor,
    resolve_gwp_set,
)
from src.ui.state import (
    create_gap_ticket,
    get_analysis_response,
    get_audit_setup,
    get_created_gap_ticket_ids,
    get_reviewed_extraction_fields,
    init_session_state,
    open_original_evidence,
    set_selected_gap_ticket_id,
    set_selected_validation_id,
)
from src.ui.workflow import render_prepared_demo_disclosure


NOT_COMPUTED = "not_computed_in_current_demo"
COMPUTED = "computed"

_HELD_SORT_ORDER = {
    "CALC-BLR003-2023-009": 0,
    "CALC-NG-2023-012": 1,
}

_HELD_EXPLANATIONS = {
    "CALC-BLR003-2023-009": {
        "title": "BLR-003 biomass activity",
        "reason": (
            "Held — requires validated biomass heat-content conversion and a "
            "biomass-aligned emission factor before MMBtu normalization."
        ),
        "assurance": (
            "Validation identified the same methodology issue. The system refuses "
            "to create an emissions result from an unsupported conversion."
        ),
    },
    "CALC-NG-2023-012": {
        "title": "Natural gas — December cross-year period",
        "reason": "Held — requires allocation of the service period between the 2023 and 2024 reporting years.",
        "assurance": (
            "Validation identified the same cutoff issue. The system refuses to "
            "calculate until the reporting-year allocation is supported."
        ),
    },
}

_HELD_VALIDATION_LINKS = {
    "CALC-BLR003-2023-009": [
        ("VAL-BLR003-2023-009", "Review validation issue"),
        ("VAL-LAB-2023-001", "Review related sampling support"),
    ],
    "CALC-NG-2023-012": [("VAL-NG-2023-012", "Review validation issue")],
}


def _switch_to(page: str, fallback: str) -> None:
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        try:
            switch_page(page)
            return
        except Exception:
            pass
    st.info(fallback)


def _fmt(value, *, decimals: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if decimals <= 0:
            return f"{value:,.0f}"
        text = f"{value:,.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return safe_text(value)


def _num(value):
    return value if isinstance(value, (int, float)) else None


def _held_sort_key(record: dict) -> tuple[int, str]:
    calculation_id = str(record.get("calculation_id") or "")
    return (_HELD_SORT_ORDER.get(calculation_id, 99), calculation_id)


def _reveal_key(calculation_id: str) -> str:
    return f"calculation_reveal::{calculation_id}"


def _go_to_validation(validation_id: str) -> None:
    set_selected_validation_id(validation_id)
    _switch_to(
        "pages/4_Validation.py",
        "Open Validation from the sidebar to review this validation issue.",
    )


def _render_held_record(record: dict) -> None:
    calculation_id = str(record.get("calculation_id") or "")
    explanation = _HELD_EXPLANATIONS.get(calculation_id, {})
    title = explanation.get("title") or safe_text(record.get("source_or_fuel")) or "Held record"
    reason = explanation.get("reason") or (
        "Held — a required validated methodology input is unavailable in the prepared demo."
    )
    assurance_text = explanation.get("assurance") or (
        "Validation identified the same prerequisite issue. The system refuses to "
        "calculate until the method input is supported."
    )

    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.error("Held")
        st.write(reason)
        st.caption(assurance_text)
        st.caption("Validation context")

        validation_links = _HELD_VALIDATION_LINKS.get(calculation_id, [])
        if validation_links:
            cols = st.columns(len(validation_links))
            for idx, (validation_id, label) in enumerate(validation_links):
                if cols[idx].button(
                    label,
                    key=f"held_validation_{calculation_id}_{validation_id}",
                ):
                    _go_to_validation(validation_id)


def _render_advanced_details(
    record: dict,
    formulas: list[dict],
    factor_record: dict | None,
    gwp_set: dict | None,
    consistency_check: dict,
) -> None:
    with st.expander("Advanced calculation details", expanded=False):
        calculation_id = safe_text(record.get("calculation_id"))
        linked_ids = record.get("linked_evidence_ids") if isinstance(record.get("linked_evidence_ids"), list) else []
        workbook_location = (
            record.get("workbook_location")
            if isinstance(record.get("workbook_location"), dict)
            else {}
        )
        formula_ids = record.get("formula_ids") if isinstance(record.get("formula_ids"), list) else []

        st.write(f"Calculation ID: {calculation_id or 'Unavailable'}")
        st.write(f"Linked evidence IDs: {', '.join(str(item) for item in linked_ids) if linked_ids else 'Unavailable'}")

        if workbook_location:
            sheet = safe_text(workbook_location.get("sheet_name")) or "Unknown"
            cell = safe_text(workbook_location.get("cell_or_range")) or "Unknown"
            st.write(f"Workbook location: {sheet}!{cell}")
        else:
            st.write("Workbook location: Unavailable")

        st.write(f"Raw factor ID: {safe_text(record.get('factor_id')) or 'Unavailable'}")
        st.write(f"Raw GWP ID: {safe_text(record.get('gwp_basis')) or 'Unavailable'}")
        st.write(
            "Raw formula/reconciliation rule IDs: "
            + (", ".join(str(item) for item in formula_ids) if formula_ids else "Unavailable")
        )

        st.markdown("**Formula-library records**")
        st.json(formulas)

        st.markdown("**Emission-factor record**")
        st.json(factor_record if isinstance(factor_record, dict) else {})

        st.markdown("**GWP-set record**")
        st.json(gwp_set if isinstance(gwp_set, dict) else {})

        st.markdown("**Calculation template**")
        st.json(resolve_calculation_template("ENERGY_BASIS_STATIONARY_COMBUSTION") or {})

        st.markdown("**Non-mutating consistency-check math**")
        st.json(consistency_check)

        st.markdown("**Raw prepared calculation JSON**")
        st.json(record)


def _render_computed_record(record: dict, audit_setup: dict) -> None:
    calculation_id = str(record.get("calculation_id") or "")
    linked_ids = record.get("linked_evidence_ids") if isinstance(record.get("linked_evidence_ids"), list) else []
    approved_evidence_id = str(linked_ids[0]) if linked_ids else ""
    created_ids = set(get_created_gap_ticket_ids())

    with st.container(border=True):
        st.markdown("### Ready to recalculate")
        st.markdown("#### Natural gas — October bill")
        if approved_evidence_id:
            st.caption(f"Approved evidence: {approved_evidence_id}")

        if st.button("Run recalculation", key=f"run_recalculation_{calculation_id}", type="primary"):
            st.session_state[_reveal_key(calculation_id)] = True

        revealed = bool(st.session_state.get(_reveal_key(calculation_id), False))
        if not revealed:
            return

        factor_record = resolve_emission_factor(safe_text(record.get("factor_id")))
        basis = factor_energy_basis(factor_record)
        gwp_set = resolve_gwp_set(safe_text(record.get("gwp_basis")) or None)
        gwp_map = gwp_values(gwp_set)
        formulas = resolve_formulas([str(item) for item in (record.get("formula_ids") or [])])

        st.markdown("#### Step 1 — Activity")
        st.metric("Activity", f"{_fmt(_num(record.get('activity_quantity')), decimals=0)} MMBtu")
        st.caption(
            "Source: auditor-approved evidence "
            + (approved_evidence_id if approved_evidence_id else "Unavailable")
        )
        if approved_evidence_id and st.button(
            "Open approved evidence",
            key=f"open_approved_evidence_{calculation_id}",
        ):
            open_original_evidence(approved_evidence_id)

        st.markdown("#### Step 2 — Emission factor")
        st.write("EPA Emission Factors Hub 2025")
        st.write("Stationary combustion — natural gas")
        st.caption(f"Source: {emission_factor_library_source_label()}")

        st.markdown("#### Step 3 — Per-gas emissions")
        gas_col1, gas_col2, gas_col3 = st.columns(3)
        gas_col1.metric("CO2", f"{_fmt(_num(record.get('co2_kg')), decimals=0)} kg")
        gas_col2.metric("CH4", f"{_fmt(_num(record.get('ch4_kg')), decimals=1)} kg")
        gas_col3.metric("N2O", f"{_fmt(_num(record.get('n2o_kg')), decimals=2)} kg")
        st.caption("Per-gas mass values are derived from the selected canonical combustion factor.")

        st.markdown("#### Step 4 — GWP conversion")
        st.write(gwp_reference_label(safe_text(record.get("gwp_basis")) or None))
        gwp_col1, gwp_col2, gwp_col3 = st.columns(3)
        gwp_col1.metric("CO2", _fmt(_num(gwp_map.get("CO2")), decimals=0))
        gwp_col2.metric("CH4", _fmt(_num(gwp_map.get("CH4_NON_FOSSIL")), decimals=0))
        gwp_col3.metric("N2O", _fmt(_num(gwp_map.get("N2O")), decimals=0))

        st.markdown("#### Step 5 — Recalculated result")
        recalculated_mt = _num(record.get("recalculated_co2e_mt"))
        st.metric("Recalculated", f"{_fmt(recalculated_mt, decimals=1)} tCO2e")
        st.caption(
            "Recalculated from the auditor-approved evidence baseline using the selected "
            "canonical factor and GWP references."
        )

        st.markdown("### Reconciliation punchline")
        workbook_mt = _num(record.get("workbook_co2e_mt"))
        difference_mt = _num(record.get("difference_mt"))
        variance_pct = _num(record.get("variance_percent"))

        comp_col1, comp_col2 = st.columns(2)
        comp_col1.metric("Recalculated", f"{_fmt(recalculated_mt, decimals=1)} tCO2e")
        comp_col2.metric("Workbook", f"{_fmt(workbook_mt, decimals=1)} tCO2e")

        variance_col1, variance_col2 = st.columns(2)
        variance_col1.metric("Variance", f"{_fmt(difference_mt, decimals=1)} tCO2e")
        variance_col2.metric("Variance %", f"{_fmt(variance_pct, decimals=0)}%")

        if recalculated_mt and workbook_mt:
            st.error(f"Workbook is {workbook_mt / recalculated_mt:,.1f}x the recalculated result.")

        materiality_pct = parse_materiality_percent(audit_setup)
        materiality_abs = parse_materiality_absolute(audit_setup)

        rel_breached = (
            variance_pct is not None
            and materiality_pct is not None
            and abs(variance_pct) > materiality_pct
        )
        abs_breached = (
            difference_mt is not None
            and materiality_abs is not None
            and abs(difference_mt) > materiality_abs
        )

        if variance_pct is not None and materiality_pct is not None:
            status = "breached" if rel_breached else "within threshold"
            st.write(
                f"Relative variance: {_fmt(variance_pct, decimals=0)}% versus the "
                f"{_fmt(materiality_pct, decimals=0)}% threshold — {status}."
            )

        if difference_mt is not None and materiality_abs is not None:
            status = "breached" if abs_breached else "within threshold"
            st.write(
                f"Absolute difference: {_fmt(difference_mt, decimals=1)} tCO2e versus the "
                f"{_fmt(materiality_abs, decimals=0)} tCO2e threshold — {status}."
            )

        st.markdown("### Gap handoff")
        st.write("This variance maps to finding GT-DEMO-GAP-003.")

        gap003_col1, gap003_col2 = st.columns(2)
        if "GT-DEMO-GAP-003" in created_ids:
            gap003_col1.success("Created")
            if gap003_col2.button(
                "Open GT-DEMO-GAP-003 in Gap Analysis",
                key=f"open_gap_003_{calculation_id}",
                use_container_width=True,
            ):
                set_selected_gap_ticket_id("GT-DEMO-GAP-003")
                _switch_to(
                    "pages/6_Gap_Analysis.py",
                    "Open Gap Analysis from the sidebar to review GT-DEMO-GAP-003.",
                )
        else:
            if gap003_col1.button(
                "Register finding GT-DEMO-GAP-003",
                key=f"register_gap_003_{calculation_id}",
                type="primary",
                use_container_width=True,
            ):
                create_gap_ticket("GT-DEMO-GAP-003")
                st.success("Created finding GT-DEMO-GAP-003.")
                st.rerun()

        st.caption("GT-DEMO-GAP-010 remains under review pending regulatory basis confirmation.")
        if st.button(
            "Open GT-DEMO-GAP-010 in Gap Analysis",
            key=f"open_gap_010_{calculation_id}",
            use_container_width=True,
        ):
            set_selected_gap_ticket_id("GT-DEMO-GAP-010")
            _switch_to(
                "pages/6_Gap_Analysis.py",
                "Open Gap Analysis from the sidebar to review GT-DEMO-GAP-010.",
            )

        activity = _num(record.get("activity_quantity"))
        co2_factor = _num((basis.get("co2") or {}).get("value"))
        ch4_factor = _num((basis.get("ch4") or {}).get("value"))
        n2o_factor = _num((basis.get("n2o") or {}).get("value"))
        gwp_co2 = _num(gwp_map.get("CO2"))
        gwp_ch4 = _num(gwp_map.get("CH4_NON_FOSSIL"))
        gwp_n2o = _num(gwp_map.get("N2O"))

        consistency_check: dict = {"inputs_available": False}
        if None not in (activity, co2_factor, ch4_factor, n2o_factor, gwp_co2, gwp_ch4, gwp_n2o):
            co2_kg = activity * co2_factor
            ch4_kg = activity * ch4_factor / 1000
            n2o_kg = activity * n2o_factor / 1000
            co2e_mt = (co2_kg * gwp_co2 + ch4_kg * gwp_ch4 + n2o_kg * gwp_n2o) / 1000
            consistency_check = {
                "inputs_available": True,
                "activity_mmbtu": activity,
                "factor_reference_label": factor_reference_label(safe_text(record.get("factor_id"))),
                "gwp_reference_label": gwp_reference_label(safe_text(record.get("gwp_basis")) or None),
                "calculated_co2_kg": co2_kg,
                "calculated_ch4_kg": ch4_kg,
                "calculated_n2o_kg": n2o_kg,
                "calculated_recalculated_co2e_mt": co2e_mt,
                "prepared_recalculated_co2e_mt": recalculated_mt,
                "difference_vs_prepared": (co2e_mt - recalculated_mt) if recalculated_mt is not None else None,
            }

        _render_advanced_details(
            record,
            formulas=formulas,
            factor_record=factor_record,
            gwp_set=gwp_set,
            consistency_check=consistency_check,
        )


init_session_state()
st.title("Calculation & Reconciliation")
st.caption("Recalculate auditor-approved evidence and reconcile against the workbook-reported totals.")
render_prepared_demo_disclosure()

analysis_response = get_analysis_response()
if not analysis_response:
    st.info("No prepared analysis loaded yet. Open Evidence Intake and run the prepared demo workflow.")
    st.stop()

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

calculation_results = [
    item for item in (analysis_response.get("calculation_results") or []) if isinstance(item, dict)
]
if not calculation_results:
    st.info("No calculation results are available in this prepared dataset.")
    st.stop()

attempted_count = len(calculation_results)
computed_records = [
    item for item in calculation_results if str(item.get("calculation_status") or "").strip().lower() == COMPUTED
]
held_records = [
    item
    for item in calculation_results
    if str(item.get("calculation_status") or "").strip().lower() == NOT_COMPUTED
]

st.subheader("Calculation queue")
st.write(
    f"{attempted_count} records attempted · {len(computed_records)} computed · "
    f"{len(held_records)} held for validated input"
)

queue_col1, queue_col2, queue_col3 = st.columns(3)
queue_col1.metric("Attempted", attempted_count)
queue_col2.metric("Computed", len(computed_records))
queue_col3.metric("Held", len(held_records))

if len(held_records) == 2:
    st.info(
        "Two records are intentionally held because validated methodology inputs are not ready. "
        "Sustentra does not guess missing conversion, factor, or allocation inputs."
    )
else:
    st.info(
        f"{len(held_records)} records are intentionally held because validated methodology "
        "inputs are not ready. Sustentra does not guess missing conversion, factor, or allocation inputs."
    )

audit_setup = get_audit_setup()
with st.expander("Engagement context", expanded=False):
    render_audit_setup_context(audit_setup)

if held_records:
    st.markdown("### Held for validated input")
    for held_record in sorted(held_records, key=_held_sort_key):
        _render_held_record(held_record)

if not computed_records:
    st.info("No computed records are available in the current prepared dataset.")
    st.stop()

computed_record = next(
    (
        item
        for item in computed_records
        if str(item.get("calculation_id") or "") == "CALC-NG-2023-010"
    ),
    computed_records[0],
)

_render_computed_record(computed_record, audit_setup)
