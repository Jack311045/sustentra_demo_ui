import streamlit as st

from src.ui.components import render_offering_cards
from src.ui.state import init_session_state
from src.ui.workflow import render_prepared_demo_disclosure

st.set_page_config(page_title="Sustentra Demo", layout="wide")
init_session_state()

st.title("Sustentra Auditor Workflow Demo")
st.caption("Auditor-facing workflow for prepared extraction, validation, reconciliation, and gap review.")

st.subheader("Demo purpose")
render_offering_cards()

render_prepared_demo_disclosure()

st.info(
	"Use the sidebar to walk through Audit Setup, Evidence Intake, Extraction Review, Validation, "
	"Calculation & Reconciliation, Gap Analysis, and Sustentra AI Assistant."
)
