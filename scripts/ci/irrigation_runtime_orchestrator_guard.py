#!/usr/bin/env python3
"""Ratchet for the server-owned irrigation runtime orchestrator."""

import ast
from pathlib import Path

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
assert "event_limit = min(max_event_depth, max_daily_depth)" in hourly

runtime_test = (ROOT / "tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py").read_text(
    encoding="utf-8"
)
assert "test_canonical_root_zone_limit_changes_actual_hourly_mpc_action" in runtime_test
assert "test_m3_fails_closed_when_engineering_event_limit_is_removed" in runtime_test

print("irrigation runtime orchestrator guard: PASS")
