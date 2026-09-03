from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ModelUsage:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExtractionResult:
    url: str
    template_id: str
    strategy: str
    description_html: str = ""
    description_text: str = ""
    confidence: float = 0.0
    latency_ms: float = 0.0
    successful: bool = False
    warnings: list[str] = field(default_factory=list)
    usage: ModelUsage = field(default_factory=ModelUsage)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionRule:
    template_id: str
    xpath: str
    source: str
    created_at: str
    success_count: int = 0
    failure_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExtractionRule":
        return cls(**payload)
