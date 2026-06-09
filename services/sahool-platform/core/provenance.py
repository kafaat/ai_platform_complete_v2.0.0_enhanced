"""
sahool_core.provenance
=======================
Makes the INFORMATION_PROVENANCE.md constitution EXECUTABLE.

Every piece of information produced by SAHOOL is wrapped in a Provenance
record that answers, for each value:
  - where did it come from?       (source)
  - what is its ground truth?     (ground_truth)
  - what is its error margin?     (error)
  - how is it verified?           (verification)
  - what stage produced it?       (stage: raw/derived/fused/decision)
  - is it calibrated?             (status)

The golden rule is enforced in code: confidence of a derived/fused value
is bounded by the WEAKEST input (largest relative error). Nothing can claim
higher confidence than its shakiest source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Stage(str, Enum):
    RAW = "raw"  # direct measurement
    DERIVED = "derived"  # equation on raw
    FUSED = "fused"  # weighted multi-source
    DECISION = "decision"  # rules + calibration


class Status(str, Enum):
    CALIBRATED = "calibrated"  # validated against ground truth
    PHYSICS = "physics"  # established equation, no calibration needed
    PENDING = "pending_calibration"  # awaits ground truth — NO fake number
    INSUFFICIENT = "insufficient_data"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def confidence_from_error(relative_error: float) -> Confidence:
    """Map a relative error to a confidence category (never a fake %)."""
    if relative_error < 0:
        return Confidence.UNKNOWN
    if relative_error <= 0.10:
        return Confidence.HIGH
    if relative_error <= 0.25:
        return Confidence.MEDIUM
    return Confidence.LOW


@dataclass
class Provenance:
    """The lineage record attached to every information value."""

    name: str  # what this is (e.g. "ET0", "suitability")
    value: Any  # the value (or None if pending)
    unit: str
    stage: Stage
    status: Status
    source: str  # measurement source / equation
    ground_truth: str  # what the reference truth is
    error: float  # relative error (e.g. 0.10 = ±10%); -1 unknown
    verification: str  # how to verify later
    inputs: list[Provenance] = field(default_factory=list)
    citation: str = ""  # literature source

    @property
    def confidence(self) -> Confidence:
        """Golden rule: bounded by the weakest input."""
        own = confidence_from_error(self.error)
        if not self.inputs:
            return own
        # weakest link across self + all inputs
        worst_err = max(
            [self.error if self.error >= 0 else 1.0]
            + [i.error if i.error >= 0 else 1.0 for i in self.inputs]
        )
        return confidence_from_error(worst_err)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "stage": self.stage.value,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "source": self.source,
            "ground_truth": self.ground_truth,
            "error": self.error,
            "verification": self.verification,
            "citation": self.citation,
            "inputs": [i.name for i in self.inputs],
        }

    def explain_ar(self) -> str:
        """Human-readable Arabic lineage line."""
        if self.value is None or self.status == Status.PENDING:
            return f"{self.name}: قيد المعايرة (لا رقم — ينتظر {self.ground_truth})"
        err_txt = f"±{self.error * 100:.0f}%" if self.error >= 0 else "غير معروف"
        return (
            f"{self.name} = {self.value} {self.unit} | "
            f"ثقة: {self.confidence.value} | خطأ: {err_txt} | "
            f"مصدر: {self.source} | حقيقة: {self.ground_truth}"
        )


# ── Error propagation helpers (enforce the rules in code) ────────────
def propagate_multiply(a: Provenance, b: Provenance) -> float:
    """Relative errors add in quadrature for z = a*b."""
    ea = a.error if a.error >= 0 else 0.0
    eb = b.error if b.error >= 0 else 0.0
    return (ea**2 + eb**2) ** 0.5


def propagate_add(values_errors: list[tuple[float, float]]) -> float:
    """Absolute errors add in quadrature for z = x+y+...; returns abs error."""
    return sum(e**2 for _, e in values_errors) ** 0.5


# ── Factory for a "pending" value (the honest default) ───────────────
def pending(name: str, unit: str, ground_truth: str, verification: str = "") -> Provenance:
    return Provenance(
        name=name,
        value=None,
        unit=unit,
        stage=Stage.DECISION,
        status=Status.PENDING,
        source="—",
        ground_truth=ground_truth,
        error=-1.0,
        verification=verification or f"يتطلب {ground_truth}",
    )
