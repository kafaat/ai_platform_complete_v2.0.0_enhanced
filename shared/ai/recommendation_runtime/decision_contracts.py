"""
Decision authority contracts for SAHOOL.

This module intentionally validates STRUCTURED KEYS only. It does not scan free text,
so phrases such as "no recommendation available" in notes do not cause false positives.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DecisionContractViolation(Exception):
    """Raised when a non-authoritative layer emits a decision-shaped key."""


FORBIDDEN_DECISION_KEYS: frozenset[str] = frozenset(
    {
        "recommendation",
        "recommendations",
        "prescription",
        "prescriptions",
        "task",
        "tasks",
        "dose",
        "fertilizer_rate",
        "irrigation_schedule",
        "pesticide_application",
        "seed_rate",
    }
)


def iter_structured_keys(obj: Any) -> Iterable[str]:
    """Yield dictionary keys recursively from JSON-like data structures only."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key).lower()
            yield from iter_structured_keys(value)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            yield from iter_structured_keys(item)


def assert_no_decision_keys(obj: Any, *, layer: str = "unknown") -> None:
    """Fail if a non-decision layer emits decision-shaped structured keys."""
    found = sorted(set(iter_structured_keys(obj)).intersection(FORBIDDEN_DECISION_KEYS))
    if found:
        raise DecisionContractViolation(
            f"{layer} emitted forbidden decision keys {found}. "
            "Only RecommendationEngine may emit recommendations, prescriptions, tasks, or rates."
        )


def has_decision_keys(obj: Any) -> bool:
    """Return True if structured output contains a forbidden decision key."""
    return bool(set(iter_structured_keys(obj)).intersection(FORBIDDEN_DECISION_KEYS))


class EvidenceStrength(str, Enum):
    LAB = "lab"
    IOT = "iot"
    WEATHER = "weather"
    SATELLITE = "satellite"
    RAG = "rag"
    KG = "kg"


EVIDENCE_WEIGHTS: dict[EvidenceStrength, float] = {
    EvidenceStrength.LAB: 1.00,
    EvidenceStrength.IOT: 0.90,
    EvidenceStrength.WEATHER: 0.85,
    EvidenceStrength.SATELLITE: 0.60,
    EvidenceStrength.RAG: 0.25,
    EvidenceStrength.KG: 0.20,
}


@dataclass(frozen=True)
class EvidenceItem:
    source: EvidenceStrength
    confidence: float
    verified: bool = False


def compose_confidence(items: list[EvidenceItem]) -> float:
    """Weighted confidence composer. RAG/KG cannot dominate governing evidence."""
    if not items:
        return 0.0
    total_weight = 0.0
    weighted = 0.0
    for item in items:
        weight = EVIDENCE_WEIGHTS[item.source]
        if item.source in (EvidenceStrength.RAG, EvidenceStrength.KG) and not item.verified:
            weight *= 0.5
        weighted += max(0.0, min(1.0, item.confidence)) * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return round(weighted / total_weight, 4)


def recommendation_inputs_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return decision inputs while treating RAG/KG as annotations only."""
    signals = context.get("signals", {}) if isinstance(context, dict) else {}
    if not isinstance(signals, dict):
        return {}
    allowed = {"lab", "iot", "weather", "satellite", "field_state", "operations"}
    return {k: v for k, v in signals.items() if k in allowed}
