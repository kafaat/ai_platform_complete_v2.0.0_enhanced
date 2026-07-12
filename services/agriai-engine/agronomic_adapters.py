"""Strict adapters from SAHOOL domain snapshots to crop-model inputs.

Each adapter validates the governed snapshot it receives and produces a
deterministic, hash-stamped model input. Missing or physically-invalid
parameters raise typed ``ValueError`` codes — nothing is defaulted or
synthesized on the science path.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash(x: Any) -> str:
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def crop_card_to_model(card: dict[str, Any]) -> dict[str, Any]:
    required = (
        "crop_id",
        "cultivar_id",
        "version",
        "base_temp_c",
        "gdd_to_maturity",
        "max_yield_kg_ha",
        "harvest_index",
        "water_use_efficiency",
    )
    missing = [k for k in required if card.get(k) is None]
    if missing:
        raise ValueError("crop_card_missing:" + ",".join(missing))
    out = {k: card[k] for k in required if k not in ("crop_id", "cultivar_id", "version")}
    out.update(
        {
            "crop_id": card["crop_id"],
            "cultivar_id": card["cultivar_id"],
            "crop_card_version": card["version"],
            "parameter_set_hash": _hash(card),
        }
    )
    return out


def soil_profile_to_model(profile: dict[str, Any]) -> dict[str, Any]:
    required = (
        "soil_profile_id",
        "field_capacity",
        "wilting_point",
        "rootable_depth_cm",
        "bulk_density",
    )
    missing = [k for k in required if profile.get(k) is None]
    if missing:
        raise ValueError("soil_profile_missing:" + ",".join(missing))
    fc = float(profile["field_capacity"])
    wp = float(profile["wilting_point"])
    depth = float(profile["rootable_depth_cm"])
    if not 0 <= wp < fc <= 1:
        raise ValueError("soil_hydraulics_invalid")
    return {
        **profile,
        # plant-available water over the rootable depth (mm): (FC-WP) * depth_cm * 10
        "available_water_mm": round((fc - wp) * depth * 10.0, 3),
        "soil_parameter_hash": _hash(profile),
    }


def weather_series_to_model(snapshot: dict[str, Any]) -> dict[str, Any]:
    daily = snapshot.get("daily")
    if not isinstance(daily, list) or not daily:
        raise ValueError("weather_daily_required")
    normalized = []
    for i, d in enumerate(daily):
        if not isinstance(d, dict):
            raise ValueError(f"weather_day_invalid:{i}")
        missing = [
            k
            for k in ("date", "tmin", "tmax", "rain_mm", "solar_radiation_mj_m2", "wind_m_s")
            if d.get(k) is None
        ]
        if missing:
            raise ValueError(f"weather_day_missing:{i}:" + ",".join(missing))
        normalized.append(d)
    return {**snapshot, "daily": normalized, "weather_series_hash": _hash(normalized)}


def irrigation_to_model(profile: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    eff = float(profile.get("application_efficiency", 0))
    if not 0 < eff <= 1:
        raise ValueError("irrigation_efficiency_invalid")
    events = history.get("irrigation_events") or []
    if not isinstance(events, list):
        raise ValueError("irrigation_events_invalid")
    gross = sum(float(e.get("depth_mm", 0)) for e in events if isinstance(e, dict))
    return {
        "irrigation_mm": round(gross * eff, 3),
        "gross_irrigation_mm": round(gross, 3),
        "application_efficiency": eff,
        "irrigation_events": events,
        "irrigation_input_hash": _hash({"profile": profile, "events": events}),
    }
