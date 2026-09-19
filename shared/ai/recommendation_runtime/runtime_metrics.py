"""Small Prometheus-compatible metric accumulator for tests and local runtime."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class RuntimeMetrics:
    counters: Counter = field(default_factory=Counter)

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)


runtime_metrics = RuntimeMetrics()
