from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatResponse:
    answer: str
    supporting_evidence_ids: list[str] = field(default_factory=list)
    supporting_gap_ticket_ids: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
