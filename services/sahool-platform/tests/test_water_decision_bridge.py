import os
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
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
        "record_decision": AsyncMock(
            return_value={
                "persisted": True,
                "authoritative": True,
                "decision_value_digest": "c" * 64,
            }
        ),
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
            # قيدٌ ريُّه مقيس (لا أعلام) — شرطُ الاعتماد الآليّ بعد إغلاق الريّ المجهول.
            entry={"deficit_mm": 20, "confidence": 0.8, "notes": []},
        )
    assert out["status"] == "execution_queued" and out["execution_request_id"] == "req1"
    # The policy approves the version decision-service stored and reported (035).
    review_payload = mods["review_decision"].await_args.args[1]
    assert review_payload["decision_value_digest"] == "c" * 64


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
            entry={"deficit_mm": 25.0, "confidence": 0.9, "applied_water_status": "recorded"},
        )
    )
    assert result["status"] == "execution_queued"
    command = captured["command_payload"]
    assert command["device_id"] == "pivot-17"
    assert command["command"] == "irrigate"
    assert command["payload"]["amount_mm"] == 25.0
    assert command["payload"]["idempotency_key"]


# ── UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01 ─────────────────────────────
#
# عجزٌ بُنِي على ريٍّ **قُرِئ صفراً لأنّه مجهول** (مزرعةٌ تروي من بئرٍ ولا تسجّل) هو حدٌّ
# أعلى للحاجة لا قياسُها. كان الجسرُ يعتمده آليّاً ويُرسل أمرَ ريٍّ بمقداره إلى المُشغِّل.


def _auto_mods():
    return {
        "record_decision": AsyncMock(
            return_value={
                "persisted": True,
                "authoritative": True,
                "decision_value_digest": "d" * 64,
            }
        ),
        "review_decision": AsyncMock(return_value={"review_id": "rev1"}),
        "create_execution_plan": AsyncMock(return_value={"execution_plan_id": "plan1"}),
        "authorize_dispatch": AsyncMock(return_value={"dispatch_authorization_id": "auth1"}),
        "create_execution_request": AsyncMock(return_value={"execution_request_id": "req1"}),
    }


def _arm_auto(monkeypatch):
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("WATER_DEFICIT_EXECUTION_TARGET_ID", "pivot-1")


@pytest.mark.unit
@pytest.mark.parametrize(
    "entry",
    [
        # كما يكتبه العامل ليومٍ بلا صفِّ ريّ (`irrigation_unobserved`).
        {"deficit_mm": 40.0, "confidence": 0.4, "notes": ["irrigation_unobserved"]},
        {"deficit_mm": 40.0, "confidence": 0.4, "applied_water_status": "unrecorded"},
        # صفٌّ موجودٌ بحجمٍ غائب — الاتّجاهُ نفسُه (الماءُ المضاف أدنى تقدير).
        {"deficit_mm": 40.0, "confidence": 0.4, "notes": ["irrigation_volume_untracked"]},
        # قيدٌ لا يُعلِن حالةَ الريّ أصلاً: الغيابُ لا يُقرأ «مُسجَّلاً».
        {"deficit_mm": 40.0, "confidence": 0.9},
    ],
)
async def test_unrecorded_irrigation_is_never_auto_executed(monkeypatch, entry):
    _arm_auto(monkeypatch)
    mods = _auto_mods()
    with patch.multiple("api.decision_service_client", **mods):
        out = await process_water_deficit(
            tenant_id="t", field_id="f", season_id="s", ledger_date=date.today(), entry=entry
        )
    assert out["status"] == "held_for_review_applied_water_unknown", out
    assert out["applied_water_status"] != "recorded"
    mods["review_decision"].assert_not_awaited()
    mods["create_execution_request"].assert_not_awaited()
    value = mods["record_decision"].await_args.args[0]["decision_value"]
    assert value["requires_human_review"] is True
    assert value["applied_water_status"] in {"unrecorded", "volume_untracked", "undeclared"}


@pytest.mark.unit
def test_candidate_names_the_applied_water_status_and_flags():
    _, _, payload = build_candidate(
        tenant_id="t",
        field_id="f",
        season_id="s",
        ledger_date=date(2026, 10, 15),
        entry={
            "deficit_mm": 40.0,
            "notes": ["irrigation_unobserved", "root_zone_texture_fallback"],
        },
        policy_version="v1",
    )
    value = payload["decision_value"]
    assert value["applied_water_status"] == "unrecorded"
    assert value["data_quality_flags"] == ["irrigation_unobserved", "root_zone_texture_fallback"]
    assert value["requires_human_review"] is True


@pytest.mark.unit
async def test_recorded_irrigation_still_auto_executes(monkeypatch):
    """الاتّجاهُ الآخر: ريٌّ مسجَّلٌ مقيس يبقى قابلاً للاعتماد الآليّ — لا تعطيلٌ شامل."""
    _arm_auto(monkeypatch)
    mods = _auto_mods()
    with patch.multiple("api.decision_service_client", **mods):
        out = await process_water_deficit(
            tenant_id="t",
            field_id="f",
            season_id="s",
            ledger_date=date.today(),
            entry={
                "deficit_mm": 40.0,
                "confidence": 0.7,
                "notes": [],
                "applied_water_status": "recorded",
            },
        )
    assert out["status"] == "execution_queued"
    assert out["applied_water_status"] == "recorded"
