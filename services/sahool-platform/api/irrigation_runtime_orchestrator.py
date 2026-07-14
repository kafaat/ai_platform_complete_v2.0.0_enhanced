"""Server-owned irrigation runtime orchestration.

Composes canonical water truth, the latest persisted irrigation capability graph,
commissioning executability and hourly energy windows into one recommendation-only
MPC schedule.  No agronomic or engineering truth is accepted from the client.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from api.canonical_water_state import resolve_canonical_water_state
from api.field_context import _field_weather_context
from api.hourly_energy_aware_irrigation_mpc import solve_hourly_energy_aware_mpc
from api.weather_service_client import get_hourly_etc_product


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _blocked(*, field_id: str, reason: str, missing: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "blocked",
        "mode": "operational",
        "field_id": field_id,
        "reason": reason,
        "execution_allowed": False,
        "recommendation_only": True,
    }
    if missing:
        payload["missing"] = missing
    payload["orchestration_digest"] = _digest(payload)
    return payload


async def _latest_capability_graph(conn, *, field_id: str, season_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT payload, capability_digest, status, operational_eligible
          FROM canonical_irrigation_capability_graphs
         WHERE field_id=$1 AND season_id=$2
         ORDER BY created_at DESC
         LIMIT 1
        """,
        field_id,
        season_id,
    )
    if row is None:
        return None
    payload = dict(row["payload"] or {})
    payload.setdefault("irrigation_capability_digest", str(row["capability_digest"]))
    payload.setdefault("capability_digest", str(row["capability_digest"]))
    payload.setdefault("status", str(row["status"]))
    payload.setdefault("operational_eligible", bool(row["operational_eligible"]))
    return payload


