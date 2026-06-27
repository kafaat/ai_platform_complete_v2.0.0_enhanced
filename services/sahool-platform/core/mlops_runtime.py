"""Small dependency-free MLOps runtime for agronomic models.

This is intentionally not a replacement for MLflow.  It gives SAHOOL a stable
local contract now: model cards, champion/challenger policy, drift checks, and a
JSON persistence format.  A future MLflow adapter can map to the same contract.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Stage = Literal["candidate", "challenger", "shadow", "champion", "archived"]


class MLOpsRuntimeError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeModelCard:
    model_id: str
    version: str
    task: str
    stage: Stage
    training_rows: int
    metrics: dict[str, float]
    feature_contract: tuple[str, ...]
    created_at: str

    def validate(self) -> None:
        if self.stage in {"champion", "challenger", "shadow"} and self.training_rows < 30:
            raise MLOpsRuntimeError("production-adjacent models require >=30 rows")
        if self.stage == "champion" and "rmse" not in self.metrics:
            raise MLOpsRuntimeError("champion model requires rmse metric")
        if not self.feature_contract:
            raise MLOpsRuntimeError("model requires a feature contract")


class JsonModelRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def register(self, card: RuntimeModelCard) -> None:
        card.validate()
        cards = self._load()
        cards = [
            c
            for c in cards
            if not (c["model_id"] == card.model_id and c["version"] == card.version)
        ]
        cards.append({**asdict(card), "feature_contract": list(card.feature_contract)})
        self.path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")

    def champion_for(self, task: str) -> RuntimeModelCard | None:
        champions = [
            self._card(c) for c in self._load() if c["task"] == task and c["stage"] == "champion"
        ]
        if len(champions) > 1:
            raise MLOpsRuntimeError(f"multiple champions for task {task}")
        return champions[0] if champions else None

    def challenger_candidates(self, task: str) -> list[RuntimeModelCard]:
        return [
            self._card(c)
            for c in self._load()
            if c["task"] == task and c["stage"] in {"candidate", "challenger", "shadow"}
        ]

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _card(raw: dict) -> RuntimeModelCard:
        return RuntimeModelCard(**{**raw, "feature_contract": tuple(raw["feature_contract"])})


def should_promote(
    champion: RuntimeModelCard | None,
    candidate: RuntimeModelCard,
    metric: str = "rmse",
    min_relative_gain: float = 0.05,
) -> bool:
    candidate.validate()
    if champion is None:
        return (
            candidate.stage in {"candidate", "challenger", "shadow"} and metric in candidate.metrics
        )
    if metric not in champion.metrics or metric not in candidate.metrics:
        return False
    return candidate.metrics[metric] <= champion.metrics[metric] * (1 - min_relative_gain)


def detect_metric_drift(
    baseline: dict[str, float], current: dict[str, float], *, tolerance: float = 0.2
) -> dict[str, object]:
    drifted = []
    for key, base in baseline.items():
        if base == 0 or key not in current:
            continue
        if abs(current[key] - base) / abs(base) > tolerance:
            drifted.append(key)
    return {"drifted": bool(drifted), "metrics": drifted, "tolerance": tolerance}
