from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkbookObservation:
    workbook_id: str
    sheet_name: str
    cell_or_range: str
    relationship_to_gap: str | None = None