async def _latest_executability_gate(
    conn, *, field_id: str, season_id: str, capability_digest: str
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT snapshot, execution_allowed, valid_until, blocking_reasons,
               executability_digest, commissioning_certification_digest
          FROM irrigation_executability_gates
         WHERE field_id::text=$1 AND season_id::text=$2
           AND irrigation_capability_digest=$3
         ORDER BY created_at DESC
         LIMIT 1
        """,
        field_id,
        season_id,
        capability_digest,
    )
    if row is None:
        return None
    payload = dict(row["snapshot"] or {})
    valid_until = row["valid_until"]
    expired = valid_until is not None and valid_until <= datetime.now(UTC)
    allowed = bool(row["execution_allowed"]) and not expired
    payload.update(
        {
            "status": "executable" if allowed else "blocked",
            "execution_allowed": allowed,
            "valid_until": None if valid_until is None else valid_until.isoformat(),
            "blocking_reasons": list(row["blocking_reasons"] or [])
            + (["COMMISSIONING_CERTIFICATION_EXPIRED"] if expired else []),
            "executability_digest": str(row["executability_digest"]),
            "commissioning_certification_digest": str(row["commissioning_certification_digest"]),
        }
    )
    return payload


async def _hourly_forecast(
    *,
    tenant_id: str,
    field_id: str,
    water_state: dict[str, Any],
    capability: dict[str, Any],
    horizon_hours: int,
    conn,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join Weather Engine native hourly ETc with governed energy windows.

    There is deliberately no daily temporal-disaggregation fallback. Missing or
    incomplete Weather Engine hours block M3 rather than silently changing semantics.
    """
    daily = list(water_state.get("forecast") or [])
    windows = list(capability.get("hourly_operating_windows") or [])
    if not daily or not windows:
        return [], {"status": "blocked", "reason": "hourly_inputs_missing"}

    evidence_location = (water_state.get("evidence") or {}).get("location") or {}
    lat = evidence_location.get("lat")
    lon = evidence_location.get("lon")
    if lat is None or lon is None:
        lat, lon, _, _, _ = await _field_weather_context(conn, field_id)

    kc_by_date = {
        str(item.get("date")): float(item["kc"])
        for item in daily
        if item.get("date") and item.get("kc") is not None
    }
    runoff_by_date = {
        str(item.get("date")): float(item.get("runoff_mm") or 0.0)
        for item in daily
        if item.get("date")
    }
    product = await get_hourly_etc_product(
        lat=float(lat),
        lon=float(lon),
        horizon_hours=horizon_hours,
        daily_kc_by_date=kc_by_date,
        daily_runoff_mm_by_date=runoff_by_date,
        tenant_id=tenant_id,
    )
    if product.get("status") != "verified" or product.get("quality_status") != "provider_native":
        return [], product

    weather_by_hour = {str(item.get("hour")): item for item in product.get("hours") or []}
    output: list[dict[str, Any]] = []
    for window in windows:
        hour_raw = str(window.get("hour") or "")
        try:
            hour = datetime.fromisoformat(hour_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if hour.tzinfo is None:
            hour = hour.replace(tzinfo=UTC)
        canonical_hour = (
            hour.astimezone(UTC)
            .replace(minute=0, second=0, microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        weather = weather_by_hour.get(canonical_hour)
        if weather is None:
            return [], {
                "status": "blocked",
                "reason": "native_hourly_etc_missing_for_energy_window",
                "missing_hour": canonical_hour,
                "content_digest": product.get("content_digest"),
            }
        output.append(
            {
                "hour": canonical_hour,
                "et0_mm": float(weather["et0_mm"]),
                "kc": float(weather["kc"]),
                "etc_mm": float(weather["etc_mm"]),
                "effective_rain_mm": float(weather["effective_rain_mm"]),
                "net_crop_demand_mm": float(weather["net_crop_demand_mm"]),
                "maximum_available_power_kw": float(
                    window.get("maximum_available_power_kw") or 0.0
                ),
                "maximum_starting_kva": float(window.get("maximum_starting_kva") or 0.0),
                "energy_cost_per_kwh": float(window.get("energy_cost_per_kwh") or 0.0),
                "renewable_fraction": float(window.get("renewable_fraction") or 0.0),
                "permitted_load_ids": list(
                    window.get("permitted_load_ids")
                    or capability.get("required_energy_load_ids")
                    or []
                ),
                "energy_window_digest": str(window.get("energy_window_digest") or _digest(window)),
                "weather_hour_digest": str(weather["content_digest"]),
            }
        )
        if len(output) >= horizon_hours:
            break
    if len(output) < horizon_hours:
        return [], {
            "status": "blocked",
            "reason": "energy_window_horizon_incomplete",
            "expected_hours": horizon_hours,
            "received_hours": len(output),
        }
    return output, product


async def _persist_schedule(conn, schedule: dict[str, Any]) -> None:
    """Idempotently persist a recommendation-only schedule and its actions."""
    row = await conn.fetchrow(
        """
        INSERT INTO hourly_irrigation_mpc_schedules (
            tenant_id, field_id, season_id, solver_version, status,
            recommendation_only, execution_allowed, horizon_start, horizon_hours,
            initial_depletion_mm, final_depletion_mm, required_refill_mm,
            scheduled_irrigation_mm, water_state_digest,
            irrigation_capability_digest, commissioning_executability_digest,
            schedule_digest, payload
        ) VALUES (
            current_setting('app.current_tenant')::uuid, $1, $2, $3, $4,
            TRUE, FALSE, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb
        )
        ON CONFLICT (tenant_id, schedule_digest) DO UPDATE SET
            payload = hourly_irrigation_mpc_schedules.payload
        RETURNING schedule_id
        """,
        schedule["field_id"],
        schedule["season_id"],
        schedule["solver_version"],
        schedule["status"],
        schedule.get("horizon_start"),
        int(schedule.get("horizon_hours") or 0),
        float(schedule.get("initial_depletion_mm") or 0.0),
        float(schedule.get("final_depletion_mm") or 0.0),
        float(schedule.get("required_refill_mm") or 0.0),
        float(schedule.get("scheduled_irrigation_mm") or 0.0),
        schedule["source_digests"]["water_state_digest"],
        schedule["source_digests"]["irrigation_capability_digest"],
        schedule["source_digests"]["commissioning_executability_digest"],
        schedule["schedule_digest"],
        json.dumps(schedule, default=str),
    )
    schedule_id = row["schedule_id"]
    for action in schedule.get("actions") or []:
        await conn.execute(
            """
            INSERT INTO hourly_irrigation_mpc_actions (
                tenant_id, schedule_id, action_hour, irrigation_depth_mm,
                runtime_minutes, expected_energy_kwh, energy_cost,
                renewable_fraction, source_window_digest
            ) VALUES (
                current_setting('app.current_tenant')::uuid, $1, $2, $3, $4, $5, $6, $7, $8
            ) ON CONFLICT (tenant_id, schedule_id, action_hour) DO NOTHING
            """,
            schedule_id,
            action["hour"],
            float(action["irrigation_depth_mm"]),
            float(action["runtime_minutes"]),
            float(action["expected_energy_kwh"]),
            float(action["energy_cost"]),
            float(action["renewable_fraction"]),
            action["source_window_digest"],
        )


async def orchestrate_irrigation_recommendation(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    horizon_hours: int = 48,
    persist: bool = True,
) -> dict[str, Any]:
    """Resolve and schedule a server-owned operational irrigation recommendation."""
    horizon_hours = max(1, min(int(horizon_hours), 72))
    water = await resolve_canonical_water_state(
        conn,
        tenant_id=tenant_id,
        field_id=field_id,
        horizon_days=max(1, (horizon_hours + 23) // 24),
    )
    water_dict = water if isinstance(water, dict) else water.to_dict()
    if water_dict.get("status") == "blocked" or not water_dict.get("season_id"):
        return _blocked(
            field_id=field_id,
            reason=str(water_dict.get("reason") or "canonical_water_state_blocked"),
        )

    season_id = str(water_dict["season_id"])
    area = await conn.fetchval("SELECT area_ha FROM fields WHERE field_id=$1", field_id)
    if area is None or float(area) <= 0:
        return _blocked(field_id=field_id, reason="valid_field_area_required")

    capability = await _latest_capability_graph(conn, field_id=field_id, season_id=season_id)
    if capability is None:
        return _blocked(field_id=field_id, reason="canonical_irrigation_capability_graph_missing")
    capability_digest = str(
        capability.get("irrigation_capability_digest") or capability.get("capability_digest") or ""
    )
    gate = await _latest_executability_gate(
        conn, field_id=field_id, season_id=season_id, capability_digest=capability_digest
    )
    if gate is None:
        return _blocked(field_id=field_id, reason="commissioning_executability_gate_missing")

    hourly, hourly_product = await _hourly_forecast(
        tenant_id=tenant_id,
        field_id=field_id,
        water_state=water_dict,
        capability=capability,
        horizon_hours=horizon_hours,
        conn=conn,
    )
    if not hourly:
        return _blocked(
            field_id=field_id,
            reason=str(hourly_product.get("reason") or "native_hourly_etc_unavailable"),
            missing=hourly_product.get("missing"),
        )
    schedule = solve_hourly_energy_aware_mpc(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        canonical_water_state=water_dict,
        irrigation_capability=capability,
        commissioning_gate=gate,
        hourly_forecast=hourly,
        area_ha=float(area),
        maximum_horizon_hours=horizon_hours,
    ).to_dict()
    schedule["hourly_weather_product_digest"] = hourly_product["content_digest"]
    schedule["hourly_weather_quality"] = hourly_product["quality_status"]
    schedule["hourly_weather_source"] = "weather-engine/open-meteo-fao-et0"
    schedule["mode"] = "operational"
    schedule["facts_source"] = "server_owned_canonical_truth"
    schedule["orchestration_digest"] = _digest(
        {
            "schedule_digest": schedule["schedule_digest"],
            "field_id": field_id,
            "season_id": season_id,
            "capability_digest": capability_digest,
            "executability_digest": gate.get("executability_digest"),
            "hourly_weather_product_digest": hourly_product.get("content_digest"),
        }
    )
    if persist and schedule["status"] in {"verified", "degraded", "blocked"}:
        await _persist_schedule(conn, schedule)
        schedule["persistence_status"] = "persisted"
    else:
        schedule["persistence_status"] = "not_requested"
    return schedule
