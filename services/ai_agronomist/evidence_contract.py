"""NDVI-grid evidence contract + machine-readiness gate (V62.3).

Two pure, deterministic pieces that productionise raster evidence before it can anchor a
variable-rate (VRA) prescription or any machine export:

1. ``build_ndvi_grid_evidence`` — normalises whatever the raster tier carries into ONE
   canonical evidence object (grid + quality + provenance). It never fabricates: an absent
   metric becomes ``None`` (and quality_flags an empty list), so a consumer can always tell
   "unknown" from "measured".

2. ``evaluate_machine_readiness`` — a **fail-closed** completeness gate. Machine export /
   VRA execution requires enough valid pixels AND enough field coverage; missing metrics ⇒
   NOT machine-ready (never assume quality we can't see). Cloud and staleness are warnings
   (advisory), and zones seeded from geometry-only fallback can never anchor machine export.

This module has no I/O and no service deps beyond the pure zoning-provenance helper, so it
runs in the unit tier. Populating the quality metrics at raster ingest and plumbing the grid
into the AI pack are the follow-up slices (v62.3-B/C); this slice makes the contract + gate
exist and fail-closed first.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

try:  # pragma: no cover - trivial import shim (mirrors vra_prescription_engine)
    from .runtime_evidence import zoning_is_evidence_backed
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.runtime_evidence import (  # type: ignore
        zoning_is_evidence_backed,
    )

# ── fail-closed thresholds for machine readiness (VRA / machine export) ──
MIN_VALID_PIXEL_RATIO = 0.7  # below ⇒ blocking (too many masked/nodata pixels)
MIN_COVERAGE_RATIO = 0.75  # below ⇒ blocking (scene does not cover enough of the field)
MAX_CLOUD_COVER = 0.35  # above ⇒ warning (advisory, not blocking)
MAX_SCENE_AGE_DAYS = 14  # older ⇒ warning (stale evidence; aligns with evidence_policy)
PIPELINE_VERSION = "v62.3"


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _ratio(value: Any) -> float | None:
    """A metric expected in [0,1]; clamps to bounds, rejects non-finite/non-numeric."""
    out = _num(value)
    if out is None:
        return None
    return max(0.0, min(out, 1.0))


def _iso_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_grid(grid: Any) -> dict[str, Any] | None:
    """Accepts a 2D list ``[[..],[..]]`` or a ``{width,height,values}`` dict; returns the
    canonical ``{width,height,values}`` or None when no usable grid is present."""
    values: Any = None
    if isinstance(grid, dict):
        values = grid.get("values")
    elif isinstance(grid, list):
        values = grid
    if not isinstance(values, list) or not values:
        return None
    rows = [r for r in values if isinstance(r, list)]
    if not rows:
        return None
    return {"width": len(rows[0]), "height": len(rows), "values": rows}


def build_ndvi_grid_evidence(
    *,
    field_id: Any = None,
    tenant_id: Any = None,
    source: Any = None,
    index: Any = "ndvi",
    scene_id: Any = None,
    acquisition_date: Any = None,
    grid: Any = None,
    cloud_cover: Any = None,
    valid_pixel_ratio: Any = None,
    coverage_ratio: Any = None,
    source_resolution_m: Any = None,
    quality_flags: Any = None,
    asset_id: Any = None,
    computed_at: Any = None,
    pipeline_version: Any = PIPELINE_VERSION,
) -> dict[str, Any]:
    """Normalise raster evidence into the canonical v62.3 contract object.

    Never fabricates: unknown numeric metrics → None, unknown flags → []. ``cloud_cover`` is
    a ratio in [0,1] (convert cloud_pct/100 at the caller); values are clamped, not guessed.
    """
    return {
        "field_id": str(field_id) if field_id is not None else None,
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "source": str(source) if source else None,
        "scene_id": str(scene_id) if scene_id else None,
        "acquisition_date": _iso_date(acquisition_date),
        "index": str(index or "ndvi"),
        "grid": _normalize_grid(grid),
        "quality": {
            "cloud_cover": _ratio(cloud_cover),
            "valid_pixel_ratio": _ratio(valid_pixel_ratio),
            "coverage_ratio": _ratio(coverage_ratio),
            "source_resolution_m": _num(source_resolution_m),
            "quality_flags": list(quality_flags) if isinstance(quality_flags, list) else [],
        },
        "provenance": {
            "asset_id": str(asset_id) if asset_id else None,
            "pipeline_version": str(pipeline_version or PIPELINE_VERSION),
            "computed_at": _iso_datetime(computed_at),
        },
    }


def _scene_age_days(acquisition_date: Any, now: Any = None) -> int | None:
    """Whole days between the scene's acquisition date and ``now`` (default: today, UTC).
    Returns None when the acquisition date is missing/unparseable (⇒ unknown age)."""
    acq: date | None = None
    if isinstance(acquisition_date, datetime):
        acq = acquisition_date.date()
    elif isinstance(acquisition_date, date):
        acq = acquisition_date
    elif isinstance(acquisition_date, str) and acquisition_date.strip():
        try:
            acq = date.fromisoformat(acquisition_date.strip()[:10])
        except ValueError:
            acq = None
    if acq is None:
        return None
    if isinstance(now, datetime):
        today = now.date()
    elif isinstance(now, date):
        today = now
    else:
        today = datetime.now(UTC).date()
    return (today - acq).days


def evaluate_machine_readiness(
    evidence: dict[str, Any] | None,
    *,
    zoning_method: str | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Fail-closed gate: is this evidence strong enough to anchor VRA / machine export?

    Blocking (⇒ not machine-ready): valid_pixel_ratio missing or < 0.7; coverage_ratio
    missing or < 0.75; zones seeded from geometry-only fallback. Advisory warnings: cloud
    cover > 0.35; scene older than 14 days; unknown scene age. Missing metrics block (we
    never assume unseen quality).
    """
    quality = (evidence or {}).get("quality") if isinstance(evidence, dict) else None
    quality = quality if isinstance(quality, dict) else {}
    vpr = _ratio(quality.get("valid_pixel_ratio"))
    cov = _ratio(quality.get("coverage_ratio"))
    cloud = _ratio(quality.get("cloud_cover"))

    blocking: list[str] = []
    warnings: list[str] = []

    if vpr is None:
        blocking.append("missing_valid_pixel_ratio")
    elif vpr < MIN_VALID_PIXEL_RATIO:
        blocking.append("valid_pixel_ratio_below_min")
    if cov is None:
        blocking.append("missing_coverage_ratio")
    elif cov < MIN_COVERAGE_RATIO:
        blocking.append("coverage_ratio_below_min")

    if cloud is not None and cloud > MAX_CLOUD_COVER:
        warnings.append("high_cloud_cover")

    age = _scene_age_days((evidence or {}).get("acquisition_date"), now)
    if age is None:
        warnings.append("unknown_scene_age")
    elif age > MAX_SCENE_AGE_DAYS:
        warnings.append("stale_scene")

    # geometry-only zones can never anchor machine export (no real index evidence).
    if zoning_method is not None and not zoning_is_evidence_backed(zoning_method):
        blocking.append("geometry_fallback_zoning_not_machine_exportable")

    return {
        "machine_ready": not blocking,
        "blocking_reasons": blocking,
        "warnings": warnings,
        "observed": {
            "valid_pixel_ratio": vpr,
            "coverage_ratio": cov,
            "cloud_cover": cloud,
            "scene_age_days": age,
        },
        "thresholds": {
            "min_valid_pixel_ratio": MIN_VALID_PIXEL_RATIO,
            "min_coverage_ratio": MIN_COVERAGE_RATIO,
            "max_cloud_cover": MAX_CLOUD_COVER,
            "max_scene_age_days": MAX_SCENE_AGE_DAYS,
        },
    }
