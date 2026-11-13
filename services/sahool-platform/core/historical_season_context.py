"""Compose a deterministic historical-season context from existing source records.

This is an in-process composition boundary, not a new service or source of truth.
It never invents missing quantities: only accepted, explicitly measured irrigation
and cloud-qualified NDVI observations may influence simulation inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from api.season_simulation import fapar_from_ndvi


def _primitive(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    # asyncpg يُعيد أعمدة UUID (season_records.id/tenant_id) كـ``UUID`` — نصّها القانونيّ،
    # وإلّا يسقط json.dumps للبصمة فيفشل التشغيل بعد ربط السجلّ.
    if isinstance(value, UUID):
        return str(value)
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
    simulation_window: Mapping[str, str] | None = None,
    weather_provenance: Mapping[str, Any] | None = None,
    spatial_provenance: Mapping[str, Any] | None = None,
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
    window = _primitive(dict(simulation_window)) if simulation_window is not None else None
    if window is not None:
        window_start = str(window.get("start") or "")
        window_end = str(window.get("end") or "")
        try:
            if date.fromisoformat(window_end) < date.fromisoformat(window_start):
                raise ValueError("simulation end precedes start")
        except (TypeError, ValueError) as exc:
            raise ValueError("historical simulation window is invalid") from exc
    else:
        window_start = window_end = ""

    def _in_window(raw_day: Any) -> bool:
        if window is None:
            return True  # historical callers without a window retain legacy behavior
        if raw_day is None:
            return False
        day = str(raw_day)[:10]
        return window_start <= day <= window_end

    def _finite(value: Any, *, minimum: float = 0.0, maximum: float | None = None) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(number) or number < minimum:
            return None
        if maximum is not None and number > maximum:
            return None
        return number

    trusted_irrigation = [
        amount
        for e in event_rows
        if e.get("event_type") == "irrigation"
        and not bool(e.get("low_confidence"))
        and _in_window(e.get("event_date"))
        if (amount := _finite(e.get("amount_mm"))) is not None
    ]
    irrigation_mm_total = sum(trusted_irrigation) if trusted_irrigation else None

    valid_vegetation: list[dict[str, Any]] = []
    fapar_values: list[float] = []
    for observation in vegetation_rows:
        ndvi = _finite(observation.get("ndvi_mean"), minimum=-1.0, maximum=1.0)
        cloud = _finite(observation.get("cloud_pct"), maximum=30.0)
        if ndvi is None or cloud is None or not _in_window(observation.get("acquisition_date")):
            continue
        # Raster owns threshold-based quality. We enforce only the physical
        # identity invariant: an observation with explicitly zero/invalid
        # valid-pixel or field coverage cannot represent a measured field mean.
        ratios = (
            observation.get("valid_pixel_ratio"),
            observation.get("coverage_ratio"),
        )
        if any(
            raw is not None
            and (
                (ratio := _finite(raw, minimum=0.0, maximum=1.0)) is None
                or ratio == 0.0
            )
            for raw in ratios
        ):
            continue
        normalized = dict(observation)
        normalized["fapar"] = round(fapar_from_ndvi(ndvi), 6)
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
            "quality_rule": "ndvi[-1,1]; cloud_pct_required<=30; reported_coverage>0",
            "observations": valid_vegetation,
            "observation_count": len(valid_vegetation),
            "observed_fapar_seasonal_mean": observed_fapar,
        },
        "weather": {
            "status": "available" if weather_rows else "empty",
            "source": "weather-service" if weather_provenance is not None else "legacy_unknown",
            "provenance": _row(weather_provenance),
            "window": window,
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
    # Spatial evidence changes the input identity even when the NDVI averages,
    # rainfall and modeled yield happen to be numerically identical.
    if spatial_provenance is not None:
        context["spatial"] = _row(spatial_provenance)
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
    if harvest is not None:
        value = harvest.get("yield_kg_ha")
        try:
            candidate = float(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            candidate = None
        if candidate is not None and math.isfinite(candidate) and candidate >= 0:
            actual = candidate

    if actual is not None and predicted is not None:
        predicted_f = float(predicted)
        delta = actual - predicted_f
        relative_error = (delta / actual) if actual != 0 else None
        within_band = low is not None and high is not None and float(low) <= actual <= float(high)
        outcome["expected_vs_actual"] = {
            "status": "compared",
            "predicted_yield_kg_ha": predicted_f,
            "actual_yield_kg_ha": actual,
            "delta_kg_ha": round(delta, 6),
            "relative_error": round(relative_error, 6) if relative_error is not None else None,
            "actual_within_uncertainty_band": within_band,
        }
    elif actual is not None:
        # A verified harvest may exist even when simulation is unavailable:
        # missing forecast is not missing observed harvest.
        outcome["expected_vs_actual"] = {
            "status": "prediction_unavailable",
            "predicted_yield_kg_ha": None,
            "actual_yield_kg_ha": actual,
        }
    else:
        outcome["expected_vs_actual"] = {
            "status": "no_actual_yield",
            "predicted_yield_kg_ha": float(predicted) if predicted is not None else None,
        }
    return outcome
