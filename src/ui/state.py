from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st

from src.api.adapters import has_meaningful_audit_setup, normalize_audit_setup


_DEFAULTS: dict[str, Any] = {
    "analysis_response": None,
    "selected_demo_scenario": "gap_path",
    "audit_setup": {},
    "audit_setup_user_saved": False,
    "audit_setup_revision": 0,
    "audit_setup_widgets_revision": -1,
    "uploaded_workbook_metadata": {},
    "uploaded_evidence_metadata": [],
    "reviewed_extraction_fields": {},
    "selected_evidence_id": None,
    "selected_validation_id": None,
    "selected_calculation_id": None,
    "selected_gap_ticket_id": None,
    "created_gap_ticket_ids": [],
    "gap_ticket_overrides": {},
    "open_create_modal_for": None,
    "selected_workbook_location": None,
    "focused_source_evidence_id": None,
    "focused_source_field_key": None,
    "extraction_review_bulk_acknowledged": False,
    "chat_history": [],
    "chat_context_gap_ticket_id": None,
    "prepared_demo_disclosure_acknowledged": False,
    "selected_chat_question": None,
    "use_mock_api": True,
    "demo_analysis_loaded_from_uploaded_flow": False,
    "mock_auditor_actions": {},
}


def _clean_ticket_id(ticket_id: Any) -> str:
    text = str(ticket_id or "").strip()
    return text


def _merge_dict(base: dict, changes: dict) -> dict:
    merged = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged.get(key) or {}, value)
        else:
            merged[key] = value
    return merged


def init_session_state() -> None:
    for key, value in _DEFAULTS.items():
        st.session_state.setdefault(key, value)

    raw_setup = st.session_state.get("audit_setup")
    if has_meaningful_audit_setup(raw_setup):
        st.session_state["audit_setup"] = normalize_audit_setup(raw_setup)
    else:
        st.session_state["audit_setup"] = {}

    analysis_response = st.session_state.get("analysis_response")
    if isinstance(analysis_response, dict):
        normalized_response = dict(analysis_response)
        raw_response_setup = normalized_response.get("audit_setup")
        if has_meaningful_audit_setup(raw_response_setup):
            normalized_response["audit_setup"] = normalize_audit_setup(raw_response_setup)
        else:
            normalized_response["audit_setup"] = {}
        st.session_state["analysis_response"] = normalized_response


def set_analysis_response(response: dict) -> None:
    if not isinstance(response, dict):
        st.session_state["analysis_response"] = {}
        return

    normalized = dict(response)
    raw_setup = normalized.get("audit_setup")
    if has_meaningful_audit_setup(raw_setup):
        normalized["audit_setup"] = normalize_audit_setup(raw_setup)
    else:
        normalized["audit_setup"] = {}
    st.session_state["analysis_response"] = normalized


def get_analysis_response() -> dict | None:
    value = st.session_state.get("analysis_response")
    return value if isinstance(value, dict) else None


def set_selected_demo_scenario(scenario_id: str) -> None:
    st.session_state["selected_demo_scenario"] = str(scenario_id or "gap_path")


def get_selected_demo_scenario() -> str:
    value = st.session_state.get("selected_demo_scenario")
    if isinstance(value, str) and value.strip():
        return value
    return "gap_path"


def set_audit_setup(
    value: dict,
    *,
    user_saved: bool | None = None,
    increment_revision: bool = True,
) -> None:
    cleaned = normalize_audit_setup(value) if has_meaningful_audit_setup(value) else {}
    existing = st.session_state.get("audit_setup")
    if not isinstance(existing, dict):
        existing = {}

    if existing != cleaned:
        st.session_state["audit_setup"] = cleaned
        if increment_revision:
            current_revision = int(st.session_state.get("audit_setup_revision", 0))
            st.session_state["audit_setup_revision"] = current_revision + 1

    if user_saved is not None:
        st.session_state["audit_setup_user_saved"] = bool(user_saved)


def get_audit_setup() -> dict:
    value = st.session_state.get("audit_setup")
    if has_meaningful_audit_setup(value):
        normalized = normalize_audit_setup(value)
        st.session_state["audit_setup"] = normalized
        return normalized
    return {}


def is_audit_setup_user_saved() -> bool:
    return bool(st.session_state.get("audit_setup_user_saved", False))


