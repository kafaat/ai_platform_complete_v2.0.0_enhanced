"""Minimal MLOps registry contracts for agronomic models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelStage = Literal["candidate", "shadow", "champion", "archived"]


class MLOpsRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ModelCard:
    model_id: str
    version: str
    task: str
    stage: ModelStage
    training_rows: int
    metrics: dict[str, float]
    source_features: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.stage in {"champion", "shadow"} and self.training_rows < 30:
            raise MLOpsRegistryError("champion/shadow models require at least 30 training rows")
        if self.stage == "champion" and not self.metrics:
            raise MLOpsRegistryError("champion model requires offline metrics")


class ModelRegistry:
    def __init__(self) -> None:
        self._cards: dict[tuple[str, str], ModelCard] = {}

    def register(self, card: ModelCard) -> None:
        self._cards[(card.model_id, card.version)] = card

    def champion_for(self, task: str) -> ModelCard | None:
        champions = [
            card for card in self._cards.values() if card.task == task and card.stage == "champion"
        ]
        if len(champions) > 1:
            raise MLOpsRegistryError(f"multiple champions for task {task}")
        return champions[0] if champions else None
