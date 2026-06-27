from collections import Counter
from dataclasses import dataclass, field


@dataclass
class GuardrailMetrics:
    counters: Counter = field(default_factory=Counter)

    def increment(self, metric: str) -> None:
        self.counters[metric] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)


metrics = GuardrailMetrics()
