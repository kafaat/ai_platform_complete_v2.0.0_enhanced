from __future__ import annotations

from shared.autonomous_farm_os_phase9 import plan_closed_loop_execution
from shared.iot_execution_runtime import (
    build_dispatch_envelopes,
    dispatch_envelopes,
    summarize_telemetry_frames,
)


def _approved_recommendation() -> dict:
    return {
        "recommendation_id": "rec-1",
        "source_state_id": "state-1",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "field_id": "22222222-2222-2222-2222-222222222222",
        "status": "approved",
        "action_type": "irrigation",
        "decision": {"operator_approved": True, "water_mm": 12, "risk_score": 0.1},
        "evidence": {},
    }


def test_iot_envelopes_are_fail_safe_by_default() -> None:
    plan = plan_closed_loop_execution(
        _approved_recommendation(),
        mode="supervised_autonomy",
        policy={"max_risk_score": 0.5},
        actuator_registry={
            "22222222-2222-2222-2222-222222222222": {"protocol": "mqtt", "target_id": "pivot-7"}
        },
    )
    assert plan["status"] == "dispatch_ready"
    prepared = build_dispatch_envelopes(plan)
    assert prepared["ready"] is True
    batch = dispatch_envelopes(prepared["envelopes"])
    assert batch["fail_closed"] is True
    assert batch["physical_effect_count"] == 0
    assert batch["results"][0]["status"] == "simulated"


def test_real_mode_still_requires_explicit_physical_enable_and_non_dry_run() -> None:
    plan = plan_closed_loop_execution(
        _approved_recommendation(),
        mode="supervised_autonomy",
        policy={"max_risk_score": 0.5},
        actuator_registry={
            "22222222-2222-2222-2222-222222222222": {"protocol": "mqtt", "target_id": "pump-3"}
        },
    )
    prepared = build_dispatch_envelopes(
        plan,
        adapter_config={"mqtt": {"enabled": True, "mode": "real"}},
        physical_actuation_enabled=False,
    )
    batch = dispatch_envelopes(prepared["envelopes"])
    assert batch["results"][0]["status"] == "blocked"
    assert batch["results"][0]["physical_effect"] is False


def test_telemetry_summary_collects_ack_fault_and_sensor_evidence() -> None:
    summary = summarize_telemetry_frames(
        [
            {"acknowledged_command_ids": ["cmd_1"], "flow_rate": 7.5, "pressure": 2.1},
            {
                "acknowledged_command_ids": ["cmd_1"],
                "power_current": 11.0,
                "soil_moisture_delta": 0.04,
            },
        ]
    )
    assert summary["telemetry_ok"] is True
    assert summary["acknowledged_command_ids"] == ["cmd_1"]
    assert summary["flow_rate"]["mean"] == 7.5
