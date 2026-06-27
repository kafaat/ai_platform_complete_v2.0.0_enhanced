"""Simple SLA monitor for KG/RAG/MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class SlaSample:
    name: str
    elapsed_ms: float
    target_ms: float

    @property
    def passed(self) -> bool:
        return self.elapsed_ms <= self.target_ms


class SlaMonitor:
    def __init__(self) -> None:
        self.samples: list[SlaSample] = []

    def record(self, name: str, elapsed_ms: float, target_ms: float) -> SlaSample:
        sample = SlaSample(name=name, elapsed_ms=elapsed_ms, target_ms=target_ms)
        self.samples.append(sample)
        return sample

    def summary(self) -> dict[str, object]:
        if not self.samples:
            return {"count": 0, "pass_rate": None, "avg_ms": None, "violations": []}
        violations = [s.name for s in self.samples if not s.passed]
        return {
            "count": len(self.samples),
            "pass_rate": round((len(self.samples) - len(violations)) / len(self.samples), 3),
            "avg_ms": round(mean(s.elapsed_ms for s in self.samples), 2),
            "violations": violations,
        }
