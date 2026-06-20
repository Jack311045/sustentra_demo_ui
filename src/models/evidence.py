from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceResult:
    evidence_id: str
    file_name: str | None = None
    evidence_type_id: str | None = None
    status: str | None = None
    extracted_fields: dict = field(default_factory=dict)