def get_audit_setup_revision() -> int:
    try:
        return int(st.session_state.get("audit_setup_revision", 0))
    except (TypeError, ValueError):
        return 0


def update_audit_setup_field(section_key: str, field_key: str, value: Any) -> None:
    audit_setup = get_audit_setup()
    section_value = audit_setup.get(section_key)
    if not isinstance(section_value, dict):
        section_value = {}
    section_value[field_key] = value
    audit_setup[section_key] = section_value
    set_audit_setup(audit_setup)


def set_uploaded_workbook_metadata(metadata: dict | None) -> None:
    st.session_state["uploaded_workbook_metadata"] = metadata if isinstance(metadata, dict) else {}


def get_uploaded_workbook_metadata() -> dict:
    value = st.session_state.get("uploaded_workbook_metadata")
    return value if isinstance(value, dict) else {}


def set_uploaded_evidence_metadata(metadata: list[dict] | None) -> None:
    cleaned: list[dict] = []
    for item in metadata or []:
        if isinstance(item, dict):
            cleaned.append(item)
    st.session_state["uploaded_evidence_metadata"] = cleaned


def get_uploaded_evidence_metadata() -> list[dict]:
    value = st.session_state.get("uploaded_evidence_metadata")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def set_uploaded_file_metadata(
    workbook_name: str | None,
    workbook_size: int | None,
    evidence_files: list[dict] | None,
) -> None:
    workbook_record = {
        "name": workbook_name,
        "size_bytes": workbook_size,
    }
    set_uploaded_workbook_metadata(workbook_record)
    set_uploaded_evidence_metadata(evidence_files)


def get_uploaded_file_metadata() -> dict:
    workbook_metadata = get_uploaded_workbook_metadata()
    evidence_metadata = get_uploaded_evidence_metadata()
    evidence_names = [
        str(item.get("name"))
        for item in evidence_metadata
        if isinstance(item.get("name"), str) and item.get("name")
    ]
    evidence_total_size = 0
    for item in evidence_metadata:
        size_value = item.get("size_bytes")
        try:
            size_int = int(size_value) if size_value is not None else 0
        except (TypeError, ValueError):
            size_int = 0
        if size_int > 0:
            evidence_total_size += size_int

    return {
        "uploaded_workbook_name": workbook_metadata.get("name"),
        "uploaded_workbook_size": workbook_metadata.get("size_bytes"),
        "uploaded_evidence_names": evidence_names,
        "uploaded_evidence_count": len(evidence_names),
        "uploaded_evidence_total_size": evidence_total_size,
        "demo_analysis_loaded_from_uploaded_flow": bool(
            st.session_state.get("demo_analysis_loaded_from_uploaded_flow", False)
        ),
        "uploaded_workbook_metadata": workbook_metadata,
        "uploaded_evidence_metadata": evidence_metadata,
    }


def set_reviewed_extraction_field(evidence_id: str, field_key: str, payload: dict) -> None:
    reviewed = st.session_state.get("reviewed_extraction_fields")
    if not isinstance(reviewed, dict):
        reviewed = {}

    evidence_map = reviewed.get(evidence_id)
    if not isinstance(evidence_map, dict):
        evidence_map = {}

    evidence_map[field_key] = payload if isinstance(payload, dict) else {"value": payload}
    reviewed[evidence_id] = evidence_map
    st.session_state["reviewed_extraction_fields"] = reviewed


def get_reviewed_extraction_fields(evidence_id: str | None = None) -> dict:
    reviewed = st.session_state.get("reviewed_extraction_fields")
    if not isinstance(reviewed, dict):
        return {}
    if not evidence_id:
        return reviewed
    evidence_map = reviewed.get(evidence_id)
    return evidence_map if isinstance(evidence_map, dict) else {}


def set_reviewed_extraction_fields(mapping: dict) -> None:
    """Replace the whole review overlay in a single write (bulk operations).

    Only well-formed ``{evidence_id: {field_key: payload}}`` shapes are stored;
    malformed entries are dropped defensively so a bulk update can never corrupt
    the overlay.
    """
    if not isinstance(mapping, dict):
        return
    cleaned: dict = {}
    for evidence_id, field_map in mapping.items():
        if not isinstance(field_map, dict):
            continue
        cleaned[str(evidence_id)] = {
            str(field_key): (payload if isinstance(payload, dict) else {"value": payload})
            for field_key, payload in field_map.items()
        }
    st.session_state["reviewed_extraction_fields"] = cleaned



