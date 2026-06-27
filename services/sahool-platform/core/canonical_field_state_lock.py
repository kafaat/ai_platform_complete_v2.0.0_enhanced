"""Canonical Field State lock and decision firewall.

The goal is to make the Source of Truth explicit. Services may emit observations,
signals, or annotations. Only verified agronomic signals enter recommendation
inputs. RAG/KG annotations are stored for explanation but excluded from governing
calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SignalKind = Literal["weather", "satellite", "lab", "iot", "operations"]
AnnotationKind = Literal["rag", "kg"]


class DecisionFirewallError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSignal:
    name: str
    kind: SignalKind
    value: Any
    verified: bool
    evidence_class: Literal["indication", "evidence", "governing", "modifying"]
    source: str

    def __post_init__(self) -> None:
        forbidden = {"recommendation", "prescription", "decision", "task"}
        if isinstance(self.value, dict) and forbidden.intersection(self.value):
            raise DecisionFirewallError("Signal payload must not contain decision fields")


@dataclass(frozen=True)
class FieldAnnotation:
    name: str
    kind: AnnotationKind
    value: Any
    source: str
    verified: bool = False

    def __post_init__(self) -> None:
        if self.verified:
            raise DecisionFirewallError("RAG/KG annotations cannot be verified decision evidence")


@dataclass
class CanonicalFieldState:
    field_id: str
    tenant_id: str
    signals: list[FieldSignal] = field(default_factory=list)
    annotations: list[FieldAnnotation] = field(default_factory=list)
    lifecycle: str = "limited"

    def add_signal(self, signal: FieldSignal) -> None:
        self.signals.append(signal)

    def add_annotation(self, annotation: FieldAnnotation) -> None:
        self.annotations.append(annotation)

    @property
    def recommendation_inputs(self) -> dict[str, Any]:
        """Verified non-RAG/KG inputs allowed to influence Recommendation Engine."""
        out: dict[str, Any] = {}
        for signal in self.signals:
            if signal.verified and signal.evidence_class in {"evidence", "governing", "modifying"}:
                out[signal.name] = signal.value
        return out

    @property
    def explanatory_annotations(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name,
                "kind": a.kind,
                "source": a.source,
                "value": a.value,
                "verified": False,
            }
            for a in self.annotations
        ]


def compose_locked_field_state(
    *,
    field_id: str,
    tenant_id: str,
    signals: list[FieldSignal] | None = None,
    annotations: list[FieldAnnotation] | None = None,
    lifecycle: str = "limited",
) -> CanonicalFieldState:
    state = CanonicalFieldState(field_id=field_id, tenant_id=tenant_id, lifecycle=lifecycle)
    for signal in signals or []:
        state.add_signal(signal)
    for annotation in annotations or []:
        state.add_annotation(annotation)
    return state
