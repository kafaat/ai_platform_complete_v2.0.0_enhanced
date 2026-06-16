"""اختبارات نقطة معاينة قرار التوزيع (routers/decision_dispatch) — استدعاء مباشر.

نختبر المعالِج مباشرةً (دالّة نقيّة: علم → check_guardrails → evaluate_dispatch)،
متفادين TestClient/المصادقة: العلم المُطفأ ⇒ 404؛ المُفعَّل ⇒ قرار صحيح (HALT يحجب،
الموافقة تُخلّص)، مع أثر dry_run/evaluated_by. لا تنفيذ، لا قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main كاملةً قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.decision_dispatch import (
    DispatchEvaluateRequest,
    evaluate_dispatch_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-eval",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُعايِن",
)


def _req(**kw):
    base = dict(recommendation_id="rec1", action_type="irrigation", risk_level="LOW")
    base.update(kw)
    return DispatchEvaluateRequest(**base)


def test_flag_off_returns_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        evaluate_dispatch_endpoint(req=_req(), user=_USER)
    assert e.value.status_code == 404


def test_flag_on_low_risk_ready(monkeypatch):
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")
    out = evaluate_dispatch_endpoint(req=_req(risk_level="LOW"), user=_USER)
    assert out["state"] == "ready"
    assert out["executable"] is True
    assert out["dry_run"] is True
    assert out["evaluated_by"] == "u-eval"


def test_flag_on_pesticide_phi_blocks(monkeypatch):
    # PHI غير مُستوفى ⇒ خرق HALT ⇒ BLOCKED مهما كانت الموافقات.
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "1")
    out = evaluate_dispatch_endpoint(
        req=_req(risk_level="LOW", pesticide_phi_satisfied=False, approvals_collected=99),
        user=_USER,
    )
    assert out["state"] == "blocked"
    assert out["executable"] is False
    assert "pesticide_phi" in out["halt_breaches"]


def test_flag_on_medium_pending_then_ready(monkeypatch):
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "yes")
    pending = evaluate_dispatch_endpoint(
        req=_req(action_type="fertilize", risk_level="MEDIUM", approvals_collected=0), user=_USER
    )
    assert pending["state"] == "pending_approval"
    ready = evaluate_dispatch_endpoint(
        req=_req(action_type="fertilize", risk_level="MEDIUM", approvals_collected=1), user=_USER
    )
    assert ready["state"] == "ready"


def test_flag_on_salinity_halt_via_guardrails(monkeypatch):
    # ملوحة تتجاوز عتبة المحصول بشدّة ⇒ HALT من check_guardrails ⇒ BLOCKED.
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "on")
    out = evaluate_dispatch_endpoint(
        req=_req(risk_level="HIGH", soil_ec_ds_m=12.0, crop_salinity_threshold_ds_m=4.0),
        user=_USER,
    )
    assert out["state"] == "blocked"
    assert any("salinity" in b for b in out["halt_breaches"])


async def test_execute_flag_off_returns_404(monkeypatch):
    # نقطة التنفيذ محروسة بنفس العلم — مُطفأة ⇒ 404 قبل أيّ قاعدة.
    from api.routers.decision_dispatch import DispatchExecuteRequest, execute_dispatch_endpoint

    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    req = DispatchExecuteRequest(recommendation_id="r", action_type="irrigation", risk_level="LOW")
    with pytest.raises(HTTPException) as e:
        await execute_dispatch_endpoint(req=req, user=_USER)
    assert e.value.status_code == 404


def test_shape_dispatch_row_decodes_jsonb_and_time():
    from datetime import UTC, datetime

    from api.routers.decision_dispatch import _shape_dispatch_row

    row = {
        "decision_id": "disp_1",
        "recommendation_id": "rec-9",
        "action_type": "irrigation",
        "field_id": "fld_1",
        "state": "ready",
        "risk_level": "LOW",
        "required_approvals": 0,
        "approvals_collected": 0,
        "halt_breaches": "[]",  # JSONB كنصّ خام من asyncpg
        "warn_breaches": '["salinity_high"]',
        "reason_ar": "محروس",
        "command": '{"device_id": "d1", "command": "open_valve"}',
        "exec_status": "queued",
        "created_by": "u1",
        "created_at": datetime(2026, 6, 16, 12, 0, tzinfo=UTC),
    }
    out = _shape_dispatch_row(row)
    assert out["warn_breaches"] == ["salinity_high"]
    assert out["halt_breaches"] == []
    assert out["command"]["command"] == "open_valve"
    assert out["created_at"].startswith("2026-06-16T12:00")
    # قيمة list أصلاً (لا نصّ) تمرّ كما هي
    row2 = dict(row, warn_breaches=["x"], command=None)
    out2 = _shape_dispatch_row(row2)
    assert out2["warn_breaches"] == ["x"]
    assert out2["command"] is None


def test_unified_flag_off_returns_404(monkeypatch):
    from api.routers.decision_dispatch import (
        UnifiedDecisionRequest,
        unified_decision_endpoint,
    )

    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    req = UnifiedDecisionRequest(field_id="f1", signals=[])
    with pytest.raises(HTTPException) as e:
        unified_decision_endpoint(req=req, user=_USER)
    assert e.value.status_code == 404


def test_unified_reconciles_irrigation_vs_spray(monkeypatch):
    from api.routers.decision_dispatch import (
        DomainSignalIn,
        UnifiedDecisionRequest,
        unified_decision_endpoint,
    )

    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")
    req = UnifiedDecisionRequest(
        field_id="f1",
        signals=[
            DomainSignalIn(
                domain="irrigation", action="irrigate", urgency="high", params={"water_mm": 20.0}
            ),
            DomainSignalIn(
                domain="pest",
                action="spray",
                urgency="medium",
                params={"needs_dry": True, "window_days": 3},
            ),
            DomainSignalIn(
                domain="economics", action="reduce_water", params={"water_budget_pct": 80.0}
            ),
        ],
    )
    out = unified_decision_endpoint(req=req, user=_USER)
    assert out["state"] == "ready"
    assert out["dry_run"] is True
    assert out["reconciled_by"] == "u-eval"
    irr = next(a for a in out["action_plan"] if "irrig" in a["action"])
    assert irr["action"] == "defer_irrigation"
    assert irr["params"]["defer_hours"] == 24
    assert irr["params"]["water_mm"] == 16.0  # 20 * 0.80
    assert len(out["reconciliations_ar"]) == 2


def test_unified_halt_blocks(monkeypatch):
    from api.routers.decision_dispatch import (
        DomainSignalIn,
        UnifiedDecisionRequest,
        unified_decision_endpoint,
    )

    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "1")
    req = UnifiedDecisionRequest(
        field_id="f1",
        signals=[
            DomainSignalIn(domain="pest", action="spray", urgency="high"),
            DomainSignalIn(domain="governance", action="none", halt=True, reason_ar="PHI"),
        ],
    )
    out = unified_decision_endpoint(req=req, user=_USER)
    assert out["state"] == "blocked"
    assert out["action_plan"] == []
    assert "PHI" in out["halt_reasons"]


async def test_read_endpoints_flag_off_404(monkeypatch):
    from api.routers.decision_dispatch import list_dispatch_decisions, list_dispatch_queue

    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e1:
        await list_dispatch_decisions(field_id=None, limit=50, user=_USER)
    assert e1.value.status_code == 404
    with pytest.raises(HTTPException) as e2:
        await list_dispatch_queue(limit=50, user=_USER)
    assert e2.value.status_code == 404
