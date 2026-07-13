"""api/routers/irrigation_mpc.py — نقطة متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC).

P1.1b: أوّل **مستهلك إنتاجيّ** لـ`solve_lexicographic_irrigation` — يقرأ حقيقة الخادم
(أحدث استنزاف من `water_ledger`) عند غيابها، يحلّ القرار المعجميّ، ويعيده كاملاً بنَسَبه
(`content_digest`/`idempotency_key`/`objective_trace`). **توصية-فقط**: لا أمر مضخّة؛
`submit=true` (خلف عَلَم الجسر) يُصدِر مرشّحاً محكوماً إلى مركز القرار فقط.

`tenant_id` من المستخدم المُصادَق (لا من الجسم) — عزل المستأجِر. الحساب نقيّ فيُختبَر
باستدعاء المعالِج.

**P1.1c (تصلّب fail-closed + فصل المحاكاة/العمليّ):** تمرير `initial_depletion_mm` صريحاً
⇒ **محاكاة** (حقيقة عميل) لا تُصدَر مرشّحاً محكوماً. غيابه ⇒ يُقرأ Dr من `water_ledger`
(حقيقة الخادم) = **عمليّ** قابل للإصدار؛ وغياب صفّ الدفتر ⇒ **blocked** (لا اختلاق Dr=0).
حدود صارمة على العقد (422 على القيم السالبة/خارج المدى).

**P1.1c-b (مصدرة الحقائق الخادميّة + فصل المسارات):** مساران منفصلان —
`POST /api/v1/irrigation/mpc/simulate` (حقائق يدويّة، scenario، لا يُصدِر أبداً) و
`POST /api/v1/fields/{field_id}/irrigation/mpc/recommendation` (توصية عمليّة: **لا حقائق
عميل** — Dr+المرحلة من water_ledger، TAW من التربة، التنبّؤ من الطقس؛ نقص أيّ حقيقة ⇒
blocked؛ تحقّق ملكيّة الحقل؛ بصمات لقطات لكلّ مصدر). المسار القديم `/plan` يبقى للتوافق.
**متبقٍّ (مُعلَن، staging):** وصل مصدرَي soil/weather الفعليَّين (هنا fail-closed stubs) +
شهادة PostgreSQL للسلسلة حتى outcome — فتفعيل الجسر يبقى غير جاهز للإنتاج حتى ذلك.
"""

from __future__ import annotations

import hashlib
import json
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
    # حدود صارمة على العقد (422 مبكّراً بدل تمرير قيم فيزيائيّة غير قانونيّة للنواة).
    et0_mm: float = Field(ge=0)
    kc: float = Field(ge=0)
    rain_mm: float = Field(default=0.0, ge=0)
    runoff_mm: float = Field(default=0.0, ge=0)


class MpcPlanRequest(BaseModel):
    """مدخلات خطّة الريّ المعجميّة.

    **دلالة المدخلات (P1.1c):** تمرير `initial_depletion_mm` صريحاً ⇒ **محاكاة** (حقيقة
    عميل، لا تُصدِر مرشّحاً محكوماً). غيابه ⇒ يُقرأ Dr من `water_ledger` (حقيقة الخادم) =
    **عمليّ** قابل للإصدار؛ وغياب صفّ الدفتر ⇒ **fail-closed** (لا اختلاق صفر). الحدود
    الصارمة أدناه ترفض القيم غير القانونيّة بـ422.
    """

    field_id: str = Field(min_length=1)
    forecast: list[ForecastDayIn] = Field(min_length=1)
    taw_mm: float = Field(gt=0)
    raw_fraction: float = Field(default=0.5, gt=0, le=1)
    initial_depletion_mm: float | None = Field(default=None, ge=0)  # مُمرَّراً ⇒ محاكاة
    season_id: str | None = None
    crop: str | None = None
    growth_stage: str | None = None
    yield_floor_ratio: float | None = Field(default=None, ge=0, le=1)
    max_application_mm: float | None = Field(default=None, ge=0)
    season_budget_mm: float | None = Field(default=None, ge=0)
    water_price_per_m3: float | None = Field(default=None, ge=0)
    depletion_confidence: float | None = Field(default=None, ge=0, le=1)
    submit: bool = False  # إصدار مرشّح محكوم (عمليّ فقط، خلف عَلَم الجسر)


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
    # P1.1c: فصل المحاكاة عن العمليّ + fail-closed على غياب الحقيقة (لا اختلاق Dr=0).
    manual_depletion = req.initial_depletion_mm is not None
    if manual_depletion:
        depletion = float(req.initial_depletion_mm)  # حقيقة عميل ⇒ محاكاة
        depletion_source = "request_simulation"
    else:
        ledger_dr = await _latest_ledger_depletion(tenant_id, req.field_id)
        if ledger_dr is None:
            # fail-closed: لا استنزاف مرجعيّ ⇒ لا صفر مُختلَق ولا قرار قابل للإرسال.
            return {
                "status": "blocked",
                "reason": "no_ground_truth_depletion",
                "field_id": req.field_id,
                "detail": (
                    "لا استنزاف Dr مرجعيّ من water_ledger لهذا الحقل؛ لا يُختلَق صفر لقرار "
                    "قابل للإرسال. شغّل عامل ميزان الماء، أو مرّر initial_depletion_mm صراحةً "
                    "كمحاكاة (لا تُصدَر مرشّحاً محكوماً)."
                ),
            }
        depletion = ledger_dr
        depletion_source = "water_ledger"

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
        data_degraded=False,
    )

    # وضع صريح: المحاكاة (حقائق عميل) لا تُصدَر مرشّحاً محكوماً؛ العمليّ (حقيقة خادم) يُصدَر.
    mode = "simulation" if manual_depletion else "operational"
    out: dict = {"decision": decision.to_dict(), "depletion_source": depletion_source, "mode": mode}

    if req.submit:
        if manual_depletion:
            out["emit"] = {
                "status": "rejected_simulation",
                "detail": (
                    "لا يُصدَر مرشّح محكوم من محاكاة (حقائق عميل). الإصدار العمليّ يتطلّب "
                    "استنزافاً مرجعيّاً من الخادم (water_ledger)."
                ),
            }
        elif not bridge_enabled():
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