def add_auditor_extraction_field(evidence_id: str, field_key: str, value: Any) -> None:
    """Record an auditor-supplied extraction field in the review overlay only.

    This never mutates ``analysis_response``; the added field lives in the
    reviewer overlay and is treated as an Edited (auditor-authored) value.
    """
    set_reviewed_extraction_field(
        evidence_id,
        field_key,
        {"status": "Edited", "edited_value": value, "auditor_added": True},
    )


def set_focused_source_field(evidence_id: str | None, field_key: str | None) -> None:
    st.session_state["focused_source_evidence_id"] = evidence_id
    st.session_state["focused_source_field_key"] = field_key


def get_focused_source_field() -> dict:
    return {
        "evidence_id": st.session_state.get("focused_source_evidence_id"),
        "field_key": st.session_state.get("focused_source_field_key"),
    }


def set_extraction_review_bulk_acknowledged(acknowledged: bool) -> None:
    st.session_state["extraction_review_bulk_acknowledged"] = bool(acknowledged)


def get_extraction_review_bulk_acknowledged() -> bool:
    return bool(st.session_state.get("extraction_review_bulk_acknowledged", False))


def set_selected_evidence_id(evidence_id: str | None) -> None:
    st.session_state["selected_evidence_id"] = evidence_id


def get_selected_evidence_id() -> str | None:
    value = st.session_state.get("selected_evidence_id")
    return value if isinstance(value, str) and value else None


def set_selected_validation_id(validation_id: str | None) -> None:
    st.session_state["selected_validation_id"] = validation_id


def get_selected_validation_id() -> str | None:
    value = st.session_state.get("selected_validation_id")
    return value if isinstance(value, str) and value else None


def set_selected_calculation_id(calculation_id: str | None) -> None:
    st.session_state["selected_calculation_id"] = calculation_id


def get_selected_calculation_id() -> str | None:
    value = st.session_state.get("selected_calculation_id")
    return value if isinstance(value, str) and value else None


def set_selected_gap_ticket_id(ticket_id: str | None) -> None:
    st.session_state["selected_gap_ticket_id"] = ticket_id


def get_selected_gap_ticket_id() -> str | None:
    value = st.session_state.get("selected_gap_ticket_id")
    return value if isinstance(value, str) and value else None


def get_created_gap_ticket_ids() -> list[str]:
    value = st.session_state.get("created_gap_ticket_ids")
    if not isinstance(value, list):
        return []

    ordered: list[str] = []
    seen: set[str] = set()
    for item in value:
        ticket_id = _clean_ticket_id(item)
        if not ticket_id or ticket_id in seen:
            continue
        ordered.append(ticket_id)
        seen.add(ticket_id)

    return list(ordered)


def get_gap_ticket_overrides() -> dict[str, dict]:
    value = st.session_state.get("gap_ticket_overrides")
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, dict] = {}
    for raw_key, raw_override in value.items():
        ticket_id = _clean_ticket_id(raw_key)
        if not ticket_id or not isinstance(raw_override, dict):
            continue
        cleaned[ticket_id] = deepcopy(raw_override)
    return cleaned


def get_gap_ticket_override(ticket_id: str) -> dict:
    key = _clean_ticket_id(ticket_id)
    if not key:
        return {}
    overrides = get_gap_ticket_overrides()
    value = overrides.get(key)
    return deepcopy(value) if isinstance(value, dict) else {}


def set_gap_ticket_override(ticket_id: str, changes: dict) -> None:
    key = _clean_ticket_id(ticket_id)
    if not key or not isinstance(changes, dict):
        return

    merged_changes = {str(field): value for field, value in changes.items()}
    if not merged_changes:
        return

    overrides = get_gap_ticket_overrides()
    current = overrides.get(key) if isinstance(overrides.get(key), dict) else {}
    overrides[key] = _merge_dict(current, merged_changes)
    st.session_state["gap_ticket_overrides"] = overrides


def create_gap_ticket(ticket_id: str, overrides: dict | None = None) -> bool:
    key = _clean_ticket_id(ticket_id)
    if not key:
        return False

    created = get_created_gap_ticket_ids()
    already_exists = key in created
    if not already_exists:
        created.append(key)
        st.session_state["created_gap_ticket_ids"] = created

    if isinstance(overrides, dict) and overrides:
        set_gap_ticket_override(key, overrides)

    set_selected_gap_ticket_id(key)
    return not already_exists


