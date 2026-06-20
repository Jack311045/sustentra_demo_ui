from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisRun:
    run_id: str
    status: str
    evidence_results: list = field(default_factory=list)
    workbook_results: list = field(default_factory=list)
    gap_tickets: list = field(default_factory=list)
