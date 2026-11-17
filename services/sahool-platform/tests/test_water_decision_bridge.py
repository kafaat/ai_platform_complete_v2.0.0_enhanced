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


@pytest.mark.unit
async def test_auto_plan_chain_stops_before_authorization(monkeypatch):
    """W2-04: policy approval and the plan run; authorisation and execution never do."""
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
    assert out["status"] == "awaiting_human_authorization", out
    assert out["execution_plan_id"] == "plan1", out
    assert out["review_id"] == "rev1", out
    assert "dispatch_authorization_id" not in out, "the bridge must not authorise"
    assert "execution_request_id" not in out, "the bridge must not request execution"
    mods["authorize_dispatch"].assert_not_awaited()
    mods["create_execution_request"].assert_not_awaited()
    # The policy approves the version decision-service stored and reported (035).
    review_payload = mods["review_decision"].await_args.args[1]
    assert review_payload["decision_value_digest"] == "c" * 64, review_payload


@pytest.mark.unit
def test_bridge_needs_no_authorization_or_execution_client(monkeypatch):
    """W2-04: the bridge's client contract no longer contains authorise/execute.

    A decision-service client without ``authorize_dispatch``/``create_execution_request``
    is enough for the whole bridge path; the old bridge failed to import them."""
    import asyncio
    import sys
    import types

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
        captured.update(args[1])
        return {"execution_plan_id": "plan-1"}

    # W2-02: the client contract includes the shared AC-1 helpers. This fake keeps the
    # staged (not enforced) behaviour: no lineage bound, the candidate recorded unchanged.
    async def governed_candidate_lineage(**kwargs):
        return None

    async def submit_governed_candidate(payload, binding, *, tenant_id, record=None):
        return {"status": "recorded", "record": await record_decision(payload)}

    fake.governed_candidate_lineage = governed_candidate_lineage
    fake.submit_governed_candidate = submit_governed_candidate
    fake.record_decision = record_decision
    fake.review_decision = review_decision
    fake.create_execution_plan = create_execution_plan
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
    assert result["status"] == "awaiting_human_authorization", result
    assert result["execution_target"] == {"target_type": "equipment", "target_id": "pivot-17"}, (
        result
    )
    assert result["recommended_irrigation_mm"] == 25.0, result
    assert captured["constraints"]["max_irrigation_mm"] == 25.0, captured
    assert captured["required_resources"] == [{"target_id": "pivot-17"}], captured


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
    """الاتّجاهُ الآخر: ريٌّ مسجَّلٌ مقيس يبقى قابلاً للاعتماد الآليّ والتخطيط — لا تعطيلٌ شامل.

    W2-04: ينتهي المسار عند خطّةٍ معتمدة تنتظر مفوِّضاً بشريّاً، لا عند طلب تنفيذ."""
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
    assert out["status"] == "awaiting_human_authorization", out
    assert out["applied_water_status"] == "recorded", out
    mods["create_execution_plan"].assert_awaited_once()
    mods["authorize_dispatch"].assert_not_awaited()
    mods["create_execution_request"].assert_not_awaited()


# ── W2-04 (owner decision 2026-11-16): stop at an approved plan, wait for a human ─────
#
# The bridge used one actor (``WATER_DEFICIT_POLICY_ACTOR``) to review, plan, authorise and
# request execution. decision-service refuses reviewer == authoriser under separation of
# duties (``persistence.authorize_dispatch``), so in production the auto path died at
# ``authorization_failed``. The stub below applies decision-service's own rule, loaded from
# its source, at the store-function level (no network, no fake connection).


