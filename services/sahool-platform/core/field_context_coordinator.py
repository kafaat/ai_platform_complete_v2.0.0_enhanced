"""Field Context Coordinator — not a decision maker.

The coordinator discovers or receives tool results and normalizes them into
context annotations. It is intentionally prevented from emitting recommendations,
prescriptions, or tasks. The only legal next step is compose_field_state or an
existing Canonical Field State gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ContextKind = Literal["weather", "lab", "satellite", "iot", "operations", "rag", "kg"]


@dataclass(frozen=True)
class ContextSignal:
    source: str
    kind: ContextKind
    payload: dict[str, Any]
    verified: bool = False
    governing: bool = False
    annotation_only: bool = False


@dataclass(frozen=True)
class FieldContextBundle:
    field_id: str
    signals: list[ContextSignal] = field(default_factory=list)
    annotations: list[ContextSignal] = field(default_factory=list)

    @property
    def recommendation(self) -> None:
        raise AttributeError("FieldContextCoordinator must not emit recommendations")

    @property
    def prescription(self) -> None:
        raise AttributeError("FieldContextCoordinator must not emit prescriptions")


def normalize_tool_result(
    field_id: str, source: str, kind: ContextKind, payload: dict[str, Any]
) -> ContextSignal:
    """Normalize one tool result into a Signal or annotation.

    RAG and KG are reference-only annotations by design. Lab/weather/IoT may be
    verified decision inputs when upstream provenance says so.
    """
    annotation = kind in {"rag", "kg"}
    if annotation:
        return ContextSignal(
            source=source,
            kind=kind,
            payload={**payload, "field_id": field_id},
            verified=False,
            governing=False,
            annotation_only=True,
        )
    verified = bool(payload.get("verified"))
    governing = kind == "lab" and verified
    return ContextSignal(
        source=source,
        kind=kind,
        payload={**payload, "field_id": field_id},
        verified=verified,
        governing=governing,
        annotation_only=False,
    )


class FieldContextCoordinator:
    """Assemble context from MCP/RAG/KG outputs without deciding."""

    def assemble(self, field_id: str, tool_results: list[dict[str, Any]]) -> FieldContextBundle:
        signals: list[ContextSignal] = []
        annotations: list[ContextSignal] = []
        for row in tool_results:
            sig = normalize_tool_result(
                field_id=field_id,
                source=str(row.get("source") or row.get("server") or "unknown"),
                kind=row.get("kind", "rag"),
                payload=dict(row.get("payload") or row.get("result") or {}),
            )
            if sig.annotation_only:
                annotations.append(sig)
            else:
                signals.append(sig)
        return FieldContextBundle(field_id=field_id, signals=signals, annotations=annotations)


def recommendation_inputs(bundle: FieldContextBundle) -> list[ContextSignal]:
    """Return only verified, non-annotation signals allowed into decisions.

    RAG/KG annotations are intentionally excluded even when present.
    """
    allowed: list[ContextSignal] = []
    for sig in bundle.signals:
        if sig.annotation_only or sig.kind in {"rag", "kg"}:
            continue
        if sig.verified:
            allowed.append(sig)
    return allowed
