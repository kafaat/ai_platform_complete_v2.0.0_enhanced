"""Canonical operational water truth for irrigation decisions.

This module is the single server-side resolver for high-impact irrigation inputs.
It never accepts agronomic facts from the client and never invents missing values.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from core.season_phenology import crop_kc_profile, resolve_crop_id, stage_kc

from api.canonical_root_zone_profile import resolve_canonical_root_zone_profile
from api.field_context import _field_weather_context
from api.weather_service_client import get_et0_series, get_weather_forecast

SCHEMA_VERSION = "canonical_water_state.v1"
MAX_LEDGER_AGE_HOURS = 72.0


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _rowdict(row: Any) -> dict | None:
    return None if row is None else dict(row)


@dataclass(frozen=True)
class CanonicalWaterState:
    schema_version: str
    tenant_id: str
    field_id: str
    season_id: str
    crop: str
    growth_stage: str
    depletion_mm: float
    depletion_confidence: float | None
    ledger_date: str
    ledger_age_hours: float
    taw_mm: float
    raw_fraction: float
    raw_mm: float
    root_depth_m: float
    soil_texture: str
    forecast: list[dict]
    evidence: dict
    quality_status: str
    operational_eligible: bool
    limitations: list[str]
    water_state_digest: str
    weather_snapshot_digest: str
    soil_profile_digest: str
    season_state_digest: str

    def to_dict(self) -> dict:
        return asdict(self)


async def resolve_canonical_water_state(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    horizon_days: int = 7,
) -> CanonicalWaterState | dict:
    """Resolve canonical water state or return a fail-closed blocked payload."""
    horizon_days = max(1, min(int(horizon_days), 14))
    lat, lon, crop, stage, days_since_sowing = await _field_weather_context(conn, field_id)

    season = await conn.fetchrow(
        "SELECT season_id, sowing_date, crops FROM seasons "
        "WHERE field_id=$1 AND status='active' ORDER BY created_at DESC LIMIT 1",
        field_id,
    )
    if season is None:
        return {"status": "blocked", "reason": "no_active_season", "field_id": field_id}
    season_id = str(season["season_id"])
    if not crop:
        return {
            "status": "blocked",
            "reason": "crop_unknown",
            "field_id": field_id,
            "season_id": season_id,
        }

    ledger = await conn.fetchrow(
        "SELECT ledger_date, depletion_mm, confidence, et0_mm, kc, etc_mm, rain_mm "
        "FROM water_ledger WHERE field_id=$1 ORDER BY ledger_date DESC LIMIT 1",
        field_id,
    )
    if ledger is None or ledger["depletion_mm"] is None:
        return {
            "status": "blocked",
            "reason": "no_ground_truth_depletion",
            "field_id": field_id,
            "season_id": season_id,
        }

    ledger_date = ledger["ledger_date"]
    ledger_dt = datetime.combine(ledger_date, datetime.min.time(), tzinfo=UTC)
    age_hours = max(0.0, (datetime.now(UTC) - ledger_dt).total_seconds() / 3600.0)

    crop_id = resolve_crop_id(crop)
    kc_profile = crop_kc_profile(crop_id)
    if kc_profile is None or days_since_sowing is None:
        return {
            "status": "blocked",
            "reason": "canonical_phenology_missing",
            "field_id": field_id,
            "season_id": season_id,
        }
    season_days = max(1.0, float(sum(kc_profile.stage_days)))
    phenology_progress = max(0.0, min(1.0, float(days_since_sowing) / season_days))
    root_zone = await resolve_canonical_root_zone_profile(
        conn,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        crop=crop_id or str(crop),
        phenology_progress=phenology_progress,
        raw_fraction=0.5,
    )
    if isinstance(root_zone, dict):
        return {
            "status": "blocked",
            "reason": root_zone.get("reason", "canonical_root_zone_unavailable"),
            "field_id": field_id,
            "season_id": season_id,
        }

    fc = await get_weather_forecast(lat, lon, days=horizon_days)
    days = fc.get("days") or []
    if len(days) < horizon_days:
        return {
            "status": "blocked",
            "reason": "weather_forecast_incomplete",
            "field_id": field_id,
            "season_id": season_id,
        }

    # ET0 is produced only by Weather Engine; the forecast endpoint supplies meteorology.
    series = await get_et0_series(
        daily_t_min=[d.get("temp_min_c") for d in days[:horizon_days]],
        daily_t_max=[d.get("temp_max_c") for d in days[:horizon_days]],
        daily_solar_rad_mj_m2=[d.get("solar_radiation_mj_m2") for d in days[:horizon_days]],
        daily_rh_mean_pct=[d.get("humidity_mean_pct") for d in days[:horizon_days]],
        daily_wind_2m_ms=[d.get("wind_max_ms") for d in days[:horizon_days]],
        lat_deg=lat,
        elevation_m=2000.0,
        daily_dates=[d.get("date") for d in days[:horizon_days]],
        tenant_id=tenant_id,
        valid_period={"start": days[0].get("date"), "end": days[horizon_days - 1].get("date")},
    )
    et0_days = series.get("daily_et0_mm") or []
    if len(et0_days) < horizon_days or any(v is None for v in et0_days[:horizon_days]):
        return {
            "status": "blocked",
            "reason": "canonical_et0_incomplete",
            "field_id": field_id,
            "season_id": season_id,
        }

    forecast: list[dict] = []
    for i, d in enumerate(days[:horizon_days]):
        rain = d.get("precipitation_mm", 0.0)
        kc = stage_kc(crop_id, None if days_since_sowing is None else days_since_sowing + i)
        if kc is None:
            return {
                "status": "blocked",
                "reason": "canonical_kc_missing",
                "field_id": field_id,
                "season_id": season_id,
            }
        forecast.append(
            {
                "date": d.get("date"),
                "et0_mm": float(et0_days[i]),
                "kc": float(kc),
                "rain_mm": float(rain or 0.0),
                "runoff_mm": 0.0,
                "source": "weather-engine-et0-series+season-phenology",
            }
        )

    limitations = list(root_zone.limitations)
    if age_hours > MAX_LEDGER_AGE_HOURS:
        limitations.append(f"water ledger stale: {age_hours:.1f}h > {MAX_LEDGER_AGE_HOURS:.0f}h")
    if float(ledger["depletion_mm"]) > float(root_zone.taw_mm):
        return {
            "status": "blocked",
            "reason": "inconsistent_depletion_exceeds_taw",
            "field_id": field_id,
            "season_id": season_id,
        }

    evidence = {
        "ledger": _rowdict(ledger),
        "soil": {
            "root_zone_profile_id": root_zone.soil_hydraulic_profile_id,
            "root_zone_profile_digest": root_zone.profile_digest,
            "root_policy_version": root_zone.root_policy_version,
            "quality_status": root_zone.quality_status,
            "evidence": root_zone.evidence,
        },
        "season": {
            "season_id": season_id,
            "crop": crop,
            "stage": stage,
            "days_since_sowing": days_since_sowing,
        },
        "weather_source": fc.get("source") or "weather-engine",
    }
    weather_digest = _digest(forecast)
    soil_digest = root_zone.profile_digest
    season_digest = _digest(evidence["season"])
    operational_eligible = age_hours <= MAX_LEDGER_AGE_HOURS and root_zone.operational_eligible
    quality = "verified" if operational_eligible else "degraded"
    base = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "crop": str(crop),
        "growth_stage": str(stage),
        "depletion_mm": float(ledger["depletion_mm"]),
        "depletion_confidence": None
        if ledger["confidence"] is None
        else float(ledger["confidence"]),
        "ledger_date": str(ledger_date),
        "ledger_age_hours": round(age_hours, 2),
        "taw_mm": float(root_zone.taw_mm),
        "raw_fraction": float(root_zone.raw_fraction),
        "raw_mm": float(root_zone.raw_mm),
        "root_depth_m": float(root_zone.root_depth_m),
        "soil_texture": "governed_hydraulic_profile",
        "forecast": forecast,
        "evidence": evidence,
        "quality_status": quality,
        "operational_eligible": operational_eligible,
        "limitations": limitations,
        "weather_snapshot_digest": weather_digest,
        "soil_profile_digest": soil_digest,
        "season_state_digest": season_digest,
    }
    water_digest = _digest(base)
    return CanonicalWaterState(**base, water_state_digest=water_digest)
