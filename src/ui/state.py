from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    st.session_state.setdefault("analysis_response", None)
    st.session_state.setdefault("selected_gap_ticket_id", None)
    st.session_state.setdefault("use_mock_api", True)
    st.session_state.setdefault("selected_evidence_id", None)
    st.session_state.setdefault("selected_chat_question", None)
    st.session_state.setdefault("uploaded_workbook_name", None)
    st.session_state.setdefault("uploaded_workbook_size", None)
    st.session_state.setdefault("uploaded_evidence_names", [])
    st.session_state.setdefault("uploaded_evidence_count", 0)
    st.session_state.setdefault("uploaded_evidence_total_size", 0)
    st.session_state.setdefault("demo_analysis_loaded_from_uploaded_flow", False)


def set_analysis_response(response: dict) -> None:
    st.session_state["analysis_response"] = response


def get_analysis_response() -> dict | None:
    value = st.session_state.get("analysis_response")
    return value if isinstance(value, dict) else None


def set_selected_gap_ticket_id(ticket_id: str | None) -> None:
    st.session_state["selected_gap_ticket_id"] = ticket_id


def get_selected_gap_ticket_id() -> str | None:
    value = st.session_state.get("selected_gap_ticket_id")
    return value if isinstance(value, str) else None


def set_uploaded_file_metadata(
    workbook_name: str | None,
    workbook_size: int | None,
    evidence_files: list[dict] | None,
) -> None:
    evidence_files = evidence_files or []
    evidence_names: list[str] = []
    evidence_total_size = 0

    for item in evidence_files:
        if not isinstance(item, dict):
            continue

        name_value = item.get("name")
        if isinstance(name_value, str) and name_value:
            evidence_names.append(name_value)

        size_value = item.get("size_bytes")
        try:
            size_int = int(size_value) if size_value is not None else 0
        except (TypeError, ValueError):
            size_int = 0
        if size_int > 0:
            evidence_total_size += size_int

    try:
        workbook_size_int = int(workbook_size) if workbook_size is not None else None
    except (TypeError, ValueError):
        workbook_size_int = None

    st.session_state["uploaded_workbook_name"] = workbook_name or None
    st.session_state["uploaded_workbook_size"] = workbook_size_int
    st.session_state["uploaded_evidence_names"] = evidence_names
    st.session_state["uploaded_evidence_count"] = len(evidence_names)
    st.session_state["uploaded_evidence_total_size"] = evidence_total_size


def get_uploaded_file_metadata() -> dict:
    return {
        "uploaded_workbook_name": st.session_state.get("uploaded_workbook_name"),
        "uploaded_workbook_size": st.session_state.get("uploaded_workbook_size"),
        "uploaded_evidence_names": st.session_state.get("uploaded_evidence_names") or [],
        "uploaded_evidence_count": st.session_state.get("uploaded_evidence_count") or 0,
        "uploaded_evidence_total_size": st.session_state.get("uploaded_evidence_total_size") or 0,
        "demo_analysis_loaded_from_uploaded_flow": bool(
            st.session_state.get("demo_analysis_loaded_from_uploaded_flow", False)
        ),
    }
