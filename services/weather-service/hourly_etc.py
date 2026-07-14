from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "hourly_etc.v1"
FORMULA_VERSION = "open-meteo-fao-et0×season-kc.v1"


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _parse_utc_hour(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def build_hourly_etc_product(
    *,
    provider_payload: dict[str, Any],
    lat: float,
    lon: float,
    horizon_hours: int,
    daily_kc_by_date: dict[str, float],
    daily_runoff_mm_by_date: dict[str, float] | None = None,
    model: str = "best_match",
) -> dict[str, Any]:
    """Build a canonical, provider-native hourly crop-water demand product.

    Open-Meteo owns the native hourly FAO ET0. Season/phenology owns daily Kc and
    supplies it as an explicit dated policy input. This function performs only the
    governed hourly ETc/rain join and never derives ET0 locally.
    """
    horizon_hours = max(1, min(int(horizon_hours), 384))
    hourly = provider_payload.get("hourly") or {}
    times = hourly.get("time") or []
    et0_values = hourly.get("et0_fao_evapotranspiration") or []
    precip_values = hourly.get("precipitation") or []
    runoff_by_date = daily_runoff_mm_by_date or {}

    if (
        not isinstance(times, list)
        or not isinstance(et0_values, list)
        or not isinstance(precip_values, list)
    ):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": "provider_hourly_arrays_missing",
            "quality_status": "unavailable",
            "hours": [],
        }

    raw_rows: list[dict[str, Any]] = []
    for idx, raw_time in enumerate(times):
        if len(raw_rows) >= horizon_hours:
            break
        hour = _parse_utc_hour(raw_time)
        if hour is None:
            continue
        et0 = _finite_nonnegative(et0_values[idx] if idx < len(et0_values) else None)
        precipitation = _finite_nonnegative(
            precip_values[idx] if idx < len(precip_values) else None
        )
        date_key = hour.date().isoformat()
        kc = _finite_nonnegative(daily_kc_by_date.get(date_key))
        if et0 is None or precipitation is None or kc is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "blocked",
                "reason": "canonical_hourly_etc_input_incomplete",
                "quality_status": "unavailable",
                "missing_hour": hour.isoformat().replace("+00:00", "Z"),
                "missing": [
                    name
                    for name, value in (
                        ("et0_mm", et0),
                        ("precipitation_mm", precipitation),
                        ("kc", kc),
                    )
                    if value is None
                ],
                "hours": [],
            }
        raw_rows.append(
            {
                "hour": hour,
                "date": date_key,
                "et0_mm": et0,
                "kc": kc,
                "precipitation_mm": precipitation,
            }
        )

    if len(raw_rows) < horizon_hours:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": "provider_hourly_horizon_incomplete",
            "quality_status": "unavailable",
            "expected_hours": horizon_hours,
            "received_hours": len(raw_rows),
            "hours": [],
        }

    # Allocate a governed daily runoff amount only across rainy hours, proportional
    # to provider precipitation. This avoids pretending all gross rainfall is effective.
    precip_sum_by_date: dict[str, float] = {}
    for row in raw_rows:
        precip_sum_by_date[row["date"]] = precip_sum_by_date.get(row["date"], 0.0) + float(
            row["precipitation_mm"]
        )

    output: list[dict[str, Any]] = []
    for row in raw_rows:
        date_key = row["date"]
        gross = float(row["precipitation_mm"])
        daily_runoff = _finite_nonnegative(runoff_by_date.get(date_key)) or 0.0
        day_precip = precip_sum_by_date.get(date_key, 0.0)
        allocated_runoff = (daily_runoff * gross / day_precip) if day_precip > 0 else 0.0
        effective_rain = max(0.0, gross - allocated_runoff)
        etc = float(row["et0_mm"]) * float(row["kc"])
        hour_payload = {
            "hour": row["hour"].isoformat().replace("+00:00", "Z"),
            "et0_mm": round(float(row["et0_mm"]), 6),
            "kc": round(float(row["kc"]), 6),
            "etc_mm": round(etc, 6),
            "precipitation_mm": round(gross, 6),
            "effective_rain_mm": round(effective_rain, 6),
            "net_crop_demand_mm": round(max(0.0, etc - effective_rain), 6),
            "quality_status": "provider_native",
            "source": "open_meteo_fao_et0",
        }
        hour_payload["content_digest"] = _digest(hour_payload)
        output.append(hour_payload)

    provenance = {
        "provider": "open-meteo",
        "provider_model": model,
        "provider_timezone": provider_payload.get("timezone") or "UTC",
        "provider_utc_offset_seconds": provider_payload.get("utc_offset_seconds", 0),
        "et0_variable": "et0_fao_evapotranspiration",
        "kc_owner": "season_phenology_policy",
        "rain_method": "provider_precipitation_minus_proportional_governed_daily_runoff",
        "formula_version": FORMULA_VERSION,
        "fetched_generation_time_ms": provider_payload.get("generationtime_ms"),
    }
    product_base = {
        "schema_version": SCHEMA_VERSION,
        "status": "verified",
        "quality_status": "provider_native",
        "location": {"lat": float(lat), "lon": float(lon)},
        "horizon_hours": horizon_hours,
        "valid_period": {"start": output[0]["hour"], "end": output[-1]["hour"]},
        "hours": output,
        "provenance": provenance,
        "limitations": [],
    }
    product_base["content_digest"] = _digest(product_base)
    return product_base