# ═══════════════════ P1.1c-b: مصدرة الحقائق الخادميّة + فصل المسارات ═══════════════════
# التوصية العمليّة تُبنى **فقط** من حقائق SoR خادميّاً (لا حقائق عميل): Dr+المرحلة من
# water_ledger، TAW من ملفّ التربة، التنبّؤ من خدمة الطقس. أيّ حقيقة ناقصة ⇒ **blocked**
# (لا تلفيق). كلّ مصدر يحمل بصمة لقطة (snapshot hash) للنَّسَب. المصدران غير الموصولَين
# خادميّاً هنا (soil/weather) يُرجعان None افتراضيّاً (fail-closed) ويُوصَلان في staging؛
# الاختبارات تحقنهما لإثبات مسار الحقائق الكاملة. (بديل يدويّ صريح: /simulate.)


def _facts_snapshot_hash(facts: object) -> str:
    """بصمة sha256 كاملة على canonical-JSON للقطة حقائق (نَسَب لا يُزوَّر)."""
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


async def _field_belongs_to_tenant(tenant_id: str, field_id: str) -> bool:
    """تحقّق ملكيّة الحقل للمستأجِر (RLS يحصر النطاق). fail-closed عند تعذّر القراءة."""
    try:
        async with tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow("SELECT 1 FROM fields WHERE field_id=$1", field_id)
        return row is not None
    except Exception:
        logger.warning("fields ownership read failed for field=%s", field_id, exc_info=True)
        return False  # fail-closed: لا نؤكّد الملكيّة ⇒ نمنع


async def _source_current_state(tenant_id: str, field_id: str) -> dict | None:
    """Dr + المرحلة من أحدث صفّ water_ledger (حقيقة الخادم). None إن لا صفّ صالح."""
    try:
        async with tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT depletion_mm, stage, ledger_date FROM water_ledger "
                "WHERE field_id=$1 ORDER BY ledger_date DESC LIMIT 1",
                field_id,
            )
        if row is None or row["depletion_mm"] is None:
            return None
        return {
            "depletion_mm": float(row["depletion_mm"]),
            "stage": row["stage"],
            "as_of": str(row["ledger_date"]),
        }
    except Exception:
        logger.warning("water_ledger state read failed for field=%s", field_id, exc_info=True)
        return None


async def _source_soil_capacity(tenant_id: str, field_id: str) -> dict | None:
    """TAW/RAW من ملفّ التربة SoR — غير موصول خادميّاً هنا (staging). fail-closed None.

    يُعاد ربطه بـsoil-service في staging؛ الاختبارات تحقن {"taw_mm":..., "raw_fraction":...}.
    """
    return None


async def _source_forecast_horizon(
    tenant_id: str, field_id: str, horizon_days: int
) -> list[dict] | None:
    """تنبّؤ (et0/kc/rain) من خدمة الطقس SoR — غير موصول خادميّاً هنا (staging). fail-closed.

    يُعاد ربطه بـweather-service في staging؛ الاختبارات تحقن قائمة أيّام التنبّؤ.
    """
    return None


class SimulateRequest(MpcPlanRequest):
    """محاكاة صريحة: نفس مدخلات الخطّة (حقائق يدويّة). لا تُصدَر مرشّحاً محكوماً أبداً."""


class RecommendationRequest(BaseModel):
    """توصية عمليّة: **لا حقائق فيزيائيّة من العميل** — تُصدَر كلّها من SoR خادميّاً."""

    season_id: str | None = None
    horizon_days: int = Field(default=7, ge=1, le=14)
    raw_fraction: float = Field(default=0.5, gt=0, le=1)  # نسبة RAW (خاصّيّة تربة)
    yield_floor_ratio: float | None = Field(default=None, ge=0, le=1)
    max_application_mm: float | None = Field(default=None, ge=0)
    season_budget_mm: float | None = Field(default=None, ge=0)
    water_price_per_m3: float | None = Field(default=None, ge=0)
    submit: bool = False


