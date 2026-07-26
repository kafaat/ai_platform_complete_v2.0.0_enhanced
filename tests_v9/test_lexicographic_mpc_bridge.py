"""اختبار جسر وراوتر متحكّم الريّ الهرميّ المعجميّ (P1.1b) — نقيّ حتميّ.

يغطّي:
- بناء المرشّح (`build_mpc_candidate`): الشكل + انتشار النَّسَب الكامل (content_digest 64-hex +
  idempotency_key + solver_version + candidate_lineage_id) + النوع irrigation_mpc + توصية-فقط.
- الإصدار (`emit_mpc_candidate`): مُطفأ افتراضيّاً (لا مسّ للشبكة) · فاشل-مُغلَق على الطوارئ ·
  candidate_created عند التمكين مع مركز قرار موثوق (mock) و execution_allowed=False دائماً.
- الراوتر (`irrigation_mpc_plan`/`capabilities`): استدعاء المعالِج مباشرةً بمستخدم وهميّ —
  عزل المستأجِر من المستخدم لا الجسم · قراءة الدفتر الغائبة ⇒ 0 + تدهور مُعلَن (لا اختلاق) ·
  submit بلا تمكين ⇒ disabled · القدرات لا تصل لأسماء خاصّة.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

# الراوتر يستورد api.main (FastAPI). بيئة اختبارات الوحدة في CI منطق صرف بلا FastAPI،
# فتخطّى اختبارات الراوتر هناك. اختبارات الجسر/الحلّال نقيّة فتبقى عاملة دائماً.
_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None
_requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/api.main not importable in the pure-logic unit env"
)

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_mpc import ForecastDay  # noqa: E402
from api.lexicographic_irrigation_mpc import (  # noqa: E402
    OperatingState,
    solve_lexicographic_irrigation,
)
from api.lexicographic_mpc_bridge import (  # noqa: E402
    bridge_enabled,
    build_mpc_candidate,
    emit_mpc_candidate,
)


def _dry(n=7, et0=10.0, kc=1.0, rain=0.0):
    return [ForecastDay(et0_mm=et0, kc=kc, rain_mm=rain) for _ in range(n)]


def _decision(**overrides):
    kwargs = dict(
        forecast=_dry(),
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=45.0,
        tenant_id="t1",
        field_id="fld_a",
        season_id="s1",
        crop="maize",
        growth_stage="flowering",
    )
    kwargs.update(overrides)
    return solve_lexicographic_irrigation(**kwargs)


# ─────────────────────────── build_mpc_candidate ───────────────────────────


def test_candidate_shape_and_lineage_propagation():
    d = _decision()
    decision_id, lineage, candidate = build_mpc_candidate(d)

    assert candidate["decision_type"] == "irrigation_mpc"
    assert candidate["stage"] == "candidate"
    assert candidate["field_id"] == "fld_a"
    assert candidate["season_id"] == "s1"
    assert decision_id == "mpcdec_" + d.content_digest[:24]
    assert lineage == d.candidate_lineage_id

    # النَّسَب الكامل مُنتشِر على مستوى القمّة (يسهل ربطه في السلسلة).
    assert candidate["content_digest"] == d.content_digest
    assert len(candidate["content_digest"]) == 64  # sha256 كامل، لا مبتور
    assert candidate["idempotency_key"] == d.idempotency_key
    assert candidate["solver_version"] == d.solver_version
    assert candidate["candidate_lineage_id"] == d.candidate_lineage_id

    # توصية-فقط: النَّسَب يدخل decision_value أيضاً فينتقل عبر السلسلة.
    value = candidate["decision_value"]
    assert value["requires_human_review"] is True
    assert value["source_type"] == "lexicographic_mpc"
    assert value["source_id"] == f"fld_a:{d.content_digest[:16]}"


def test_distinct_decisions_yield_distinct_candidate_ids():
    # قرارات مختلفة (استنزاف مختلف) ⇒ decision_id/lineage مختلفان (لا تصادم P0).
    a = _decision(initial_depletion_mm=45.0)
    b = _decision(initial_depletion_mm=60.0)
    da, la, _ = build_mpc_candidate(a)
    db, lb, _ = build_mpc_candidate(b)
    assert da != db
    assert la != lb


def test_same_inputs_stable_idempotency_key():
    a = _decision()
    b = _decision()
    _, _, ca = build_mpc_candidate(a)
    _, _, cb = build_mpc_candidate(b)
    assert ca["idempotency_key"] == cb["idempotency_key"]  # نفس المُدخلات ⇒ نفس الخانة المنطقيّة


# ─────────────────────────── emit_mpc_candidate ───────────────────────────


def test_emit_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", raising=False)
    assert bridge_enabled() is False
    out = asyncio.run(emit_mpc_candidate(_decision(), tenant_id="t1"))
    assert out == {"status": "disabled"}


def test_emit_fail_closed_on_emergency(monkeypatch):
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")
    # حقائق غير صالحة ⇒ EMERGENCY_FAIL_CLOSED.
    d = solve_lexicographic_irrigation(
        forecast=[], taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=0.0, field_id="fld_x"
    )
    assert d.operating_state is OperatingState.EMERGENCY_FAIL_CLOSED
    out = asyncio.run(emit_mpc_candidate(d, tenant_id="t1"))
    assert out["status"] == "fail_closed"


def test_emit_creates_candidate_with_mocked_center(monkeypatch):
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")
    captured = {}

    async def _fake_record(payload, *, tenant_id=None):
        captured["payload"] = payload
        captured["tenant_id"] = tenant_id
        return {"persisted": True, "authoritative": True}

    import api.decision_service_client as dsc

    monkeypatch.setattr(dsc, "record_decision", _fake_record)

    d = _decision()
    out = asyncio.run(emit_mpc_candidate(d, tenant_id="t1"))
    assert out["status"] == "candidate_created"
    assert out["execution_allowed"] is False  # توصية-فقط بنيويّاً
    assert out["content_digest"] == d.content_digest
    assert out["idempotency_key"] == d.idempotency_key
    # عزل المستأجِر: يُمرَّر إلى مركز القرار.
    assert captured["tenant_id"] == "t1"
    assert captured["payload"]["decision_type"] == "irrigation_mpc"


def test_emit_not_authoritative_is_surfaced(monkeypatch):
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")

    async def _fake_record(payload, *, tenant_id=None):
        return {"persisted": False}

    import api.decision_service_client as dsc

    monkeypatch.setattr(dsc, "record_decision", _fake_record)

    out = asyncio.run(emit_mpc_candidate(_decision(), tenant_id="t1"))
    assert out["status"] == "candidate_not_authoritative"


# ─────────────────────────── الراوتر (استدعاء المعالِج) ───────────────────────────


class _User:
    tenant_id = "tenant-42"


@_requires_fastapi
def test_route_plan_blocks_when_no_ground_truth_depletion(monkeypatch):
    """P1.1c: غياب Dr مرجعيّ ⇒ blocked (لا اختلاق صفر، لا قرار قابل للإرسال)."""
    import api.routers.irrigation_mpc as route

    async def _no_ledger(tenant_id, field_id):
        return None  # لا صفّ دفتر

    monkeypatch.setattr(route, "_latest_ledger_depletion", _no_ledger)

    req = route.MpcPlanRequest(
        field_id="fld_a",
        forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
        taw_mm=100.0,
        crop="maize",
        growth_stage="flowering",
    )
    out = asyncio.run(route.irrigation_mpc_plan(req, user=_User()))
    assert out["status"] == "blocked"
    assert out["reason"] == "no_ground_truth_depletion"
    assert "decision" not in out  # لا قرار مُختلَق


@_requires_fastapi
def test_route_plan_reads_ledger_when_depletion_absent(monkeypatch):
    """غياب initial_depletion + وجود صفّ دفتر ⇒ عمليّ بحقيقة الخادم، والمستأجِر من المستخدم."""
    import api.routers.irrigation_mpc as route

    async def _ledger(tenant_id, field_id):
        return 55.0

    monkeypatch.setattr(route, "_latest_ledger_depletion", _ledger)

    req = route.MpcPlanRequest(
        field_id="fld_a",
        forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
        taw_mm=100.0,
    )
    out = asyncio.run(route.irrigation_mpc_plan(req, user=_User()))
    assert out["depletion_source"] == "water_ledger"
    assert out["mode"] == "operational"
    assert out["decision"]["tenant_id"] == "tenant-42"  # من المستخدم لا الجسم


@_requires_fastapi
def test_route_plan_manual_depletion_is_simulation_and_submit_rejected(monkeypatch):
    """P1.1c: تمرير initial_depletion صراحةً ⇒ محاكاة؛ submit لا يُصدِر مرشّحاً محكوماً."""
    import api.routers.irrigation_mpc as route

    async def _ledger(tenant_id, field_id):
        raise AssertionError("must not read ledger when depletion is client-supplied")

    monkeypatch.setattr(route, "_latest_ledger_depletion", _ledger)
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")

    req = route.MpcPlanRequest(
        field_id="fld_a",
        forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
        taw_mm=100.0,
        initial_depletion_mm=40.0,  # حقيقة عميل ⇒ محاكاة
        submit=True,
    )
    out = asyncio.run(route.irrigation_mpc_plan(req, user=_User()))
    assert out["mode"] == "simulation"
    assert out["depletion_source"] == "request_simulation"
    assert out["emit"]["status"] == "rejected_simulation"  # لا مرشّح من محاكاة


@_requires_fastapi
def test_route_plan_rejects_illegal_bounds():
    """P1.1c: العقد يرفض القيم غير القانونيّة مبكّراً (422 عبر Pydantic)."""
    import api.routers.irrigation_mpc as route
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        route.MpcPlanRequest(
            field_id="fld_a",
            forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
            taw_mm=-5.0,  # TAW سالب ⇒ مرفوض
        )
    with pytest.raises(pydantic.ValidationError):
        route.ForecastDayIn(et0_mm=-1.0, kc=1.0)  # ET0 سالب ⇒ مرفوض
    with pytest.raises(pydantic.ValidationError):
        route.MpcPlanRequest(
            field_id="fld_a",
            forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
            taw_mm=100.0,
            raw_fraction=1.5,  # خارج (0,1] ⇒ مرفوض
        )


@_requires_fastapi
def test_route_plan_submit_without_bridge_is_disabled(monkeypatch):
    import api.routers.irrigation_mpc as route

    async def _ledger(tenant_id, field_id):
        return 45.0

    monkeypatch.setattr(route, "_latest_ledger_depletion", _ledger)
    monkeypatch.delenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", raising=False)

    req = route.MpcPlanRequest(
        field_id="fld_a",
        forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
        taw_mm=100.0,
        submit=True,
    )
    out = asyncio.run(route.irrigation_mpc_plan(req, user=_User()))
    assert out["emit"] == {"status": "disabled"}


@_requires_fastapi
def test_route_capabilities_no_private_leak():
    import api.routers.irrigation_mpc as route

    out = asyncio.run(route.irrigation_mpc_capabilities(user=_User()))
    assert out["execution_allowed"] is False
    assert out["recommendation_only"] is True
    assert "yield_ky_forecast_horizon" in out["modeled_capabilities"]
    assert "predicted_energy_kwh" in out["not_modeled"]


# ─────────────────── P1.1c-b: مصدرة الحقائق الخادميّة + فصل المسارات ───────────────────


@_requires_fastapi
def test_route_simulate_never_emits(monkeypatch):
    """/simulate بحقائق يدويّة ⇒ scenario، لا يُصدِر مرشّحاً محكوماً أبداً."""
    import api.routers.irrigation_mpc as route

    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")
    req = route.SimulateRequest(
        field_id="fld_a",
        forecast=[route.ForecastDayIn(et0_mm=10.0, kc=1.0)],
        taw_mm=100.0,
        initial_depletion_mm=45.0,
        crop="maize",
        growth_stage="flowering",
    )
    out = asyncio.run(route.irrigation_mpc_simulate(req, user=_User()))
    assert out["mode"] == "simulation"
    assert out["emit"]["status"] == "not_applicable_simulation"


@_requires_fastapi
def test_route_recommendation_blocks_on_missing_sor_facts(monkeypatch):
    """P1.1c-b: نقص أيّ حقيقة SoR ⇒ blocked مع قائمة الناقص (لا تلفيق)."""
    import api.routers.irrigation_mpc as route

    async def _owned(t, f):
        return True

    async def _state(t, f):
        return {"depletion_mm": 40.0, "stage": "flowering", "as_of": "2026-07-13"}

    async def _no_soil(t, f):
        return None  # TAW غير مُصدَّر

    async def _no_forecast(t, f, h):
        return None  # تنبّؤ غير مُصدَّر

    async def _no_bindings(t, f):
        return []  # H5.1: unbound field ⇒ no salinity limit, proceed to ground-truth checks

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _owned)
    monkeypatch.setattr(route, "_active_field_source_bindings", _no_bindings)
    monkeypatch.setattr(route, "_source_current_state", _state)
    monkeypatch.setattr(route, "_source_soil_capacity", _no_soil)
    monkeypatch.setattr(route, "_source_forecast_horizon", _no_forecast)

    req = route.RecommendationRequest(horizon_days=7)
    out = asyncio.run(route.irrigation_mpc_recommendation("fld_a", req, user=_User()))
    assert out["status"] == "blocked"
    assert out["reason"] == "insufficient_ground_truth"
    assert "taw(soil_profile)" in out["missing"]
    assert "forecast(weather_service)" in out["missing"]


@_requires_fastapi
def test_route_recommendation_blocks_on_unowned_field(monkeypatch):
    import api.routers.irrigation_mpc as route

    async def _not_owned(t, f):
        return False

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _not_owned)
    req = route.RecommendationRequest()
    out = asyncio.run(route.irrigation_mpc_recommendation("fld_x", req, user=_User()))
    assert out["status"] == "blocked"
    assert out["reason"] == "field_not_owned"


@_requires_fastapi
def test_route_recommendation_operational_with_full_sor_facts(monkeypatch):
    """كلّ الحقائق مُصدَّرة من SoR ⇒ عمليّ + بصمات لقطات + إصدار محكوم (جسر مموّه)."""
    import api.routers.irrigation_mpc as route

    async def _owned(t, f):
        return True

    async def _state(t, f):
        return {"depletion_mm": 45.0, "stage": "flowering", "as_of": "2026-07-13"}

    async def _soil(t, f):
        return {"taw_mm": 100.0, "raw_fraction": 0.5, "crop": "maize"}

    async def _forecast(t, f, h):
        return [{"et0_mm": 10.0, "kc": 1.0, "rain_mm": 0.0} for _ in range(h)]

    async def _no_bindings(t, f):
        return []  # H5.1: unbound field ⇒ no salinity limit to enforce

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _owned)
    monkeypatch.setattr(route, "_active_field_source_bindings", _no_bindings)
    monkeypatch.setattr(route, "_source_current_state", _state)
    monkeypatch.setattr(route, "_source_soil_capacity", _soil)
    monkeypatch.setattr(route, "_source_forecast_horizon", _forecast)
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")

    captured = {}

    async def _fake_record(payload, *, tenant_id=None):
        captured["payload"] = payload
        return {"persisted": True, "authoritative": True}

    import api.decision_service_client as dsc

    monkeypatch.setattr(dsc, "record_decision", _fake_record)

    req = route.RecommendationRequest(horizon_days=7, submit=True)
    out = asyncio.run(route.irrigation_mpc_recommendation("fld_a", req, user=_User()))
    assert out["mode"] == "operational"
    prov = out["facts_provenance"]
    assert prov["depletion_source"] == "water_ledger"
    assert prov["taw_source"] == "soil_profile"
    assert prov["forecast_source"] == "weather_service"
    # H5.1: unbound field is recorded honestly (governance not applicable, not enforced).
    assert prov["water_salinity"]["mode"] == "unbound_no_active_source_assignment"
    assert prov["water_salinity"]["enforced"] is False
    # بصمات لقطات كاملة (64-hex) — نَسَب لا يُزوَّر.
    assert len(prov["ledger_snapshot_hash"]) == 64
    assert len(prov["weather_snapshot_hash"]) == 64
    assert len(prov["soil_snapshot_hash"]) == 64
    # الإصدار العمليّ يمرّ للجسر (تنفيذ ممنوع بنيويّاً).
    assert out["emit"]["status"] == "candidate_created"
    assert out["emit"]["execution_allowed"] is False


@_requires_fastapi
def test_route_recommendation_blocks_on_server_bound_salinity(monkeypatch):
    """H5.1: a server-bound source whose gate blocks (e.g. only estimated sample) ⇒ blocked
    BEFORE any ground-truth read, with per-source verdicts and expert review — the source is
    derived from the binding, never from the client."""
    import api.routers.irrigation_mpc as route

    async def _owned(t, f):
        return True

    async def _bound_estimated(t, f):
        # One active bound source with a configured limit but no decision-grade sample.
        return [
            {
                "water_source_id": "src-1",
                "priority": 1,
                "mixing_ratio": None,
                "maximum_allowed_ec_ds_m": 3.0,
                "water_quality": None,
                "non_decision_grade_sample_present": True,
            }
        ]

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _owned)
    monkeypatch.setattr(route, "_active_field_source_bindings", _bound_estimated)

    req = route.RecommendationRequest(horizon_days=7)
    out = asyncio.run(route.irrigation_mpc_recommendation("fld_a", req, user=_User()))
    assert out["status"] == "blocked"
    assert out["reason"] == "water_salinity_gate_blocked"
    assert out["requires_expert_review"] is True
    verdict = out["source_verdicts"][0]
    assert verdict["water_source_id"] == "src-1"
    assert "WATER_QUALITY_NOT_DECISION_GRADE" in verdict["blocking_reasons"]


@_requires_fastapi
def test_route_recommendation_rejects_client_source_steering(monkeypatch):
    """H5.1: a client-supplied water_source_id that is NOT the field's active binding is rejected
    (anti-steering) — the client cannot point the gate at a cleaner source."""
    import api.routers.irrigation_mpc as route

    async def _owned(t, f):
        return True

    async def _bound_other(t, f):
        return [
            {
                "water_source_id": "real-src",
                "priority": 1,
                "mixing_ratio": None,
                "maximum_allowed_ec_ds_m": None,
                "water_quality": None,
                "non_decision_grade_sample_present": False,
            }
        ]

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _owned)
    monkeypatch.setattr(route, "_active_field_source_bindings", _bound_other)

    req = route.RecommendationRequest(horizon_days=7, water_source_id="attacker-picked-src")
    out = asyncio.run(route.irrigation_mpc_recommendation("fld_a", req, user=_User()))
    assert out["status"] == "blocked"
    assert out["reason"] == "water_source_binding_mismatch"


@_requires_fastapi
def test_snapshot_hash_deterministic_and_content_addressed():
    import api.routers.irrigation_mpc as route

    a = route._facts_snapshot_hash({"x": 1, "y": 2})
    b = route._facts_snapshot_hash({"y": 2, "x": 1})  # ترتيب مفاتيح مختلف
    c = route._facts_snapshot_hash({"x": 1, "y": 3})
    assert a == b  # canonical (sort_keys) ⇒ نفس البصمة
    assert a != c  # محتوى مختلف ⇒ بصمة مختلفة
    assert len(a) == 64
