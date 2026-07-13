"""Canonical M2.2 root-zone hydraulic truth.

Combines a governed soil hydraulic profile with an explicit crop root policy.
No generic texture or root-depth fallback is eligible for operational control.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from core.crop_intelligence.roots import build_root_state

from api.soil_hydraulic_client import get_soil_hydraulic_profile

SCHEMA_VERSION = "canonical_root_zone_profile.v1"
PRODUCT_VERSION = "root-zone-hydraulics/1.0.0"
MAX_PROFILE_AGE_DAYS = 730.0


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _hydraulic_value(node: Any) -> tuple[float | None, str | None, float | None]:
    if not isinstance(node, dict):
        return None, None, None
    return (
        _number(node.get("value")),
        str(node.get("origin") or "unknown"),
        _number(node.get("confidence")),
    )


@dataclass(frozen=True)
class CanonicalRootZoneProfile:
    schema_version: str
    product_version: str
    tenant_id: str
    field_id: str
    season_id: str
    crop: str
    root_policy_id: str
    root_policy_version: str
    soil_hydraulic_profile_id: str
    source_soil_profile_hash: str
    generated_at: str
    effective_at: str
    root_depth_m: float
    effective_root_zone_m: float
    taw_mm: float
    raw_fraction: float
    raw_mm: float
    field_capacity_weighted: float
    wilting_point_weighted: float
    available_water_capacity_weighted: float
    infiltration_mm_h: float | None
    ksat_mm_h: float | None
    soil_ec_ds_m: float | None
    layer_contributions: list[dict[str, Any]]
    evidence: dict[str, Any]
    quality_status: str
    operational_eligible: bool
    limitations: list[str]
    profile_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_root_zone_profile(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    crop: str,
    phenology_progress: float | None,
    raw_fraction: float,
    root_policy: dict[str, Any],
    soil_profile: dict[str, Any],
    soil_ec_ds_m: float | None = None,
    now: datetime | None = None,
) -> CanonicalRootZoneProfile | dict[str, Any]:
    """Build the canonical profile or return a fail-closed blocked payload."""
    now = now or datetime.now(UTC)
    if not isinstance(soil_profile, dict) or not soil_profile.get("executable"):
        return {"status": "blocked", "reason": "soil_hydraulic_profile_not_executable"}
    layers = soil_profile.get("layers")
    if not isinstance(layers, list) or not layers:
        return {"status": "blocked", "reason": "soil_hydraulic_layers_missing"}

    root_state = build_root_state(
        phenology_progress=phenology_progress,
        initial_depth_m=root_policy.get("initial_depth_m"),
        maximum_depth_m=root_policy.get("maximum_depth_m"),
        effective_fraction=root_policy.get("effective_fraction", 0.8),
        policy_version=root_policy.get("policy_version"),
        source_ids=root_policy.get("evidence_ids") or [],
    )
    if root_state.get("status") != "available":
        return {"status": "blocked", "reason": "validated_root_policy_and_phenology_required"}

    p = _number(raw_fraction)
    if p is None or not 0 < p <= 1:
        return {"status": "blocked", "reason": "invalid_raw_fraction"}

    root_depth_m = float(root_state["current_depth_m"])
    root_depth_cm = root_depth_m * 100.0
    remaining_cm = root_depth_cm
    taw_mm = 0.0
    weighted_fc = 0.0
    weighted_wp = 0.0
    weighted_awc = 0.0
    total_depth_cm = 0.0
    contributions: list[dict[str, Any]] = []
    limitations: list[str] = []
    infiltration_candidates: list[float] = []
    ksat_candidates: list[float] = []
    measured_core = True

    for layer in sorted(layers, key=lambda x: float(x.get("depth_from_cm", 0))):
        if remaining_cm <= 0:
            break
        top = _number(layer.get("depth_from_cm"))
        bottom = _number(layer.get("depth_to_cm"))
        if top is None or bottom is None or bottom <= top:
            return {"status": "blocked", "reason": "invalid_soil_layer_geometry"}
        if top >= root_depth_cm:
            continue
        included_cm = min(bottom, root_depth_cm) - top
        if included_cm <= 0:
            continue

        fc, fc_origin, fc_conf = _hydraulic_value(layer.get("field_capacity"))
        wp, wp_origin, wp_conf = _hydraulic_value(layer.get("wilting_point"))
        cf, _, _ = _hydraulic_value(layer.get("coarse_fragments"))
        infiltration, inf_origin, inf_conf = _hydraulic_value(layer.get("infiltration"))
        ksat, ks_origin, ks_conf = _hydraulic_value(layer.get("ksat"))
        if fc is None or wp is None or not 0 <= wp < fc <= 0.8:
            return {"status": "blocked", "reason": "invalid_field_capacity_or_wilting_point"}
        coarse_fraction = max(0.0, min(0.95, (cf or 0.0) / 100.0))
        awc = (fc - wp) * (1.0 - coarse_fraction)
        layer_taw = 10.0 * included_cm * awc
        taw_mm += layer_taw
        weighted_fc += fc * included_cm
        weighted_wp += wp * included_cm
        weighted_awc += awc * included_cm
        total_depth_cm += included_cm
        remaining_cm -= included_cm
        if infiltration is not None and infiltration > 0:
            infiltration_candidates.append(infiltration)
        if ksat is not None and ksat > 0:
            ksat_candidates.append(ksat)
        if fc_origin != "measured" or wp_origin != "measured":
            measured_core = False
        contributions.append(
            {
                "depth_from_cm": top,
                "depth_to_cm": bottom,
                "included_depth_cm": round(included_cm, 3),
                "field_capacity": fc,
                "wilting_point": wp,
                "coarse_fragments_pct": cf or 0.0,
                "available_water_capacity": round(awc, 6),
                "taw_contribution_mm": round(layer_taw, 4),
                "origins": {"field_capacity": fc_origin, "wilting_point": wp_origin},
                "confidence": {"field_capacity": fc_conf, "wilting_point": wp_conf},
            }
        )

    if total_depth_cm + 1e-6 < root_depth_cm:
        return {"status": "blocked", "reason": "soil_profile_does_not_cover_root_depth"}
    if taw_mm <= 0:
        return {"status": "blocked", "reason": "non_positive_taw"}

    generated_raw = soil_profile.get("generated_at")
    profile_age_days = None
    if generated_raw:
        try:
            generated = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
            profile_age_days = max(0.0, (now - generated.astimezone(UTC)).total_seconds() / 86400.0)
            if profile_age_days > MAX_PROFILE_AGE_DAYS:
                limitations.append("soil hydraulic profile is stale")
        except (ValueError, TypeError):
            limitations.append("soil hydraulic profile timestamp invalid")
    else:
        limitations.append("soil hydraulic profile timestamp missing")

    infiltration_mm_h = min(infiltration_candidates) if infiltration_candidates else None
    ksat_mm_h = min(ksat_candidates) if ksat_candidates else None
    if infiltration_mm_h is None:
        limitations.append("field infiltration measurement missing")
    if ksat_mm_h is None:
        limitations.append("ksat measurement missing")
    if not measured_core:
        limitations.append("field capacity or wilting point includes pedotransfer evidence")

    soil_ec = _number(soil_ec_ds_m)
    raw_mm = taw_mm * p
    operational = (
        measured_core
        and infiltration_mm_h is not None
        and profile_age_days is not None
        and profile_age_days <= MAX_PROFILE_AGE_DAYS
    )
    quality = "verified" if operational else "degraded"
    effective_at = str(generated_raw or now.isoformat())
    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "crop": crop,
        "root_policy_id": str(root_policy.get("policy_id") or ""),
        "root_policy_version": str(root_policy.get("policy_version") or ""),
        "soil_hydraulic_profile_id": str(soil_profile.get("profile_id") or ""),
        "source_soil_profile_hash": str(soil_profile.get("source_soil_profile_hash") or ""),
        "generated_at": now.isoformat(),
        "effective_at": effective_at,
        "root_depth_m": round(root_depth_m, 4),
        "effective_root_zone_m": round(float(root_state["effective_root_zone_m"]), 4),
        "taw_mm": round(taw_mm, 4),
        "raw_fraction": round(p, 4),
        "raw_mm": round(raw_mm, 4),
        "field_capacity_weighted": round(weighted_fc / total_depth_cm, 6),
        "wilting_point_weighted": round(weighted_wp / total_depth_cm, 6),
        "available_water_capacity_weighted": round(weighted_awc / total_depth_cm, 6),
        "infiltration_mm_h": None if infiltration_mm_h is None else round(infiltration_mm_h, 4),
        "ksat_mm_h": None if ksat_mm_h is None else round(ksat_mm_h, 4),
        "soil_ec_ds_m": soil_ec,
        "layer_contributions": contributions,
        "evidence": {
            "soil_hydraulic_profile": str(soil_profile.get("profile_id") or ""),
            "source_soil_profile_hash": str(soil_profile.get("source_soil_profile_hash") or ""),
            "root_policy_evidence_ids": list(root_policy.get("evidence_ids") or []),
            "root_state_evidence_ids": list(root_state.get("evidence_ids") or []),
            "soil_profile_age_days": None
            if profile_age_days is None
            else round(profile_age_days, 2),
        },
        "quality_status": quality,
        "operational_eligible": operational,
        "limitations": limitations,
    }
    return CanonicalRootZoneProfile(**base, profile_digest=_digest(base))


async def persist_canonical_root_zone_profile(conn, profile: CanonicalRootZoneProfile) -> None:
    """Persist an immutable, tenant-scoped snapshot for evidence and replay."""
    payload = profile.to_dict()
    profile_id = f"rzp_{profile.profile_digest[:24]}"
    await conn.execute(
        "INSERT INTO canonical_root_zone_profiles("
        "root_zone_profile_id,tenant_id,field_id,season_id,soil_hydraulic_profile_id,"
        "source_soil_profile_hash,root_policy_id,effective_at,quality_status,"
        "operational_eligible,root_depth_m,effective_root_zone_m,taw_mm,raw_fraction,"
        "raw_mm,infiltration_mm_h,ksat_mm_h,soil_ec_ds_m,profile_digest,payload) "
        "VALUES($1,$2::uuid,$3,$4,$5,$6,$7::uuid,$8::timestamptz,$9,$10,$11,$12,$13,$14,"
        "$15,$16,$17,$18,$19,$20::jsonb) ON CONFLICT(tenant_id,field_id,season_id,profile_digest) DO NOTHING",
        profile_id,
        profile.tenant_id,
        profile.field_id,
        profile.season_id,
        profile.soil_hydraulic_profile_id,
        profile.source_soil_profile_hash,
        profile.root_policy_id,
        profile.effective_at,
        profile.quality_status,
        profile.operational_eligible,
        profile.root_depth_m,
        profile.effective_root_zone_m,
        profile.taw_mm,
        profile.raw_fraction,
        profile.raw_mm,
        profile.infiltration_mm_h,
        profile.ksat_mm_h,
        profile.soil_ec_ds_m,
        profile.profile_digest,
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
    )


async def resolve_canonical_root_zone_profile(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    crop: str,
    phenology_progress: float | None,
    raw_fraction: float,
) -> CanonicalRootZoneProfile | dict[str, Any]:
    """Resolve governed soil hydraulics and root policy for operational consumers."""
    policy = await conn.fetchrow(
        "SELECT policy_id, initial_depth_m, maximum_depth_m, effective_fraction, "
        "policy_version, evidence_ids FROM crop_root_policies "
        "WHERE tenant_id=$1::uuid AND crop_id=$2 AND status='validated' "
        "AND valid_from <= now() AND (valid_to IS NULL OR valid_to > now()) "
        "ORDER BY valid_from DESC LIMIT 1",
        tenant_id,
        crop,
    )
    if policy is None:
        return {"status": "blocked", "reason": "validated_crop_root_policy_missing"}
    soil_profile = await get_soil_hydraulic_profile(tenant_id=tenant_id, field_id=field_id)
    if soil_profile is None:
        return {"status": "blocked", "reason": "governed_soil_hydraulic_profile_missing"}
    ec_row = await conn.fetchrow(
        "SELECT result FROM soil_lab_tests WHERE field_id=$1 "
        "AND status IN ('approved','published') ORDER BY sampled_on DESC NULLS LAST, created_at DESC LIMIT 1",
        field_id,
    )
    ec = None
    if ec_row and isinstance(ec_row.get("result"), dict):
        result = ec_row["result"]
        ec = result.get("ec_ds_m") or result.get("ec") or result.get("ece_ds_m")
    profile = build_canonical_root_zone_profile(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        crop=crop,
        phenology_progress=phenology_progress,
        raw_fraction=raw_fraction,
        root_policy=dict(policy),
        soil_profile=soil_profile,
        soil_ec_ds_m=ec,
    )
    if isinstance(profile, CanonicalRootZoneProfile):
        await persist_canonical_root_zone_profile(conn, profile)
    return profile