@router.post("/api/v1/irrigation/mpc/simulate")
async def irrigation_mpc_simulate(
    req: SimulateRequest, user: UserSchema = Depends(get_current_user)
) -> dict:
    """محاكاة صريحة بحقائق يدويّة — **لا تُصدَر مرشّحاً محكوماً** (scenario فقط)."""
    tenant_id = user.tenant_id
    decision = solve_lexicographic_irrigation(
        forecast=[
            ForecastDay(et0_mm=d.et0_mm, kc=d.kc, rain_mm=d.rain_mm, runoff_mm=d.runoff_mm)
            for d in req.forecast
        ],
        taw_mm=req.taw_mm,
        raw_fraction=req.raw_fraction,
        initial_depletion_mm=float(req.initial_depletion_mm or 0.0),
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
        data_degraded=req.initial_depletion_mm is None,  # بلا Dr صريح ⇒ تدهور مُعلَن
    )
    return {
        "decision": decision.to_dict(),
        "mode": "simulation",
        "emit": {"status": "not_applicable_simulation"},
    }


@router.post("/api/v1/fields/{field_id}/irrigation/mpc/recommendation")
async def irrigation_mpc_recommendation(
    field_id: str, req: RecommendationRequest, user: UserSchema = Depends(get_current_user)
) -> dict:
    """توصية عمليّة قابلة للإصدار — كلّ الحقائق من SoR خادميّاً، fail-closed على النقص.

    يتحقّق من ملكيّة الحقل؛ يُصدِر Dr+المرحلة من water_ledger، TAW من التربة، التنبّؤ من
    الطقس؛ أيّ نقص ⇒ blocked (لا تلفيق). بصمات لقطات لكلّ مصدر (نَسَب). submit خلف عَلَم الجسر.
    """
    tenant_id = user.tenant_id
    if not await _field_belongs_to_tenant(tenant_id, field_id):
        return {"status": "blocked", "reason": "field_not_owned", "field_id": field_id}

    state = await _source_current_state(tenant_id, field_id)
    soil = await _source_soil_capacity(tenant_id, field_id)
    forecast = await _source_forecast_horizon(tenant_id, field_id, req.horizon_days)

    missing = []
    if not state:
        missing.append("depletion+stage(water_ledger)")
    if not soil or "taw_mm" not in soil:
        missing.append("taw(soil_profile)")
    if not forecast:
        missing.append("forecast(weather_service)")
    if missing:
        return {
            "status": "blocked",
            "reason": "insufficient_ground_truth",
            "field_id": field_id,
            "missing": missing,
            "detail": (
                "لا تُبنى توصية عمليّة إلّا من حقائق SoR كاملة (لا حقائق عميل). استعمل "
                "/simulate للمحاكاة اليدويّة، أو شغّل مصادر الحقائق الناقصة."
            ),
        }

    ledger_snapshot_hash = _facts_snapshot_hash(state)
    weather_snapshot_hash = _facts_snapshot_hash(forecast)
    soil_snapshot_hash = _facts_snapshot_hash(soil)

    decision = solve_lexicographic_irrigation(
        forecast=[
            ForecastDay(
                et0_mm=float(d["et0_mm"]),
                kc=float(d["kc"]),
                rain_mm=float(d.get("rain_mm", 0.0)),
                runoff_mm=float(d.get("runoff_mm", 0.0)),
            )
            for d in forecast
        ],
        taw_mm=float(soil["taw_mm"]),
        raw_fraction=float(soil.get("raw_fraction", req.raw_fraction)),
        initial_depletion_mm=float(state["depletion_mm"]),
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=req.season_id,
        crop=soil.get("crop"),
        growth_stage=state.get("stage"),
        yield_floor_ratio=req.yield_floor_ratio,
        max_application_mm=req.max_application_mm,
        season_budget_mm=req.season_budget_mm,
        water_price_per_m3=req.water_price_per_m3,
        depletion_confidence=None,
        data_degraded=False,
    )

    out: dict = {
        "decision": decision.to_dict(),
        "mode": "operational",
        "facts_provenance": {
            "depletion_source": "water_ledger",
            "stage_source": "water_ledger",
            "taw_source": "soil_profile",
            "forecast_source": "weather_service",
            "as_of": state.get("as_of"),
            "ledger_snapshot_hash": ledger_snapshot_hash,
            "weather_snapshot_hash": weather_snapshot_hash,
            "soil_snapshot_hash": soil_snapshot_hash,
        },
    }
    if req.submit:
        if not bridge_enabled():
            out["emit"] = {"status": "disabled"}
        else:
            out["emit"] = await emit_mpc_candidate(decision, tenant_id=tenant_id)
    return out
