"""Decision firewall for Canonical Field State inputs.

The firewall accepts verified field signals and reference annotations. Only
verified, non-annotation signals are allowed into recommendation inputs. RAG and
Knowledge Graph context is preserved for explanation, citations, and review but
cannot become a governing input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class InsufficientEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSignal:
    name: str
    value: Any
    source: str
    verified: bool
    governing: bool = False
    annotation_only: bool = False


@dataclass(frozen=True)
class CanonicalFieldStateFirewall:
    field_id: str
    signals: list[FieldSignal] = field(default_factory=list)
    annotations: list[FieldSignal] = field(default_factory=list)

    def recommendation_inputs(self) -> dict[str, Any]:
        """Return only verified signals; never RAG/KG annotations."""
        return {s.name: s.value for s in self.signals if s.verified and not s.annotation_only}

    def require(self, *names: str) -> None:
        available = self.recommendation_inputs()
        missing = [name for name in names if name not in available]
        if missing:
            raise InsufficientEvidenceError(
                f"Missing verified field-state inputs: {', '.join(missing)}"
            )

    def add_signal(self, signal: FieldSignal) -> CanonicalFieldStateFirewall:
        if signal.annotation_only:
            return CanonicalFieldStateFirewall(
                self.field_id, self.signals, [*self.annotations, signal]
            )
        return CanonicalFieldStateFirewall(self.field_id, [*self.signals, signal], self.annotations)


def from_context_bundle(bundle: Any) -> CanonicalFieldStateFirewall:
    """Build the firewall from a FieldContextBundle without importing it strictly."""
    fw = CanonicalFieldStateFirewall(field_id=bundle.field_id)
    for sig in getattr(bundle, "signals", []):
        fw = fw.add_signal(
            FieldSignal(
                name=str(sig.payload.get("name") or sig.kind),
                value=sig.payload.get("value", sig.payload),
                source=sig.source,
                verified=bool(sig.verified),
                governing=bool(sig.governing),
                annotation_only=False,
            )
        )
    for ann in getattr(bundle, "annotations", []):
        fw = fw.add_signal(
            FieldSignal(
                name=str(ann.payload.get("name") or ann.kind),
                value=ann.payload,
                source=ann.source,
                verified=False,
                governing=False,
                annotation_only=True,
            )
        )
    return fw
