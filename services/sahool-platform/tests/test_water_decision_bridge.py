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
