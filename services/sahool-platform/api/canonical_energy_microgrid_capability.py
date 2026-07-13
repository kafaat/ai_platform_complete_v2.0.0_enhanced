"""M2.7 canonical agricultural microgrid capability.

This module converts governed PV, inverter, battery, generator/grid and load
facts into deterministic hourly energy envelopes.  It is recommendation-only:
it does not dispatch equipment or mutate battery state.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "canonical_energy_microgrid_capability.v1"
PRODUCT_VERSION = "energy-microgrid-capability/1.0.0"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _parse_time(value: Any) -> datetime | None:
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
class HourlyEnergyEnvelope:
    hour: str
    pv_available_kw: float
    battery_soc_percent: float
    battery_charge_limit_kw: float
    battery_discharge_limit_kw: float
    generator_available_kw: float
    grid_available_kw: float
    maximum_continuous_load_kw: float
    maximum_starting_kva: float
    permitted_load_ids: list[str]
    blocked_loads: list[dict[str, str]]
    energy_cost_per_kwh: float
    renewable_fraction: float


@dataclass(frozen=True)
class CanonicalEnergyMicrogridCapability:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    energy_system_id: str
    status: str
    operational_eligible: bool
    battery_chemistry: str | None
    battery_soc_percent: float
    battery_state_of_health_percent: float | None
    reserve_soc_percent: float
    inverter_continuous_kw: float
    inverter_peak_kva: float
    hourly_envelopes: list[dict[str, Any]]
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pv_power_kw(
    *,
    irradiance_w_m2: float,
    ambient_temp_c: float,
    pv_capacity_kwp: float,
    system_derate: float,
    temperature_coefficient_per_c: float,
) -> float:
    """Estimate AC PV power using a conservative nameplate model.

    Cell temperature is approximated as ambient + 20 C at 1000 W/m2.  The
    result is capped at nameplate and never negative.
    """
    irradiance_ratio = _clamp(irradiance_w_m2 / 1000.0, 0.0, 1.2)
    cell_temp_c = ambient_temp_c + 20.0 * irradiance_ratio
    temperature_factor = 1.0 + temperature_coefficient_per_c * (cell_temp_c - 25.0)
    dc_kw = pv_capacity_kwp * irradiance_ratio * max(0.0, temperature_factor)
    return max(0.0, min(pv_capacity_kwp, dc_kw * system_derate))


def _load_start_kva(load: dict[str, Any]) -> float | None:
    explicit = _num(load.get("starting_kva"))
    if explicit is not None:
        return explicit
    rated_kw = _num(load.get("rated_kw"))
    power_factor = _num(load.get("power_factor"))
    multiplier = _num(load.get("starting_multiplier"))
    if rated_kw is None or rated_kw <= 0 or power_factor is None or not (0 < power_factor <= 1):
        return None
    method = str(load.get("start_method") or "direct_on_line")
    default_multiplier = {
        "vfd": 1.15,
        "soft_starter": 2.5,
        "star_delta": 3.5,
        "direct_on_line": 6.0,
    }.get(method, 6.0)
    return rated_kw * (multiplier or default_multiplier) / power_factor


def build_canonical_energy_microgrid_capability(
    *,
    tenant_id: str,
    project_id: str,
    system: dict[str, Any],
    battery: dict[str, Any] | None,
    generator: dict[str, Any] | None,
    grid: dict[str, Any] | None,
    loads: list[dict[str, Any]],
    weather_hours: list[dict[str, Any]],
) -> CanonicalEnergyMicrogridCapability | dict[str, Any]:
    """Build governed hourly energy feasibility for irrigation assets."""
    system_id = str(system.get("energy_system_id") or system.get("id") or "")
    if not system_id or str(system.get("certification_status") or "") != "certified":
        return {"status": "blocked", "reason": "certified_energy_system_required"}
    if system.get("quality") not in {"field_validated", "certified"}:
        return {"status": "blocked", "reason": "field_validated_energy_system_required"}

    pv_kwp = _num(system.get("pv_capacity_kwp")) or 0.0
    inverter_kw = _num(system.get("inverter_continuous_kw"))
    inverter_peak_kva = _num(system.get("inverter_peak_kva"))
    derate = _num(system.get("pv_system_derate"))
    temp_coeff = _num(system.get("pv_temperature_coefficient_per_c"))
    if (
        inverter_kw is None
        or inverter_kw <= 0
        or inverter_peak_kva is None
        or inverter_peak_kva <= 0
    ):
        return {"status": "blocked", "reason": "certified_inverter_limits_required"}
    derate = derate if derate is not None else 0.82
    temp_coeff = temp_coeff if temp_coeff is not None else -0.004
    if not (0 < derate <= 1) or not (-0.02 <= temp_coeff <= 0):
        return {"status": "blocked", "reason": "invalid_pv_model_parameters"}

    blockers: list[str] = []
    limitations: list[str] = []

    # Battery is optional for direct-solar or grid/generator systems.
    battery_soc = 0.0
    reserve_soc = 0.0
    battery_soh: float | None = None
    battery_chemistry: str | None = None
    battery_discharge_kw = 0.0
    battery_charge_kw = 0.0
    _battery_usable_kwh = 0.0
    battery_evidence_digest = None
    if battery:
        battery_chemistry = str(battery.get("chemistry") or "") or None
        battery_soc_value = _num(battery.get("soc_percent"))
        reserve = _num(battery.get("emergency_reserve_percent"))
        minimum_soc = _num(battery.get("minimum_soc_percent"))
        battery_soh = _num(battery.get("state_of_health_percent"))
        battery_discharge = _num(battery.get("maximum_discharge_kw"))
        battery_charge = _num(battery.get("maximum_charge_kw"))
        battery_usable = _num(battery.get("usable_energy_kwh"))
        if any(
            v is None
            for v in (
                battery_soc_value,
                reserve,
                minimum_soc,
                battery_discharge,
                battery_charge,
                battery_usable,
            )
        ):
            blockers.append("COMPLETE_BATTERY_LIMITS_REQUIRED")
        else:
            battery_soc = _clamp(battery_soc_value, 0.0, 100.0)
            reserve_soc = max(reserve, minimum_soc)
            battery_discharge_kw = max(0.0, battery_discharge)
            battery_charge_kw = max(0.0, battery_charge)
            _battery_usable_kwh = max(0.0, battery_usable)
        if str(battery.get("bms_status") or "") not in {"normal", "ready"}:
            blockers.append("BATTERY_BMS_NOT_READY")
        temperature_c = _num(battery.get("temperature_c"))
        if temperature_c is None:
            blockers.append("BATTERY_TEMPERATURE_REQUIRED")
        elif temperature_c < 0 or temperature_c > 45:
            blockers.append("BATTERY_TEMPERATURE_OUT_OF_RANGE")
        if battery_soh is not None and battery_soh < 70:
            blockers.append("BATTERY_STATE_OF_HEALTH_TOO_LOW")
        if battery_soc <= reserve_soc:
            battery_discharge_kw = 0.0
            limitations.append("battery reserve protected; discharge unavailable")
        battery_evidence_digest = battery.get("evidence_digest")

    generator_kw = 0.0
    generator_kva = 0.0
    generator_cost = 0.0
    generator_digest = None
    if generator and generator.get("available"):
        generator_kw = max(0.0, _num(generator.get("continuous_kw")) or 0.0)
        generator_kva = max(0.0, _num(generator.get("starting_kva")) or 0.0)
        generator_cost = max(0.0, _num(generator.get("energy_cost_per_kwh")) or 0.0)
        generator_digest = generator.get("evidence_digest")
        if str(generator.get("certification_status") or "") != "certified":
            blockers.append("CERTIFIED_GENERATOR_REQUIRED")

    grid_kw = 0.0
    grid_kva = 0.0
    grid_cost = 0.0
    grid_digest = None
    if grid and grid.get("available"):
        grid_kw = max(0.0, _num(grid.get("contracted_kw")) or 0.0)
        grid_kva = max(0.0, _num(grid.get("starting_kva")) or grid_kw)
        grid_cost = max(0.0, _num(grid.get("energy_cost_per_kwh")) or 0.0)
        grid_digest = grid.get("evidence_digest")
        voltage_ok = bool(grid.get("voltage_within_limits"))
        frequency_ok = bool(grid.get("frequency_within_limits"))
        if not voltage_ok:
            blockers.append("GRID_VOLTAGE_OUT_OF_RANGE")
        if not frequency_ok:
            blockers.append("GRID_FREQUENCY_OUT_OF_RANGE")

    governed_loads: list[dict[str, Any]] = []
    for load in loads:
        load_id = str(load.get("load_id") or load.get("id") or "")
        rated_kw = _num(load.get("rated_kw"))
        measured_kw = _num(load.get("measured_kw"))
        continuous_kw = measured_kw if measured_kw is not None else rated_kw
        start_kva = _load_start_kva(load)
        if (
            not load_id
            or continuous_kw is None
            or continuous_kw <= 0
            or start_kva is None
            or start_kva <= 0
            or str(load.get("certification_status") or "") != "certified"
        ):
            blockers.append("CERTIFIED_LOAD_PROFILE_REQUIRED")
            continue
        governed_loads.append(
            {
                "load_id": load_id,
                "load_type": str(load.get("load_type") or "other"),
                "continuous_kw": continuous_kw,
                "starting_kva": start_kva,
                "priority": int(load.get("priority") or 99),
                "interruptible": bool(load.get("interruptible", False)),
                "evidence_digest": load.get("evidence_digest"),
            }
        )

    if not weather_hours:
        blockers.append("HOURLY_SOLAR_FORECAST_REQUIRED")

    envelopes: list[dict[str, Any]] = []
    for weather in weather_hours:
        hour_dt = _parse_time(weather.get("hour"))
        irradiance = _num(weather.get("solar_radiation_w_m2"))
        ambient = _num(weather.get("temperature_c"))
        if hour_dt is None or irradiance is None or irradiance < 0 or ambient is None:
            blockers.append("COMPLETE_HOURLY_SOLAR_FORECAST_REQUIRED")
            continue
        if weather.get("quality") not in {"forecast", "measured", "field_validated", "certified"}:
            blockers.append("GOVERNED_WEATHER_FORECAST_REQUIRED")
            continue

        pv_available = _pv_power_kw(
            irradiance_w_m2=irradiance,
            ambient_temp_c=ambient,
            pv_capacity_kwp=pv_kwp,
            system_derate=derate,
            temperature_coefficient_per_c=temp_coeff,
        )
        # The inverter is the AC bottleneck. Grid/generator are independent AC inputs.
        renewable_continuous_kw = min(inverter_kw, pv_available + battery_discharge_kw)
        maximum_continuous_kw = renewable_continuous_kw + generator_kw + grid_kw
        maximum_start_kva = max(inverter_peak_kva, generator_kva, grid_kva)

        permitted: list[str] = []
        blocked: list[dict[str, str]] = []
        for load in sorted(governed_loads, key=lambda item: (item["priority"], item["load_id"])):
            if load["continuous_kw"] > maximum_continuous_kw + 1e-9:
                blocked.append(
                    {"load_id": load["load_id"], "reason": "CONTINUOUS_POWER_LIMIT_EXCEEDED"}
                )
            elif load["starting_kva"] > maximum_start_kva + 1e-9:
                blocked.append(
                    {"load_id": load["load_id"], "reason": "STARTING_KVA_LIMIT_EXCEEDED"}
                )
            else:
                permitted.append(load["load_id"])

        nonrenewable_kw = generator_kw + grid_kw
        renewable_fraction = (
            min(1.0, renewable_continuous_kw / maximum_continuous_kw)
            if maximum_continuous_kw > 0
            else 0.0
        )
        weighted_cost = 0.0
        if nonrenewable_kw > 0:
            weighted_cost = (generator_kw * generator_cost + grid_kw * grid_cost) / nonrenewable_kw

        envelope = HourlyEnergyEnvelope(
            hour=hour_dt.isoformat().replace("+00:00", "Z"),
            pv_available_kw=round(pv_available, 6),
            battery_soc_percent=round(battery_soc, 6),
            battery_charge_limit_kw=round(battery_charge_kw, 6),
            battery_discharge_limit_kw=round(battery_discharge_kw, 6),
            generator_available_kw=round(generator_kw, 6),
            grid_available_kw=round(grid_kw, 6),
            maximum_continuous_load_kw=round(maximum_continuous_kw, 6),
            maximum_starting_kva=round(maximum_start_kva, 6),
            permitted_load_ids=permitted,
            blocked_loads=blocked,
            energy_cost_per_kwh=round(weighted_cost, 6),
            renewable_fraction=round(renewable_fraction, 6),
        )
        envelopes.append(asdict(envelope))

    if not envelopes:
        blockers.append("NO_VALID_HOURLY_ENERGY_ENVELOPES")

    evidence = {
        "energy_system_digest": system.get("evidence_digest"),
        "battery_digest": battery_evidence_digest,
        "generator_digest": generator_digest,
        "grid_digest": grid_digest,
        "load_profile_digests": sorted(
            digest for digest in (item.get("evidence_digest") for item in governed_loads) if digest
        ),
        "weather_snapshot_digests": sorted(
            str(item.get("snapshot_digest"))
            for item in weather_hours
            if item.get("snapshot_digest")
        ),
    }
    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "energy_system_id": system_id,
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "battery_chemistry": battery_chemistry,
        "battery_soc_percent": round(battery_soc, 6),
        "battery_state_of_health_percent": (
            round(battery_soh, 6) if battery_soh is not None else None
        ),
        "reserve_soc_percent": round(reserve_soc, 6),
        "inverter_continuous_kw": round(inverter_kw, 6),
        "inverter_peak_kva": round(inverter_peak_kva, 6),
        "hourly_envelopes": envelopes,
        "evidence": evidence,
        "limitations": sorted(set(limitations)),
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalEnergyMicrogridCapability(**base, capability_digest=_digest(base))


def energy_capability_to_mpc_constraints(
    capability: CanonicalEnergyMicrogridCapability | dict[str, Any],
) -> dict[str, Any]:
    """Expose only governed energy constraints to the MPC boundary."""
    data = (
        capability.to_dict()
        if isinstance(capability, CanonicalEnergyMicrogridCapability)
        else capability
    )
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_energy_capability_not_operational",
            "blocking_reasons": list(
                data.get("blocking_reasons") or [data.get("reason") or "unknown"]
            ),
        }
    return {
        "status": "available",
        "energy_system_id": data["energy_system_id"],
        "minimum_reserved_soc_percent": data["reserve_soc_percent"],
        "hourly_energy_envelopes": [
            {
                "hour": item["hour"],
                "maximum_available_power_kw": item["maximum_continuous_load_kw"],
                "maximum_starting_kva": item["maximum_starting_kva"],
                "maximum_battery_discharge_kw": item["battery_discharge_limit_kw"],
                "permitted_load_ids": item["permitted_load_ids"],
                "energy_cost_per_kwh": item["energy_cost_per_kwh"],
                "renewable_fraction": item["renewable_fraction"],
            }
            for item in data["hourly_envelopes"]
        ],
        "energy_capability_digest": data["capability_digest"],
    }