def set_open_create_modal_for(ticket_id: str | None) -> None:
    key = _clean_ticket_id(ticket_id)
    st.session_state["open_create_modal_for"] = key or None


def get_open_create_modal_for() -> str | None:
    value = st.session_state.get("open_create_modal_for")
    key = _clean_ticket_id(value)
    return key if key else None


def update_mock_auditor_action(ticket_id: str, changes: dict) -> None:
    key = _clean_ticket_id(ticket_id)
    if not key or not isinstance(changes, dict):
        return

    actions = st.session_state.get("mock_auditor_actions")
    current_actions = actions if isinstance(actions, dict) else {}
    existing = current_actions.get(key) if isinstance(current_actions.get(key), dict) else {}
    current_actions[key] = _merge_dict(existing, changes)
    st.session_state["mock_auditor_actions"] = current_actions


def set_selected_workbook_location(location: dict | None) -> None:
    st.session_state["selected_workbook_location"] = location if isinstance(location, dict) else None


def get_selected_workbook_location() -> dict | None:
    value = st.session_state.get("selected_workbook_location")
    return value if isinstance(value, dict) else None


def set_chat_context_gap_ticket_id(ticket_id: str | None) -> None:
    st.session_state["chat_context_gap_ticket_id"] = ticket_id


def get_chat_context_gap_ticket_id() -> str | None:
    value = st.session_state.get("chat_context_gap_ticket_id")
    return value if isinstance(value, str) and value else None


def get_chat_history() -> list[dict]:
    value = st.session_state.get("chat_history")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def append_chat_message(role: str, content: str, metadata: dict | None = None) -> None:
    history = get_chat_history()
    history.append(
        {
            "role": str(role),
            "content": str(content),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
    )
    st.session_state["chat_history"] = history


def clear_chat_history() -> None:
    st.session_state["chat_history"] = []


def set_prepared_demo_disclosure_acknowledged(acknowledged: bool) -> None:
    st.session_state["prepared_demo_disclosure_acknowledged"] = bool(acknowledged)


def get_prepared_demo_disclosure_acknowledged() -> bool:
    return bool(st.session_state.get("prepared_demo_disclosure_acknowledged", False))


def _switch_page_with_fallback(target_page: str, fallback_message: str) -> bool:
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(target_page)
        return True
    st.info(fallback_message)
    return False


def open_original_evidence(evidence_id: str | None) -> bool:
    set_selected_evidence_id(evidence_id)
    return _switch_page_with_fallback(
        "pages/3_Extraction_Review.py",
        "Page navigation is not available in this environment. Open Extraction Review from the sidebar.",
    )


def open_workbook_location(location: dict | None) -> bool:
    set_selected_workbook_location(location)
    return _switch_page_with_fallback(
        "pages/5_Calculation_and_Reconciliation.py",
        "Page navigation is not available in this environment. Open Calculation & Reconciliation from the sidebar.",
    )


def open_applicable_regulation(ticket_id: str | None) -> bool:
    set_chat_context_gap_ticket_id(ticket_id)
    set_selected_gap_ticket_id(ticket_id)
    return _switch_page_with_fallback(
        "pages/7_Sustentra_AI_Assistant.py",
        "Page navigation is not available in this environment. Open Sustentra AI Assistant from the sidebar.",
    )


def ask_regulatory_assistant(ticket_id: str | None, suggested_prompt: str | None = None) -> bool:
    set_chat_context_gap_ticket_id(ticket_id)
    if suggested_prompt:
        st.session_state["selected_chat_question"] = suggested_prompt
    return _switch_page_with_fallback(
        "pages/7_Sustentra_AI_Assistant.py",
        "Page navigation is not available in this environment. Open Sustentra AI Assistant from the sidebar.",
    )


def draft_auditor_note(ticket_id: str | None) -> bool:
    set_selected_gap_ticket_id(ticket_id)
    st.session_state["draft_note_target_gap_ticket_id"] = ticket_id
    return _switch_page_with_fallback(
        "pages/6_Gap_Analysis.py",
        "Page navigation is not available in this environment. Open Gap Analysis from the sidebar.",
    )
