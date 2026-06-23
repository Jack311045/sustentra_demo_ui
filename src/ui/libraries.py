"""Dynamic resolution of formula and emission-factor library records.

Page 5 (Calculation & Reconciliation) must not hardcode formula logic, factor
values, or GWP values. These helpers read the canonical library files so the
displayed methodology stays in lock-step with the libraries.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


FORMULA_LIBRARY_PATH = Path("config/libraries/formula_library.json")
EMISSION_FACTOR_LIBRARY_PATH = Path("config/libraries/emission_factor_library.json")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _formula_library() -> dict:
    return _load_json(FORMULA_LIBRARY_PATH)


@lru_cache(maxsize=1)
def _emission_factor_library() -> dict:
    return _load_json(EMISSION_FACTOR_LIBRARY_PATH)


def resolve_formula(formula_id: str) -> dict | None:
    """Return the formula record for ``formula_id`` (or ``None``)."""
    if not formula_id:
        return None
    library = _formula_library()
    records = library.get("formula_records")
    if not isinstance(records, list):
        return None
    for record in records:
        if isinstance(record, dict) and str(record.get("formula_id")) == str(formula_id):
            return record
    return None


def resolve_formulas(formula_ids: list[str] | None) -> list[dict]:
    resolved: list[dict] = []
    for formula_id in formula_ids or []:
        record = resolve_formula(str(formula_id))
        if record is not None:
            resolved.append(record)
    return resolved


def resolve_emission_factor(factor_id: str) -> dict | None:
    """Return the stationary-combustion factor record for ``factor_id``."""
    if not factor_id:
        return None
    library = _emission_factor_library()
    records = library.get("stationary_combustion_factors")
    if not isinstance(records, list):
        return None
    for record in records:
        if isinstance(record, dict) and str(record.get("factor_id")) == str(factor_id):
            return record
    return None


def resolve_gwp_set(gwp_set_id: str | None = None) -> dict | None:
    """Return a GWP set by id, or the library default when id is omitted."""
    library = _emission_factor_library()
    sets = library.get("gwp_sets")
    if not isinstance(sets, list):
        return None

    if gwp_set_id:
        for record in sets:
            if isinstance(record, dict) and str(record.get("gwp_set_id")) == str(gwp_set_id):
                return record

    for record in sets:
        if isinstance(record, dict) and record.get("default_for_this_library"):
            return record
    return sets[0] if sets and isinstance(sets[0], dict) else None


def gwp_values(gwp_set: dict | None) -> dict[str, Any]:
    """Map gwp_key -> gwp value for a GWP set."""
    if not isinstance(gwp_set, dict):
        return {}
    output: dict[str, Any] = {}
    for entry in gwp_set.get("values") or []:
        if isinstance(entry, dict) and entry.get("gwp_key"):
            output[str(entry["gwp_key"])] = entry.get("gwp")
    return output


def factor_energy_basis(factor: dict | None) -> dict[str, Any]:
    """Extract co2/ch4/n2o energy-basis factor values with units."""
    if not isinstance(factor, dict):
        return {}
    basis = factor.get("energy_basis_factors")
    if not isinstance(basis, dict):
        return {}
    output: dict[str, Any] = {}
    for gas in ("co2", "ch4", "n2o"):
        entry = basis.get(gas)
        if isinstance(entry, dict):
            output[gas] = {"value": entry.get("value"), "unit": entry.get("unit")}
    return output


_NUMERIC_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def parse_leading_number(value: Any) -> float | None:
    """Parse a leading numeric token from strings like '750 tCO2e' or '5%'."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    match = _NUMERIC_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_materiality_absolute(audit_setup: dict | None) -> float | None:
    """Numeric absolute materiality (tCO2e) parsed from Audit Setup."""
    if not isinstance(audit_setup, dict):
        return None
    materiality = audit_setup.get("materiality_and_thresholds")
    if not isinstance(materiality, dict):
        return None
    return parse_leading_number(materiality.get("materiality_absolute"))


def parse_materiality_percent(audit_setup: dict | None) -> float | None:
    """Numeric percentage materiality parsed from Audit Setup."""
    if not isinstance(audit_setup, dict):
        return None
    materiality = audit_setup.get("materiality_and_thresholds")
    if not isinstance(materiality, dict):
        return None
    return parse_leading_number(materiality.get("material_misstatement_percentage"))
