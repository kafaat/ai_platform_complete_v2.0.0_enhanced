"""Compose a deterministic historical-season context from existing source records.

This is an in-process composition boundary, not a new service or source of truth.
It never invents missing quantities: only accepted, explicitly measured irrigation
and cloud-qualified NDVI observations may influence simulation inputs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from api.season_simulation import fapar_from_ndvi


def _primitive(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(k): _primitive(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    if isinstance(value, (list, tuple)):
        return [_primitive(v) for v in value]
    return value


def _row(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return _primitive(dict(value)) if value is not None else None


def compose_historical_season_context(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    season: Mapping[str, Any],
    season_record: Mapping[str, Any] | None = None,
    crop: Mapping[str, Any] | None = None,
    events: Iterable[Mapping[str, Any]] = (),
    harvest: Mapping[str, Any] | None = None,
    vegetation: Iterable[Mapping[str, Any]] = (),
    weather: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return canonical context plus safe inputs for the existing simulator."""
    event_rows = sorted(
        (_primitive(dict(e)) for e in events),
        key=lambda e: (str(e.get("event_date") or ""), str(e.get("id") or "")),
    )
    vegetation_rows = sorted(
        (_primitive(dict(v)) for v in vegetation),
        key=lambda v: (str(v.get("acquisition_date") or ""), str(v.get("id") or "")),
    )
    weather_rows = [_primitive(dict(w)) for w in weather]

    trusted_irrigation = [
        float(e["amount_mm"])
        for e in event_rows
        if e.get("event_type") == "irrigation"
        and e.get("amount_mm") is not None
        and not bool(e.get("low_confidence"))
        and float(e["amount_mm"]) >= 0
    ]
    irrigation_mm_total = sum(trusted_irrigation) if trusted_irrigation else None

    valid_vegetation: list[dict[str, Any]] = []
    fapar_values: list[float] = []
    for observation in vegetation_rows:
        ndvi = observation.get("ndvi_mean")
        cloud = observation.get("cloud_pct")
        if ndvi is None or not -1.0 <= float(ndvi) <= 1.0:
            continue
        if cloud is None or float(cloud) > 30.0:
            continue
        normalized = dict(observation)
        normalized["fapar"] = round(fapar_from_ndvi(float(ndvi)), 6)
        valid_vegetation.append(normalized)
        fapar_values.append(normalized["fapar"])

    # The existing simulator explicitly supports a seasonal observed-fAPAR scalar.
    # We use it only when there are qualified observations and expose count/quality;
    # no daily interpolation or persistence is invented.
    observed_fapar = round(sum(fapar_values) / len(fapar_values), 6) if fapar_values else None

    linked = season_record is not None
    context = {
        "contract_version": "historical-season-context.v1",
        "identity": {
            "tenant_id": str(tenant_id),
            "field_id": str(field_id),
            "season_id": str(season_id),
            "season_record_id": (
                str(season_record.get("id")) if season_record and season_record.get("id") else None
            ),
        },
        "season": _row(season),
        "manual_record": {
            "status": "available" if linked else "empty",
            "record": _row(season_record),
            "crop": _row(crop),
            "events": event_rows,
            "harvest": _row(harvest),
        },
        "vegetation": {
            "status": "available" if valid_vegetation else "empty",
            "quality_rule": "ndvi[-1,1]; cloud_pct_required<=30",
            "observations": valid_vegetation,
            "observation_count": len(valid_vegetation),
            "observed_fapar_seasonal_mean": observed_fapar,
        },
        "weather": {
            "status": "available" if weather_rows else "empty",
            "source": "open-meteo-era5+weather-engine",
            "days": weather_rows,
            "day_count": len(weather_rows),
        },
        "simulation_inputs": {
            "irrigation_mm_total": irrigation_mm_total,
            "observed_fapar": observed_fapar,
        },
        "quality": {
            "manual_record_accepted": bool(
                season_record and season_record.get("trust_status") == "accepted"
            ),
            "irrigation_measurement_count": len(trusted_irrigation),
            "vegetation_observation_count": len(valid_vegetation),
            "weather_day_count": len(weather_rows),
            "no_daily_fapar_interpolation": True,
        },
    }
    canonical = json.dumps(
        context, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    context["input_digest"] = hashlib.sha256(canonical).hexdigest()
    return context


def build_simulation_outcome(
    result: Mapping[str, Any],
    *,
    engine_name: str,
    engine_version: str,
    parameter_version: str,
    harvest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Output-side companion to the input bundle for the decision-center snapshot.

    Carries the run's engine identity, the prediction with its uncertainty band,
    and — only when an accepted actual harvest yield exists — the expected-vs-actual
    delta. Deliberately kept OUT of ``compose_historical_season_context`` and its
    ``input_digest``: this describes results, not the reproducible inputs the run was
    derived from. Never invents an actual yield; absence is reported explicitly.
    """
    row = _primitive(dict(result))
    predicted = row.get("yield_kg_ha")
    low = row.get("yield_low_kg_ha")
    high = row.get("yield_high_kg_ha")

    outcome: dict[str, Any] = {
        "engine": {
            "name": str(engine_name),
            "version": str(engine_version),
            "parameter_version": str(parameter_version),
        },
        "prediction": {
            "yield_kg_ha": predicted,
            "yield_low_kg_ha": low,
            "yield_high_kg_ha": high,
            "confidence": row.get("confidence"),
            "water_stress_factor": row.get("water_stress_factor"),
        },
    }

    actual: float | None = None
    if harvest is not None and harvest.get("yield_kg_ha") is not None:
        try:
            actual = float(harvest["yield_kg_ha"])
        except (TypeError, ValueError):
            actual = None

    if actual is not None and predicted is not None:
        predicted_f = float(predicted)
        delta = actual - predicted_f
        relative_error = (delta / actual) if actual not in (0, 0.0) else None
        within_band = low is not None and high is not None and float(low) <= actual <= float(high)
        outcome["expected_vs_actual"] = {
            "status": "compared",
            "predicted_yield_kg_ha": predicted_f,
            "actual_yield_kg_ha": actual,
            "delta_kg_ha": round(delta, 6),
            "relative_error": round(relative_error, 6) if relative_error is not None else None,
            "actual_within_uncertainty_band": within_band,
        }
    else:
        outcome["expected_vs_actual"] = {
            "status": "no_actual_yield",
            "predicted_yield_kg_ha": float(predicted) if predicted is not None else None,
        }
    return outcome
