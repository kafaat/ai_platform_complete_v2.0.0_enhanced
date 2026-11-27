#!/usr/bin/env python3
"""Ratchet for the server-owned irrigation runtime orchestrator."""

import ast
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path


def check_hourly_budgets(path: Path) -> None:
    """Exercise the pure solver: source spelling cannot prove cumulative budgets."""
    spec = importlib.util.spec_from_file_location("_hourly_mpc_budget_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    start = datetime(2026, 7, 13, 20, tzinfo=UTC)
    digest = "a" * 64
    forecast = [
        {
            "hour": (start + timedelta(hours=index)).isoformat(),
            "etc_mm": 0.2,
            "effective_rain_mm": 0.0,
            "maximum_available_power_kw": 100.0,
            "maximum_starting_kva": 100.0,
            "energy_cost_per_kwh": 0.2,
            "renewable_fraction": 0.8,
            "permitted_load_ids": ["guard-pump"],
            "energy_window_digest": digest,
        }
        for index in range(8)
    ]

    def probe(*, area_ha=4.5, minimum_runtime_minutes=30.0, **limits):
        result = module.solve_hourly_energy_aware_mpc(
            tenant_id="guard-tenant",
            field_id="guard-field",
            season_id="guard-season",
            canonical_water_state={
                "operational_eligible": True,
                "taw_mm": 120.0,
                "raw_mm": 60.0,
                "depletion_mm": 70.0,
                "water_state_digest": digest,
                "weather_snapshot_digest": digest,
                "soil_profile_digest": digest,
                "season_state_digest": digest,
            },
            irrigation_capability={
                "status": "verified",
                "maximum_flow_lps": 50.0,
                "maximum_daily_depth_mm": 6.0,
                "maximum_safe_depth_mm_event": 4.0,
                "specific_energy_kwh_m3": 0.3,
                "pump_starting_kva": 25.0,
                "required_energy_load_ids": ["guard-pump"],
                "irrigation_capability_digest": digest,
                **limits,
            },
            commissioning_gate={
                "status": "executable",
                "execution_allowed": True,
                "executability_digest": digest,
            },
            hourly_forecast=forecast,
            area_ha=area_ha,
            minimum_runtime_minutes=minimum_runtime_minutes,
            minimum_off_hours=1,
        )
        assert result.actions, "hourly budget contract: feasible probes must schedule water"
        assert result.execution_allowed is False and result.recommendation_only is True
        for previous, following in pairwise(result.actions):
            elapsed = datetime.fromisoformat(following["hour"]) - datetime.fromisoformat(
                previous["hour"]
            )
            assert elapsed >= timedelta(hours=1, minutes=previous["runtime_minutes"]), (
                "hourly budget contract: rest starts after pump stops"
            )
        return result.actions

    event = probe(maximum_safe_depth_mm_event=2.0, maximum_daily_depth_mm=100.0)
    assert all(Decimal(str(action["irrigation_depth_mm"])) <= 2 for action in event), (
        "hourly budget contract: event ceiling"
    )

    daily = {}
    for action in probe():
        day = datetime.fromisoformat(action["hour"]).astimezone(UTC).date()
        daily[day] = daily.get(day, Decimal(0)) + Decimal(str(action["irrigation_depth_mm"]))
    assert all(depth <= 6 for depth in daily.values()), (
        "hourly budget contract: cumulative daily ceiling"
    )
    assert daily == {start.date(): Decimal(6), (start + timedelta(days=1)).date(): Decimal(6)}, (
        "hourly budget contract: daily budgets renew at UTC midnight"
    )

    seasonal = probe(remaining_seasonal_volume_m3=450.0)
    volume = sum(Decimal(str(action["irrigation_volume_m3"])) for action in seasonal)
    assert volume <= 450, "hourly budget contract: cumulative seasonal ceiling"
    assert volume == 450 and len({action["hour"][:10] for action in seasonal}) == 2, (
        "hourly budget contract: seasonal balance is shared across days"
    )

    # Non-integral volume per mm exposes published rounding, including the
    # conservative seasonal debit when each action rounds its volume upward.
    fractional = probe(
        maximum_daily_depth_mm=1.000001,
        maximum_safe_depth_mm_event=0.3333338,
        remaining_seasonal_volume_m3=3.333329,
        area_ha=0.3333333,
        minimum_runtime_minutes=0,
    )
    volume = sum(Decimal(str(action["irrigation_volume_m3"])) for action in fractional)
    assert Decimal("3.33332") <= volume <= Decimal("3.333329"), (
        "hourly budget contract: published seasonal precision"
    )


ROOT = Path(__file__).resolve().parents[2]
service = (ROOT / "services/sahool-platform/api/irrigation_runtime_orchestrator.py").read_text(
    encoding="utf-8"
)
router = (ROOT / "services/sahool-platform/api/routers/irrigation_mpc.py").read_text(
    encoding="utf-8"
)
required = [
    "resolve_canonical_water_state",
    "canonical_irrigation_capability_graphs",
    "irrigation_executability_gates",
    "solve_hourly_energy_aware_mpc",
    "hourly_irrigation_mpc_schedules",
    "recommendation_only",
    "execution_allowed",
    "server_owned_canonical_truth",
]
for token in required:
    assert token in service, token
assert "/api/v1/fields/{field_id}/irrigation/mpc/hourly-recommendation" in router
for forbidden in ("mqtt.publish", "modbus.write", "actuator dispatch", "dispatch_allowed = true"):
    assert forbidden not in service.lower(), forbidden

orch_tree = ast.parse(service)
solver_calls = [
    node
    for node in ast.walk(orch_tree)
    if isinstance(node, ast.Call)
    and (
        (isinstance(node.func, ast.Name) and node.func.id == "solve_hourly_energy_aware_mpc")
        or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "solve_hourly_energy_aware_mpc"
        )
    )
]
assert len(solver_calls) == 1, "expected exactly one governed hourly MPC solver call"
solver_call = solver_calls[0]
kw = {item.arg: item.value for item in solver_call.keywords if item.arg}
assert "irrigation_capability" in kw
assert isinstance(kw["irrigation_capability"], ast.Name)
assert kw["irrigation_capability"].id == "capability"

hourly = (ROOT / "services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py").read_text(
    encoding="utf-8"
)
hourly_tree = ast.parse(hourly)
capability_keys = set()
for node in ast.walk(hourly_tree):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "irrigation_capability"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        capability_keys.add(node.args[0].value)

assert "maximum_safe_depth_mm_event" in capability_keys
assert "maximum_daily_depth_mm" in capability_keys
assert "remaining_seasonal_volume_m3" in capability_keys
check_hourly_budgets(ROOT / "services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py")

runtime_test = (ROOT / "tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py").read_text(
    encoding="utf-8"
)
assert "test_canonical_root_zone_limit_changes_actual_hourly_mpc_action" in runtime_test
assert "test_m3_fails_closed_when_engineering_event_limit_is_removed" in runtime_test

print("irrigation runtime orchestrator guard: PASS")
