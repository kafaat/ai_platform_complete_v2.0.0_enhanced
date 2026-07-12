import os
from datetime import date
from unittest.mock import AsyncMock, patch

from api.water_decision_bridge import build_candidate, process_water_deficit


def test_candidate_is_deterministic():
    kw = dict(
        tenant_id="11111111-1111-1111-1111-111111111111",
        field_id="f1",
        season_id="s1",
        ledger_date=date(2026, 7, 12),
        entry={"deficit_mm": 20, "confidence": 0.9},
        policy_version="v1",
    )
    a = build_candidate(**kw)
    b = build_candidate(**kw)
    assert a == b and a[2]["stage"] == "candidate"
    assert a[2]["decision_value"]["source_type"] == "water_ledger"


async def test_below_threshold_does_nothing(monkeypatch):
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_DECISION_THRESHOLD_MM", "10")
    out = await process_water_deficit(
        tenant_id="t",
        field_id="f",
        season_id="s",
        ledger_date=date.today(),
        entry={"deficit_mm": 9},
    )
    assert out["status"] == "below_threshold"


async def test_candidate_fail_closed_when_mirror(monkeypatch):
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    with patch(
        "api.decision_service_client.record_decision",
        AsyncMock(return_value={"persisted": False, "authoritative": False}),
    ):
        out = await process_water_deficit(
            tenant_id="t",
            field_id="f",
            season_id="s",
            ledger_date=date.today(),
            entry={"deficit_mm": 20},
        )
    assert out["status"] == "candidate_not_authoritative"


async def test_full_auto_chain(monkeypatch):
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_EXECUTION_TARGET_ID", "pivot-1")
    mods = {
        "record_decision": AsyncMock(return_value={"persisted": True, "authoritative": True}),
        "review_decision": AsyncMock(return_value={"review_id": "rev1"}),
        "create_execution_plan": AsyncMock(return_value={"execution_plan_id": "plan1"}),
        "authorize_dispatch": AsyncMock(return_value={"dispatch_authorization_id": "auth1"}),
        "create_execution_request": AsyncMock(return_value={"execution_request_id": "req1"}),
    }
    with patch.multiple("api.decision_service_client", **mods):
        out = await process_water_deficit(
            tenant_id="t",
            field_id="f",
            season_id="s",
            ledger_date=date.today(),
            entry={"deficit_mm": 20, "confidence": 0.8},
        )
    assert out["status"] == "execution_queued" and out["execution_request_id"] == "req1"


def test_auto_execution_payload_matches_actuator_contract(monkeypatch):
    import asyncio
    import sys
    import types
    from datetime import date

    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_EXECUTION_TARGET_ID", "pivot-17")
    monkeypatch.setenv("WATER_DEFICIT_EXECUTION_TARGET_TYPE", "equipment")

    captured = {}
    fake = types.ModuleType("api.decision_service_client")

    async def record_decision(payload, **kwargs):
        return {"persisted": True, "authoritative": True}

    async def review_decision(*args, **kwargs):
        return {"review_id": "rev-1"}

    async def create_execution_plan(*args, **kwargs):
        return {"execution_plan_id": "plan-1"}

    async def authorize_dispatch(*args, **kwargs):
        return {"dispatch_authorization_id": "auth-1"}

    async def create_execution_request(*args, **kwargs):
        captured.update(args[1])
        return {"execution_request_id": "req-1"}

    fake.record_decision = record_decision
    fake.review_decision = review_decision
    fake.create_execution_plan = create_execution_plan
    fake.authorize_dispatch = authorize_dispatch
    fake.create_execution_request = create_execution_request
    monkeypatch.setitem(sys.modules, "api.decision_service_client", fake)

    result = asyncio.run(
        process_water_deficit(
            tenant_id="tenant-1",
            field_id="field-1",
            season_id="season-1",
            ledger_date=date(2026, 7, 12),
            entry={"deficit_mm": 25.0, "confidence": 0.9},
        )
    )
    assert result["status"] == "execution_queued"
    command = captured["command_payload"]
    assert command["device_id"] == "pivot-17"
    assert command["command"] == "irrigate"
    assert command["payload"]["amount_mm"] == 25.0
    assert command["payload"]["idempotency_key"]
