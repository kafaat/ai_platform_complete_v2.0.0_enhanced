"""api/routers/irrigation_mpc.py — نقطة متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC).

P1.1b: أوّل **مستهلك إنتاجيّ** لـ`solve_lexicographic_irrigation` — يقرأ حقيقة الخادم
(أحدث استنزاف من `water_ledger`) عند غيابها، يحلّ القرار المعجميّ، ويعيده كاملاً بنَسَبه
(`content_digest`/`idempotency_key`/`objective_trace`). **توصية-فقط**: لا أمر مضخّة؛
`submit=true` (خلف عَلَم الجسر) يُصدِر مرشّحاً محكوماً إلى مركز القرار فقط.

`tenant_id` من المستخدم المُصادَق (لا من الجسم) — عزل المستأجِر. الحساب نقيّ فيُختبَر
باستدعاء المعالِج؛ قراءة الدفتر دفاعيّة (بلا صفّ ⇒ استنزاف 0 + data_degraded، لا اختلاق).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.irrigation_mpc import ForecastDay
from api.lexicographic_irrigation_mpc import solve_lexicographic_irrigation
from api.lexicographic_mpc_bridge import bridge_enabled, emit_mpc_candidate
from api.main import UserSchema, get_current_user, tenant_connection

router = APIRouter()
logger = logging.getLogger("sahool.irrigation_mpc")


class ForecastDayIn(BaseModel):
    et0_mm: float
    kc: float
    rain_mm: float = 0.0
    runoff_mm: float = 0.0


class MpcPlanRequest(BaseModel):
    """مدخلات خطّة الريّ المعجميّة (الحقائق تُمرَّر أو تُقرأ من الدفتر)."""

    field_id: str
    forecast: list[ForecastDayIn] = Field(min_length=1)
    taw_mm: float
    raw_fraction: float = 0.5
    initial_depletion_mm: float | None = None  # يُقرأ من water_ledger عند الغياب
    season_id: str | None = None
    crop: str | None = None
    growth_stage: str | None = None
    yield_floor_ratio: float | None = None
    max_application_mm: float | None = None
    season_budget_mm: float | None = None
    water_price_per_m3: float | None = None
    depletion_confidence: float | None = None
    submit: bool = False  # إصدار مرشّح محكوم (خلف عَلَم الجسر)


async def _latest_ledger_depletion(tenant_id: str, field_id: str) -> float | None:
    """أحدث استنزاف Dr من water_ledger (حقيقة الخادم). None إن لا صفّ/تعذّر."""
    try:
        async with tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT depletion_mm FROM water_ledger WHERE field_id=$1 "
                "ORDER BY ledger_date DESC LIMIT 1",
                field_id,
            )
        return None if row is None or row["depletion_mm"] is None else float(row["depletion_mm"])
    except Exception:  # قراءة دفاعيّة — لا نفشل النقطة على غياب/عطل الدفتر
        logger.warning("water_ledger read failed for field=%s", field_id, exc_info=True)
        return None


@router.post("/api/v1/irrigation/mpc/plan")
async def irrigation_mpc_plan(
    req: MpcPlanRequest, user: UserSchema = Depends(get_current_user)
) -> dict:
    tenant_id = user.tenant_id
    data_degraded = False
    depletion = req.initial_depletion_mm
    if depletion is None:
        depletion = await _latest_ledger_depletion(tenant_id, req.field_id)
        if depletion is None:
            depletion = 0.0  # لا اختلاق: استنزاف مجهول ⇒ 0 + تدهور بيانات مُعلَن
            data_degraded = True

    decision = solve_lexicographic_irrigation(
        forecast=[
            ForecastDay(et0_mm=d.et0_mm, kc=d.kc, rain_mm=d.rain_mm, runoff_mm=d.runoff_mm)
            for d in req.forecast
        ],
        taw_mm=req.taw_mm,
        raw_fraction=req.raw_fraction,
        initial_depletion_mm=depletion,
        tenant_id=tenant_id,
        field_id=req.field_id,
        season_id=req.season_id,
        crop=req.crop,
        growth_stage=req.growth_stage,
        yield_floor_ratio=req.yield_floor_ratio,
        max_application_mm=req.max_application_mm,
        season_budget_mm=req.season_budget_mm,
        water_price_per_m3=req.water_price_per_m3,
        depletion_confidence=req.depletion_confidence,
        data_degraded=data_degraded,
    )

    out: dict = {
        "decision": decision.to_dict(),
        "depletion_source": (
            "request"
            if req.initial_depletion_mm is not None
            else ("water_ledger" if not data_degraded else "absent_bootstrap")
        ),
    }

    if req.submit:
        if not bridge_enabled():
            out["emit"] = {"status": "disabled"}
        else:
            out["emit"] = await emit_mpc_candidate(decision, tenant_id=tenant_id)
    return out


@router.get("/api/v1/irrigation/mpc/capabilities")
async def irrigation_mpc_capabilities(user: UserSchema = Depends(get_current_user)) -> dict:
    """شفافيّة القدرات المُنمذَجة/المُؤجَّلة — لا حساب."""
    from api.lexicographic_irrigation_mpc import (
        MODELED_CAPABILITIES,
        NOT_MODELED,
        SOLVER_VERSION,
    )

    return {
        "solver_version": SOLVER_VERSION,
        "modeled_capabilities": list(MODELED_CAPABILITIES),
        "not_modeled": list(NOT_MODELED),
        "execution_allowed": False,
        "recommendation_only": True,
    }