def _decision_service_sod_rule():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "decision-service" / "persistence.py"
    spec = importlib.util.spec_from_file_location("_w204_decision_persistence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.separation_of_duties_violation


class _SodDecisionService:
    """decision-service's review/plan/authorise/execute calls with its SoD refusal."""

    def __init__(self):
        self.violation = _decision_service_sod_rule()
        self.reviews: dict[str, str] = {}
        self.plans: dict[str, str] = {}
        self.authorize_calls: list[str] = []
        self.execute_calls: list[str] = []

    async def record(self, payload, **_kw):
        return {"persisted": True, "authoritative": True, "decision_value_digest": "e" * 64}

    async def review(self, decision_id, payload, *, tenant_id, reviewed_by):
        self.reviews[decision_id] = reviewed_by
        return {"review_id": f"rev:{decision_id}"}

    async def plan(self, decision_id, payload, *, tenant_id, created_by):
        plan_id = f"plan:{decision_id}"
        self.plans[plan_id] = decision_id
        return {"execution_plan_id": plan_id}

    async def authorize(self, plan_id, payload, *, tenant_id, authorized_by):
        self.authorize_calls.append(authorized_by)
        reviewed_by = self.reviews[self.plans[plan_id]]
        if self.violation(reviewed_by, authorized_by):
            return {"status": "forbidden", "reason": "separation_of_duties_violation"}
        return {"dispatch_authorization_id": f"auth:{plan_id}"}

    async def execute(self, auth_id, payload, *, tenant_id, requested_by):
        self.execute_calls.append(requested_by)
        return {"execution_request_id": f"req:{auth_id}"}

    def mods(self):
        return {
            "record_decision": self.record,
            "review_decision": self.review,
            "create_execution_plan": self.plan,
            "authorize_dispatch": self.authorize,
            "create_execution_request": self.execute,
        }


@pytest.mark.unit
async def test_sod_on_bridge_ends_awaiting_human_authorization(monkeypatch):
    """Acceptance: with SoD on, the path ends in ``awaiting_human_authorization`` and no
    authorisation or execution call is made. Negative control: the old bridge called
    ``authorize_dispatch`` as its own reviewer and ended in ``authorization_failed``."""
    _arm_auto(monkeypatch)
    monkeypatch.setenv("DECISION_REQUIRE_SEPARATION_OF_DUTIES", "true")
    service = _SodDecisionService()
    with patch.multiple("api.decision_service_client", **service.mods()):
        out = await process_water_deficit(
            tenant_id="11111111-1111-1111-1111-111111111111",
            field_id="f",
            season_id="s",
            ledger_date=date(2026, 11, 16),
            entry={"deficit_mm": 30.0, "confidence": 0.8, "applied_water_status": "recorded"},
        )
    assert out["status"] == "awaiting_human_authorization", out
    assert service.authorize_calls == [], f"bridge called authorize: {service.authorize_calls}"
    assert service.execute_calls == [], f"bridge requested execution: {service.execute_calls}"
    assert out["execution_plan_id"] == f"plan:{out['decision_id']}", out
    assert out["review_id"] == f"rev:{out['decision_id']}", out
    assert out["reviewed_by"] == "water-deficit-policy", out


@pytest.mark.unit
async def test_human_authoriser_completes_the_plan_the_bridge_left(monkeypatch):
    """The ids the bridge returns are what the existing authorise path needs: a human other
    than the policy reviewer is authorised; the policy actor itself is refused (which is why
    the bridge must stop)."""
    _arm_auto(monkeypatch)
    monkeypatch.setenv("DECISION_REQUIRE_SEPARATION_OF_DUTIES", "true")
    service = _SodDecisionService()
    with patch.multiple("api.decision_service_client", **service.mods()):
        out = await process_water_deficit(
            tenant_id="11111111-1111-1111-1111-111111111111",
            field_id="f",
            season_id="s",
            ledger_date=date(2026, 11, 16),
            entry={"deficit_mm": 30.0, "confidence": 0.8, "applied_water_status": "recorded"},
        )
    plan_id = out["execution_plan_id"]
    by_policy = await service.authorize(
        plan_id, {}, tenant_id="t", authorized_by=out["reviewed_by"]
    )
    assert by_policy.get("reason") == "separation_of_duties_violation", by_policy
    by_human = await service.authorize(plan_id, {}, tenant_id="t", authorized_by="farm-manager-1")
    assert by_human.get("dispatch_authorization_id") == f"auth:{plan_id}", by_human


@pytest.mark.unit
async def test_unknown_applied_water_still_holds_for_review_under_sod(monkeypatch):
    """W2-04 keeps the earlier hold: unknown applied water never reaches review or plan."""
    _arm_auto(monkeypatch)
    monkeypatch.setenv("DECISION_REQUIRE_SEPARATION_OF_DUTIES", "true")
    service = _SodDecisionService()
    with patch.multiple("api.decision_service_client", **service.mods()):
        out = await process_water_deficit(
            tenant_id="11111111-1111-1111-1111-111111111111",
            field_id="f",
            season_id="s",
            ledger_date=date(2026, 11, 16),
            entry={"deficit_mm": 30.0, "notes": ["irrigation_unobserved"]},
        )
    assert out["status"] == "held_for_review_applied_water_unknown", out
    assert service.reviews == {} and service.plans == {}, (service.reviews, service.plans)
    assert service.authorize_calls == [] and service.execute_calls == [], "no dispatch"
