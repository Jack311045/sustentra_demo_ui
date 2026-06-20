from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    gap_ticket_id: str
    title: str
    status: str
    primary_assertion: str | None = None
    trigger_ids: list[str] = field(default_factory=list)
