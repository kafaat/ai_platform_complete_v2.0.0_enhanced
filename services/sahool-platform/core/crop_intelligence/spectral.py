from __future__ import annotations

import math
from typing import Any

from core.engines.spectral_stress_bridge import fuse_water_stress, spectral_confirmation_eligible

_SCHEMA = "canonical_spectral_state.v1"
_PRODUCT_VERSION = "crop-spectral-adapter/1.1.0"
_CONFIRMATION_QUALITIES = frozenset({"validated"})
_STRESS_SIGNALS = {"moderate", "severe"}


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def build_canonical_spectral_state(
    *,
    ndvi: float | None = None,
    ndre: float | None = None,
    ndmi: float | None = None,
    msi: float | None = None,
    acquisition_date: str | None = None,
    product_ids: list[str] | None = None,
    quality_status: str | None = None,
    temporal_compatible: bool | None = None,
    index_provenance: dict[str, dict[str, Any]] | None = None,
    source_authority: str | None = None,
) -> dict[str, Any]:
    """Project validated spectral products into a crop-facing read model.

    This adapter never computes raster indices. It only interprets already-computed
    values and preserves their evidence/provenance for Crop Intelligence.
    """
    vals = {
        "ndvi": _finite(ndvi),
        "ndre": _finite(ndre),
        "ndmi": _finite(ndmi),
        "msi": _finite(msi),
    }
    # Finite is necessary, but does not make an index or its quality valid.
    for name in ("ndvi", "ndre", "ndmi"):
        if vals[name] is not None and not -1.0 <= vals[name] <= 1.0:
            vals[name] = None
    if vals["msi"] is not None and vals["msi"] < 0.0:
        vals["msi"] = None
    missing = [name for name, value in vals.items() if value is None]
    quality = quality_status if isinstance(quality_status, str) else "unknown"
    quality_eligible = quality in _CONFIRMATION_QUALITIES
    water_confirmation_available = spectral_confirmation_eligible(
        vals["ndmi"],
        vals["msi"],
        quality_status=quality,
        temporal_compatible=temporal_compatible,
    )

    fused = None
    if water_confirmation_available:
        fused = fuse_water_stress(vals["ndmi"], vals["msi"])

    if not any(value is not None for value in vals.values()):
        availability = "unavailable"
    elif quality in {"invalid", "insufficient", "unavailable"}:
        availability = "unavailable"
    elif quality_eligible:
        availability = "available"
    else:
        # Source authority, missing quality and estimated values are not validation.
        availability = "degraded"

    limitations: list[str] = []
    if not quality_eligible:
        limitations.append("spectral_quality_not_eligible_for_confirmation")
    if vals["ndmi"] is not None and vals["msi"] is not None and temporal_compatible is not True:
        limitations.append("ndmi_msi_temporal_compatibility_not_verified")
    if not water_confirmation_available:
        limitations.append("spectral_water_confirmation_unavailable")

    return {
        "schema": _SCHEMA,
        "product_version": _PRODUCT_VERSION,
        "status": availability,
        "indices": vals,
        "acquisition_date": acquisition_date,
        "water_stress": {
            "confirmation_available": water_confirmation_available,
            "confirmed": (fused["fused_signal"] in _STRESS_SIGNALS if fused is not None else None),
            "signal": fused["fused_signal"] if fused is not None else "unknown",
            "confidence": fused.get("confidence") if fused is not None else "none",
            "agreement": fused.get("agreement") if fused is not None else None,
            "temporal_compatible": temporal_compatible,
            "independent_evidence_count": (
                fused.get("independent_evidence_count", 0) if fused is not None else 0
            ),
        },
        "quality_status": quality,
        "source_authority": source_authority,
        "index_provenance": index_provenance or {},
        "evidence_ids": list(dict.fromkeys(product_ids or [])),
        "missing_indices": missing,
        "limitations": limitations,
        "ownership": {
            "index_computation": "raster-service",
            "spectral_interpretation": "vegetation-analysis-service/canonical-water-stress",
            "crop_response_interpretation": "crop-intelligence-engine",
        },
    }
