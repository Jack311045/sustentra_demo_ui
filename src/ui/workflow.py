from __future__ import annotations

import streamlit as st


WORKFLOW_STEPS = [
    (1, "Setup", "Audit Setup"),
    (2, "Intake", "Evidence Intake"),
    (3, "Extract", "Extraction Review"),
    (4, "Validate", "Validation"),
    (5, "Calculate", "Calculation & Reconciliation"),
    (6, "Gap Analysis", "Gap Analysis"),
    (7, "Regulatory", "Regulatory Assistant"),
]


PREPARED_DISCLOSURE = (
    "Prepared demo workflow: some extraction, validation, calculation, and gap-analysis "
    "results are precomputed to demonstrate the intended auditor experience."
)


def render_workflow_progress(current_step: int) -> None:
    st.caption("Setup -> Intake -> Extract -> Validate -> Calculate -> Gap Analysis")

    active_steps = [step for step in WORKFLOW_STEPS if step[0] <= 6]
    columns = st.columns(len(active_steps))

    for col, (index, short_label, full_label) in zip(columns, active_steps):
        with col:
            with st.container(border=True):
                if index < current_step:
                    icon = "✅"
                    state_text = "Completed"
                elif index == current_step:
                    icon = "🔵"
                    state_text = "Current"
                else:
                    icon = "⚪"
                    state_text = "Pending"

                st.markdown(f"**{icon} {short_label}**")
                st.caption(full_label)
                st.caption(state_text)


def render_prepared_demo_disclosure() -> None:
    st.caption(PREPARED_DISCLOSURE)


def render_regulatory_stage_hint() -> None:
    with st.container(border=True):
        st.markdown("**Step 7 · Regulatory Assistant**")
        st.caption("Use source-backed NY Part 253 support for auditor follow-up questions.")
