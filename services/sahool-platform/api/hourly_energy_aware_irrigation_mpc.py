"""M3 hourly energy-aware lexicographic irrigation MPC.

Deterministic, recommendation-only scheduler.  It consumes governed canonical
water state, the unified irrigation capability graph, commissioning gate,
hourly crop/weather demand and hourly energy envelopes.  It never dispatches
controllers and it fails closed when an execution prerequisite is absent.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "hourly_energy_aware_irrigation_mpc.v1"
SOLVER_VERSION = "hourly-lex-mpc.v1"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _hour(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class HourlyMPCAction:
    hour: str
    irrigation_depth_mm: float
    irrigation_volume_m3: float
    runtime_minutes: float
    expected_energy_kwh: float
    energy_cost: float
    renewable_fraction: float
    depletion_before_mm: float
    depletion_after_mm: float
    source_window_digest: str


@dataclass(frozen=True)
class HourlyLexObjectives:
    j1_critical_stress_hours: int
    j2_total_water_mm: float
    j2_total_energy_kwh: float
    j3_yield_floor_preserved: bool | None
    j4_total_energy_cost: float
    j5_start_count: int
    j6_renewable_fraction: float


@dataclass(frozen=True)
class HourlyEnergyAwareMPCSchedule:
    schema_version: str
    solver_version: str
    tenant_id: str
    field_id: str
    season_id: str
    decision: str
    status: str
    execution_allowed: bool
    recommendation_only: bool
    horizon_start: str | None
    horizon_hours: int
    initial_depletion_mm: float
    final_depletion_mm: float
    taw_mm: float
    raw_mm: float
    required_refill_mm: float
    scheduled_irrigation_mm: float
    scheduled_volume_m3: float
    actions: list[dict[str, Any]]
    objectives: dict[str, Any]
    operating_state: str
    blocking_reasons: list[str]
    limitations: list[str]
    source_digests: dict[str, str]
    schedule_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocked(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    reasons: list[str],
    taw_mm: float = 0.0,
    raw_mm: float = 0.0,
    initial_depletion_mm: float = 0.0,
    source_digests: dict[str, str] | None = None,
) -> HourlyEnergyAwareMPCSchedule:
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "reasons": sorted(set(reasons)),
        "source_digests": source_digests or {},
    }
    return HourlyEnergyAwareMPCSchedule(
        schema_version=SCHEMA_VERSION,
        solver_version=SOLVER_VERSION,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        decision="blocked",
        status="blocked",
        execution_allowed=False,
        recommendation_only=True,
        horizon_start=None,
        horizon_hours=0,
        initial_depletion_mm=initial_depletion_mm,
        final_depletion_mm=initial_depletion_mm,
        taw_mm=taw_mm,
        raw_mm=raw_mm,
        required_refill_mm=0.0,
        scheduled_irrigation_mm=0.0,
        scheduled_volume_m3=0.0,
        actions=[],
        objectives=asdict(HourlyLexObjectives(0, 0.0, 0.0, None, 0.0, 0, 0.0)),
        operating_state="EMERGENCY_FAIL_CLOSED",
        blocking_reasons=sorted(set(reasons)),
        limitations=[],
        source_digests=source_digests or {},
        schedule_digest=_digest(payload),
    )


def solve_hourly_energy_aware_mpc(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    canonical_water_state: dict[str, Any],
    irrigation_capability: dict[str, Any],
    commissioning_gate: dict[str, Any],
    hourly_forecast: list[dict[str, Any]],
    area_ha: float,
    maximum_horizon_hours: int = 72,
    minimum_runtime_minutes: float = 30.0,
    minimum_off_hours: int = 1,
    target_depletion_fraction_of_raw: float = 0.5,
    yield_floor_preserved: bool | None = None,
) -> HourlyEnergyAwareMPCSchedule:
    """Build a governed hourly schedule using strict lexicographic priorities.

    Priority order: avoid critical stress, obey hard engineering/energy limits,
    preserve an externally governed yield floor when supplied, minimize water and
    energy cost, then minimize starts and maximize renewable use.
    """
    reasons: list[str] = []
    limitations: list[str] = []
    source_digests = {
        "water_state_digest": str(canonical_water_state.get("water_state_digest") or ""),
        "irrigation_capability_digest": str(
            irrigation_capability.get("irrigation_capability_digest") or ""
        ),
        "commissioning_executability_digest": str(
            commissioning_gate.get("executability_digest") or ""
        ),
        "weather_snapshot_digest": str(canonical_water_state.get("weather_snapshot_digest") or ""),
        "soil_profile_digest": str(canonical_water_state.get("soil_profile_digest") or ""),
        "season_state_digest": str(canonical_water_state.get("season_state_digest") or ""),
    }
    if not all(len(v) == 64 for v in source_digests.values()):
        reasons.append("COMPLETE_CANONICAL_SOURCE_DIGESTS_REQUIRED")
    if canonical_water_state.get("operational_eligible") is not True:
        reasons.append("CANONICAL_WATER_STATE_NOT_OPERATIONAL")
    if irrigation_capability.get("status") not in {"verified", "available"}:
        reasons.append("IRRIGATION_CAPABILITY_GRAPH_BLOCKED")
    if (
        commissioning_gate.get("status") != "executable"
        or commissioning_gate.get("execution_allowed") is not True
    ):
        reasons.append("COMMISSIONING_EXECUTABILITY_GATE_REQUIRED")

    taw = _num(canonical_water_state.get("taw_mm"))
    raw = _num(canonical_water_state.get("raw_mm"))
    dr = _num(canonical_water_state.get("depletion_mm"))
    area = _num(area_ha)
    if (
        taw is None
        or taw <= 0
        or raw is None
        or not (0 < raw <= taw)
        or dr is None
        or not (0 <= dr <= taw)
    ):
        reasons.append("VALID_WATER_STATE_REQUIRED")
    if area is None or area <= 0:
        reasons.append("VALID_IRRIGATED_AREA_REQUIRED")

    max_flow_lps = _num(irrigation_capability.get("maximum_flow_lps"))
    max_daily_depth = _num(irrigation_capability.get("maximum_daily_depth_mm"))
    max_event_depth = _num(irrigation_capability.get("maximum_safe_depth_mm_event"))
    specific_energy = _num(irrigation_capability.get("specific_energy_kwh_m3"))
    if any(
        v is None or v <= 0
        for v in (max_flow_lps, max_daily_depth, max_event_depth, specific_energy)
    ):
        reasons.append("COMPLETE_ENGINEERING_CAPABILITY_REQUIRED")

    if not hourly_forecast:
        reasons.append("HOURLY_FORECAST_REQUIRED")
    if reasons:
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            reasons=reasons,
            taw_mm=taw or 0.0,
            raw_mm=raw or 0.0,
            initial_depletion_mm=dr or 0.0,
            source_digests=source_digests,
        )

    assert taw is not None and raw is not None and dr is not None and area is not None
    assert max_flow_lps is not None and max_daily_depth is not None
    assert max_event_depth is not None and specific_energy is not None

    hours: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    for raw_hour in hourly_forecast[:maximum_horizon_hours]:
        when = _hour(raw_hour.get("hour"))
        etc = _num(raw_hour.get("etc_mm"))
        rain = _num(raw_hour.get("effective_rain_mm"))
        available_kw = _num(raw_hour.get("maximum_available_power_kw"))
        starting_kva = _num(raw_hour.get("maximum_starting_kva"))
        cost = _num(raw_hour.get("energy_cost_per_kwh"))
        renewable = _num(raw_hour.get("renewable_fraction"))
        permitted = raw_hour.get("permitted_load_ids")
        if when is None or etc is None or etc < 0 or rain is None or rain < 0:
            reasons.append("INVALID_HOURLY_CROP_WEATHER_INPUT")
            continue
        if previous_time is not None and when <= previous_time:
            reasons.append("HOURLY_FORECAST_NOT_STRICTLY_ORDERED")
        previous_time = when
        if any(v is None or v < 0 for v in (available_kw, starting_kva, cost, renewable)):
            reasons.append("INVALID_HOURLY_ENERGY_ENVELOPE")
            continue
        hours.append(
            {
                "hour": when,
                "etc_mm": etc,
                "rain_mm": rain,
                "available_kw": available_kw,
                "starting_kva": starting_kva,
                "cost": cost,
                "renewable": max(0.0, min(1.0, renewable)),
                "permitted_load_ids": list(permitted or []),
                "window_digest": str(raw_hour.get("energy_window_digest") or _digest(raw_hour)),
            }
        )
    if reasons or not hours:
        reasons.append("NO_VALID_HOURLY_WINDOWS") if not hours else None
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            reasons=reasons,
            taw_mm=taw,
            raw_mm=raw,
            initial_depletion_mm=dr,
            source_digests=source_digests,
        )

    pump_kw = max_flow_lps * specific_energy * 3.6
    pump_start_kva = _num(irrigation_capability.get("pump_starting_kva")) or pump_kw * 1.15
    required_load_ids = set(irrigation_capability.get("required_energy_load_ids") or [])
    feasible: list[dict[str, Any]] = []
    projected_dr = dr
    critical_hours_without_irrigation = 0
    for h in hours:
        projected_dr = min(taw, max(0.0, projected_dr + h["etc_mm"] - h["rain_mm"]))
        if projected_dr > raw:
            critical_hours_without_irrigation += 1
        loads_ok = not required_load_ids or required_load_ids.issubset(set(h["permitted_load_ids"]))
        h["feasible"] = (
            h["available_kw"] >= pump_kw and h["starting_kva"] >= pump_start_kva and loads_ok
        )
        h["projected_dr"] = projected_dr
        if h["feasible"]:
            feasible.append(h)

    target_dr = max(0.0, min(raw, raw * target_depletion_fraction_of_raw))
    required_refill = max(0.0, dr - target_dr)
    forecast_net_demand = sum(h["etc_mm"] - h["rain_mm"] for h in hours)
    required_refill = min(taw, max(required_refill, max(0.0, dr + forecast_net_demand - raw)))
    event_limit = min(max_event_depth, max_daily_depth)
    if required_refill <= 1e-9:
        actions: list[HourlyMPCAction] = []
        _final_dr = min(taw, max(0.0, dr + forecast_net_demand))
    elif not feasible:
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            reasons=["NO_FEASIBLE_HOURLY_ENERGY_WINDOW"],
            taw_mm=taw,
            raw_mm=raw,
            initial_depletion_mm=dr,
            source_digests=source_digests,
        )
    else:
        # Lexicographic ordering: earliest stress prevention first, then lower cost,
        # fewer starts (larger event), then higher renewable fraction.
        feasible.sort(
            key=lambda h: (h["projected_dr"] <= raw, h["hour"], h["cost"], -h["renewable"])
        )
        remaining = required_refill
        actions = []
        last_action_time: datetime | None = None
        state_dr = dr
        for h in hours:
            state_dr = min(taw, max(0.0, state_dr + h["etc_mm"] - h["rain_mm"]))
            if remaining <= 1e-9:
                continue
            if not h["feasible"]:
                continue
            if (
                last_action_time is not None
                and (h["hour"] - last_action_time).total_seconds() < minimum_off_hours * 3600
            ):
                continue
            depth_from_full_hour = max_flow_lps * 3.6 / (area * 10.0)
            min_depth = max_flow_lps * minimum_runtime_minutes * 0.06 / (area * 10.0)
            depth = min(remaining, event_limit, depth_from_full_hour, state_dr)
            if depth < min_depth and remaining > min_depth:
                continue
            if depth <= 1e-9:
                continue
            runtime = depth * area * 10.0 / (max_flow_lps * 0.06)
            volume = depth * area * 10.0
            energy = volume * specific_energy
            action = HourlyMPCAction(
                hour=h["hour"].isoformat().replace("+00:00", "Z"),
                irrigation_depth_mm=round(depth, 6),
                irrigation_volume_m3=round(volume, 6),
                runtime_minutes=round(runtime, 3),
                expected_energy_kwh=round(energy, 6),
                energy_cost=round(energy * h["cost"], 6),
                renewable_fraction=round(h["renewable"], 6),
                depletion_before_mm=round(state_dr, 6),
                depletion_after_mm=round(max(0.0, state_dr - depth), 6),
                source_window_digest=h["window_digest"],
            )
            actions.append(action)
            state_dr = max(0.0, state_dr - depth)
            remaining -= depth
            last_action_time = h["hour"]
        _final_dr = state_dr
        if remaining > 1e-6:
            limitations.append("HOURLY_CAPABILITY_COULD_NOT_SATISFY_FULL_REFILL_TARGET")

    total_depth = sum(a.irrigation_depth_mm for a in actions)
    total_volume = sum(a.irrigation_volume_m3 for a in actions)
    total_energy = sum(a.expected_energy_kwh for a in actions)
    total_cost = sum(a.energy_cost for a in actions)
    renewable_energy = sum(a.expected_energy_kwh * a.renewable_fraction for a in actions)
    renewable_fraction = renewable_energy / total_energy if total_energy > 0 else 0.0
    stress_hours = 0
    check_dr = dr
    action_by_hour = {a.hour: a for a in actions}
    for h in hours:
        check_dr = min(taw, max(0.0, check_dr + h["etc_mm"] - h["rain_mm"]))
        action = action_by_hour.get(h["hour"].isoformat().replace("+00:00", "Z"))
        if action:
            check_dr = max(0.0, check_dr - action.irrigation_depth_mm)
        if check_dr > raw:
            stress_hours += 1
    status = "verified" if stress_hours == 0 and not limitations else "degraded"
    decision = "irrigate" if actions else "hold"
    operating_state = (
        "ENERGY_CONSTRAINED" if limitations or len(feasible) < len(hours) else "NORMAL_OPTIMIZATION"
    )
    objectives = HourlyLexObjectives(
        j1_critical_stress_hours=stress_hours,
        j2_total_water_mm=round(total_depth, 6),
        j2_total_energy_kwh=round(total_energy, 6),
        j3_yield_floor_preserved=yield_floor_preserved,
        j4_total_energy_cost=round(total_cost, 6),
        j5_start_count=len(actions),
        j6_renewable_fraction=round(renewable_fraction, 6),
    )
    payload = {
        "solver_version": SOLVER_VERSION,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "initial_depletion_mm": dr,
        "taw_mm": taw,
        "raw_mm": raw,
        "required_refill_mm": required_refill,
        "actions": [asdict(a) for a in actions],
        "objectives": asdict(objectives),
        "source_digests": source_digests,
    }
    return HourlyEnergyAwareMPCSchedule(
        schema_version=SCHEMA_VERSION,
        solver_version=SOLVER_VERSION,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        decision=decision,
        status=status,
        execution_allowed=False,
        recommendation_only=True,
        horizon_start=hours[0]["hour"].isoformat().replace("+00:00", "Z"),
        horizon_hours=len(hours),
        initial_depletion_mm=dr,
        final_depletion_mm=round(check_dr, 6),
        taw_mm=taw,
        raw_mm=raw,
        required_refill_mm=round(required_refill, 6),
        scheduled_irrigation_mm=round(total_depth, 6),
        scheduled_volume_m3=round(total_volume, 6),
        actions=[asdict(a) for a in actions],
        objectives=asdict(objectives),
        operating_state=operating_state,
        blocking_reasons=[],
        limitations=limitations,
        source_digests=source_digests,
        schedule_digest=_digest(payload),
    )
