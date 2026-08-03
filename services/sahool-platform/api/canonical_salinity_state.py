"""Canonical soil/water salinity state and leaching-safety reconciliation.

This module does not replace laboratory measurements or the FAO-56 leaching
kernel.  It reconciles immutable evidence for one tenant/field/season and
fails closed when drainage, crop tolerance, or evidence freshness is
insufficient for an operational recommendation.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.salinity_management import (
    classify_soil_salinity,
    classify_water_salinity,
    leaching_requirement,
    sodium_hazard,
)

_HEX = set("0123456789abcdef")
_ALLOWED_DRAINAGE = {"good", "moderate", "poor", "unknown"}
_ALLOWED_STAGES = {"initial", "development", "mid", "late", "unknown"}


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _finite_nonnegative(value: float | None, name: str) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be finite and non-negative")


def _digest(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class SoilSalinityEvidence:
    ece_dsm: float
    sampled_at: datetime
    evidence_digest: str
    depth_cm: float | None = None


@dataclass(frozen=True)
class WaterQualityEvidence:
    ecw_dsm: float
    sampled_at: datetime
    evidence_digest: str
    sar: float | None = None
    rsc_meq_l: float | None = None
    chloride_mg_l: float | None = None
    boron_mg_l: float | None = None


@dataclass(frozen=True)
class DrainageEvidence:
    drainage_class: str
    assessed_at: datetime
    evidence_digest: str
    water_table_depth_m: float | None = None


@dataclass(frozen=True)
class CropSalinityTolerance:
    threshold_ece_dsm: float
    yield_decline_pct_per_dsm: float
    evidence_digest: str
    stage_tolerance_factor: float | None = None
    chloride_threshold_mg_l: float | None = None
    boron_threshold_mg_l: float | None = None


@dataclass(frozen=True)
class CanonicalSalinityState:
    tenant_id: str
    field_id: str
    season_id: str
    crop_id: str
    cultivar_id: str | None
    phenology_stage: str
    as_of: datetime
    status: str
    soil_class: str | None
    water_risk: str | None
    sodium_hazard_class: str | None
    rsc_hazard_class: str | None
    effective_crop_threshold_ece_dsm: float | None
    estimated_relative_yield: float | None
    leaching_fraction: float | None
    leaching_feasible: bool | None
    drainage_class: str
    operational_recommendation_allowed: bool
    limitations: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    state_digest: str


def _rsc_class(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1.25:
        return "low"
    if value <= 2.5:
        return "moderate"
    return "high"


def _fresh(sampled_at: datetime, as_of: datetime, max_age_days: int) -> bool:
    return timedelta(0) <= as_of - sampled_at <= timedelta(days=max_age_days)


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_canonical_salinity_state(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    crop_id: str,
    cultivar_id: str | None,
    phenology_stage: str,
    as_of: datetime,
    soil: SoilSalinityEvidence | None,
    water: WaterQualityEvidence | None,
    drainage: DrainageEvidence | None,
    tolerance: CropSalinityTolerance | None,
    max_soil_age_days: int = 730,
    max_water_age_days: int = 365,
    max_drainage_age_days: int = 1095,
) -> CanonicalSalinityState:
    """Reconcile salinity evidence without fabricating missing thresholds.

    An operational leaching recommendation is allowed only when current water
    quality, crop tolerance and non-poor drainage evidence are all present.
    """
    as_of = _aware(as_of, "as_of")
    if not all((tenant_id, field_id, season_id, crop_id)):
        raise ValueError("tenant_id, field_id, season_id and crop_id are required")
    if phenology_stage not in _ALLOWED_STAGES:
        raise ValueError("unknown phenology_stage")
    for value, name in (
        (max_soil_age_days, "max_soil_age_days"),
        (max_water_age_days, "max_water_age_days"),
        (max_drainage_age_days, "max_drainage_age_days"),
    ):
        if value < 1:
            raise ValueError(f"{name} must be positive")

    limitations: list[str] = []
    digests: list[str] = []
    soil_class = water_risk = sodium_class = rsc_class = None
    drainage_class = "unknown"
    effective_threshold = relative_yield = leaching_fraction = None
    leaching_feasible: bool | None = None

    if soil is None:
        limitations.append("MISSING_SOIL_SALINITY_EVIDENCE")
    else:
        _finite_nonnegative(soil.ece_dsm, "soil.ece_dsm")
        _finite_nonnegative(soil.depth_cm, "soil.depth_cm")
        sampled = _aware(soil.sampled_at, "soil.sampled_at")
        _digest(soil.evidence_digest, "soil.evidence_digest")
        digests.append(soil.evidence_digest)
        soil_class = classify_soil_salinity(soil.ece_dsm)["class"]
        if not _fresh(sampled, as_of, max_soil_age_days):
            limitations.append("STALE_SOIL_SALINITY_EVIDENCE")

    if water is None:
        limitations.append("MISSING_IRRIGATION_WATER_QUALITY")
    else:
        for value, name in (
            (water.ecw_dsm, "water.ecw_dsm"),
            (water.sar, "water.sar"),
            (water.rsc_meq_l, "water.rsc_meq_l"),
            (water.chloride_mg_l, "water.chloride_mg_l"),
            (water.boron_mg_l, "water.boron_mg_l"),
        ):
            _finite_nonnegative(value, name)
        sampled = _aware(water.sampled_at, "water.sampled_at")
        _digest(water.evidence_digest, "water.evidence_digest")
        digests.append(water.evidence_digest)
        water_risk = classify_water_salinity(water.ecw_dsm)["risk"]
        sodium_class = sodium_hazard(water.sar)["class"] if water.sar is not None else None
        rsc_class = _rsc_class(water.rsc_meq_l)
        if not _fresh(sampled, as_of, max_water_age_days):
            limitations.append("STALE_IRRIGATION_WATER_QUALITY")

    if drainage is None:
        limitations.append("MISSING_DRAINAGE_EVIDENCE")
    else:
        if drainage.drainage_class not in _ALLOWED_DRAINAGE:
            raise ValueError("unknown drainage_class")
        _finite_nonnegative(drainage.water_table_depth_m, "drainage.water_table_depth_m")
        assessed = _aware(drainage.assessed_at, "drainage.assessed_at")
        _digest(drainage.evidence_digest, "drainage.evidence_digest")
        digests.append(drainage.evidence_digest)
        drainage_class = drainage.drainage_class
        if not _fresh(assessed, as_of, max_drainage_age_days):
            limitations.append("STALE_DRAINAGE_EVIDENCE")
        if drainage_class == "poor":
            limitations.append("POOR_DRAINAGE_BLOCKS_LEACHING")
        elif drainage_class == "unknown":
            limitations.append("UNKNOWN_DRAINAGE_CLASS")

    if tolerance is None:
        limitations.append("MISSING_CROP_SALINITY_TOLERANCE")
    else:
        for value, name in (
            (tolerance.threshold_ece_dsm, "tolerance.threshold_ece_dsm"),
            (tolerance.yield_decline_pct_per_dsm, "tolerance.yield_decline_pct_per_dsm"),
            (tolerance.stage_tolerance_factor, "tolerance.stage_tolerance_factor"),
            (tolerance.chloride_threshold_mg_l, "tolerance.chloride_threshold_mg_l"),
            (tolerance.boron_threshold_mg_l, "tolerance.boron_threshold_mg_l"),
        ):
            _finite_nonnegative(value, name)
        if tolerance.threshold_ece_dsm <= 0 or tolerance.yield_decline_pct_per_dsm <= 0:
            raise ValueError("crop salinity threshold and yield decline must be positive")
        _digest(tolerance.evidence_digest, "tolerance.evidence_digest")
        digests.append(tolerance.evidence_digest)
        factor = tolerance.stage_tolerance_factor
        if factor is None:
            factor = 1.0
            limitations.append("STAGE_SPECIFIC_TOLERANCE_UNAVAILABLE")
        if factor <= 0:
            raise ValueError("stage_tolerance_factor must be positive")
        effective_threshold = tolerance.threshold_ece_dsm * factor
        if soil is not None:
            excess = max(0.0, soil.ece_dsm - effective_threshold)
            relative_yield = max(0.0, 1.0 - excess * tolerance.yield_decline_pct_per_dsm / 100.0)
        if water is not None:
            lr = leaching_requirement(water.ecw_dsm, effective_threshold)
            leaching_feasible = bool(lr.get("feasible"))
            leaching_fraction = lr.get("leaching_fraction") if leaching_feasible else None
            if not leaching_feasible:
                limitations.append("LEACHING_FORMULA_NOT_FEASIBLE")
            if water.chloride_mg_l is not None:
                if tolerance.chloride_threshold_mg_l is None:
                    limitations.append("CHLORIDE_THRESHOLD_UNAVAILABLE")
                elif water.chloride_mg_l > tolerance.chloride_threshold_mg_l:
                    limitations.append("CHLORIDE_EXCEEDS_CROP_THRESHOLD")
            if water.boron_mg_l is not None:
                if tolerance.boron_threshold_mg_l is None:
                    limitations.append("BORON_THRESHOLD_UNAVAILABLE")
                elif water.boron_mg_l > tolerance.boron_threshold_mg_l:
                    limitations.append("BORON_EXCEEDS_CROP_THRESHOLD")

    stale = any(item.startswith("STALE_") for item in limitations)
    operational_allowed = bool(
        water is not None
        and tolerance is not None
        and drainage is not None
        and drainage_class in {"good", "moderate"}
        and leaching_feasible
        and not stale
    )
    severe = (
        soil_class in {"strongly_saline", "very_strongly_saline"}
        or water_risk == "severe"
        or sodium_class in {"high", "very_high"}
        or rsc_class == "high"
        or "CHLORIDE_EXCEEDS_CROP_THRESHOLD" in limitations
        or "BORON_EXCEEDS_CROP_THRESHOLD" in limitations
    )
    if not operational_allowed:
        status = "blocked"
    elif severe:
        status = "high_risk"
    elif limitations:
        status = "managed_with_limitations"
    else:
        status = "managed"

    evidence = tuple(sorted(set(digests)))
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "crop_id": crop_id,
        "cultivar_id": cultivar_id,
        "phenology_stage": phenology_stage,
        "as_of": as_of.isoformat(),
        "status": status,
        "soil_class": soil_class,
        "water_risk": water_risk,
        "sodium_hazard_class": sodium_class,
        "rsc_hazard_class": rsc_class,
        "effective_crop_threshold_ece_dsm": effective_threshold,
        "estimated_relative_yield": relative_yield,
        "leaching_fraction": leaching_fraction,
        "leaching_feasible": leaching_feasible,
        "drainage_class": drainage_class,
        "operational_recommendation_allowed": operational_allowed,
        "limitations": sorted(set(limitations)),
        "evidence_digests": evidence,
    }
    state_digest = _hash_payload(payload)
    payload["limitations"] = tuple(payload["limitations"])
    return CanonicalSalinityState(**payload, state_digest=state_digest)
