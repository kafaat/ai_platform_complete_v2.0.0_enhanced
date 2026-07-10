"""Validated indicator product contract for the consumer-facing grid response.

``raster_validated_product.py`` records the quality/provenance envelope of the
*raw pixel* QA step.  That envelope is computed but historically stayed inside an
internal ``stats`` dict and never reached the wire — the
``/v1/fields/{field_id}/indicator-grid`` response was a bare dict.

This module surfaces that envelope as a typed, honesty-checked
``ValidatedIndicatorProduct`` that rides alongside the existing grid contract
(under an ``indicator_product`` key) so consumers such as
vegetation-analysis-service can read provenance/quality instead of guessing from
``stats.mean`` + ``real_data`` alone.

Honesty invariants (enforced by validators, never bypassed):
  * ``source != "raster-service"``  ⇒  ``estimated`` MUST be True and
    ``quality_gate_passed`` MUST be False (a simulation can never claim a passed
    quality gate or non-estimated data).
  * ``real_data`` True requires ``source == "raster-service"``.
  * Provenance is never fabricated: if the source payload carries no provenance,
    ``provenance`` is None.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator
from raster_validated_product import ProvenanceRecord

RASTER_SOURCE = "raster-service"
SIMULATION_SOURCE = "simulation"


class IndicatorStats(BaseModel):
    """Min/max/mean summary of the (down-sampled) indicator grid."""

    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0


class ValidatedIndicatorProduct(BaseModel):
    """Typed provenance/quality envelope for an indicator-grid response.

    It mirrors the shape of ``ValidatedRasterProduct`` at the *indicator*
    (consumer) boundary: quality score, valid-pixel ratio, an explicit
    quality-gate flag, and an optional embedded ``ProvenanceRecord``.  Both the
    real (COG-backed) and the simulation branches emit this identical contract
    so the frontend/consumers see the same shape in both states.
    """

    schema: str = "sahool.validated_indicator_product/1"
    field_id: str
    index: str
    date: str
    stats: IndicatorStats = Field(default_factory=IndicatorStats)
    source: str = SIMULATION_SOURCE
    estimated: bool = True
    real_data: bool = False
    quality_score: float | None = None
    valid_pixel_ratio: float | None = None
    quality_gate_passed: bool = False
    provenance: ProvenanceRecord | None = None

    @model_validator(mode="after")
    def _enforce_honesty_invariants(self) -> ValidatedIndicatorProduct:
        if self.source != RASTER_SOURCE:
            if not self.estimated:
                raise ValueError(
                    "non-raster-service indicator product must be estimated=True "
                    f"(source={self.source!r})"
                )
            if self.quality_gate_passed:
                raise ValueError(
                    "non-raster-service indicator product cannot claim a passed quality gate "
                    f"(source={self.source!r})"
                )
        if self.real_data and self.source != RASTER_SOURCE:
            raise ValueError(
                f"real_data=True requires source={RASTER_SOURCE!r}, got {self.source!r}"
            )
        return self


def _coerce_stats(raw: Any) -> IndicatorStats:
    if isinstance(raw, IndicatorStats):
        return raw
    if isinstance(raw, dict):
        return IndicatorStats(
            min=float(raw.get("min", 0.0) or 0.0),
            max=float(raw.get("max", 0.0) or 0.0),
            mean=float(raw.get("mean", 0.0) or 0.0),
        )
    return IndicatorStats()


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):  # bool is a subclass of int — never a quality score
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_provenance(raw: Any) -> ProvenanceRecord | None:
    """Build a ProvenanceRecord only from real data; never fabricate one."""
    if raw is None:
        return None
    if isinstance(raw, ProvenanceRecord):
        return raw
    if isinstance(raw, dict):
        return ProvenanceRecord(**raw)
    return None


def from_grid_response(
    payload: dict[str, Any],
    *,
    quality_score: float | None = None,
    provenance: Any = None,
) -> dict[str, Any]:
    """Map an existing grid dict into a ``ValidatedIndicatorProduct`` json dump.

    ``source`` is derived honestly from ``real_data`` — a real COG-backed grid is
    labelled ``raster-service`` (non-estimated, quality gate passed); anything
    else is a ``simulation`` (estimated, quality gate not passed).  Provenance is
    taken only from what the payload/caller actually carries.
    """
    real = bool(payload.get("real_data"))
    src = RASTER_SOURCE if real else SIMULATION_SOURCE
    qscore = quality_score
    if qscore is None:
        qscore = _maybe_float(payload.get("quality_score"))
    if qscore is None:
        qscore = _maybe_float(payload.get("confidence"))
    prov = provenance if provenance is not None else payload.get("provenance")
    product = ValidatedIndicatorProduct(
        field_id=str(payload.get("field_id") or ""),
        index=str(payload.get("index") or ""),
        date=str(payload.get("date") or ""),
        stats=_coerce_stats(payload.get("stats")),
        source=src,
        estimated=not real,
        real_data=real,
        quality_score=qscore if real else None,
        valid_pixel_ratio=_maybe_float(payload.get("valid_pixel_ratio")) if real else None,
        quality_gate_passed=real,
        provenance=_coerce_provenance(prov) if real else None,
    )
    return product.model_dump(mode="json")


def from_validated_raster_product(
    *,
    field_id: str,
    index: str,
    date: str,
    stats: Any,
    validated_raster_product: dict[str, Any] | Any,
) -> dict[str, Any]:
    """Build the indicator envelope from a ValidatedRasterProduct (dict or model).

    This is the richest path: quality_score / valid_pixel_ratio / provenance come
    straight from the validated raster product's own QA envelope.
    """
    vrp = validated_raster_product
    if hasattr(vrp, "model_dump"):
        vrp = vrp.model_dump(mode="json")
    if not isinstance(vrp, dict):
        vrp = {}
    product = ValidatedIndicatorProduct(
        field_id=field_id,
        index=index,
        date=date,
        stats=_coerce_stats(stats),
        source=RASTER_SOURCE,
        estimated=False,
        real_data=True,
        quality_score=_maybe_float(vrp.get("quality_score")),
        valid_pixel_ratio=_maybe_float(vrp.get("valid_pixel_ratio")),
        quality_gate_passed=True,
        provenance=_coerce_provenance(vrp.get("provenance")),
    )
    return product.model_dump(mode="json")
