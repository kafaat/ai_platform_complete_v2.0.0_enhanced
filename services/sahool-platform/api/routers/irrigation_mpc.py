"""api/routers/irrigation_mpc.py — نقطة متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC).

المساران `/plan` و`/simulate` يقبلان حقائق العميل، ولذلك يعيدان محاكاة فقط ولا
يُصدران مرشّحاً محكوماً، حتى عند قراءة استنزاف البداية من `water_ledger`.
مصدر Dr الخادمي لا يغيّر مصدر TAW والطقس وبقيّة حقائق العميل.

`tenant_id` من المستخدم المُصادَق (لا من الجسم) — عزل المستأجِر. الحساب نقيّ فيُختبَر
باستدعاء المعالِج.

غياب `initial_depletion_mm` في `/plan` يسمح بقراءة Dr كبداية للمحاكاة فقط؛
وغياب صفّ الدفتر ⇒ **blocked** (لا اختلاق Dr=0).
حدود صارمة على العقد (422 على القيم السالبة/خارج المدى).

**P1.1c-b (مصدرة الحقائق الخادميّة + فصل المسارات):** مساران منفصلان —
`POST /api/v1/irrigation/mpc/simulate` (حقائق يدويّة، scenario، لا يُصدِر أبداً) و
`POST /api/v1/fields/{field_id}/irrigation/mpc/recommendation` (توصية عمليّة: **لا حقائق
عميل** — كلُّها من `resolve_canonical_water_state`؛ نقص أيّ دليل ⇒ blocked بسببٍ مُسمّى؛
تحقّق ملكيّة الحقل؛ بصماتُ لقطة المُنتِج نفسِه). المسار القديم `/plan` يبقى للتوافق.

**والوصلُ تمّ:** كان مصدرا التربة والطقس هنا `return None` بلا شرط، فتُرجِع هذه النقطةُ
`insufficient_ground_truth` **دائماً** ولا تُختبَر إلّا بحقن — أي أنّ البابَ المُحكَم كان
مقفلاً بنيويّاً والمفتوحَ الوحيدَ هو `/plan` الذي لا يفحص شيئاً. المُنتِجُ القانونيّ كان
قائماً ويستهلكه المسارُ الساعيُّ فعلاً، فوُصِل بالمستهلِك المُعطَّل.
**ويبقى غيرَ مقيس:** شهادةُ PostgreSQL للسلسلة حتّى outcome.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.canonical_water_state import CanonicalWaterState, resolve_canonical_water_state
from api.canonical_well_capability import evaluate_water_salinity_gate
from api.irrigation_mpc import ForecastDay
from api.irrigation_runtime_orchestrator import orchestrate_irrigation_recommendation
from api.irrigation_source_binding import resolve_active_bindings
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

    جميع هذه المدخلات للمحاكاة فقط. عند غياب `initial_depletion_mm` يُقرأ Dr من
    `water_ledger` كبداية للمحاكاة، ويُحجب الحساب إن غاب صفّ الدفتر. مدخلات TAW والطقس
    تبقى حقائق عميل، ولا يُسمح بإصدار مرشّح منها. الحدود أدناه تُفرَض بـ422.
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
    submit: bool = False  # Legacy compatibility: simulation submissions are rejected.


async def _latest_ledger_depletion(user: UserSchema, field_id: str) -> float | None:
    """أحدث استنزاف Dr من water_ledger (حقيقة الخادم). None إن لا صفّ/تعذّر."""
    try:
        async with tenant_connection(user) as conn:
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
    # The entire request remains a simulation, including when only Dr is server-owned.
    manual_depletion = req.initial_depletion_mm is not None
    if manual_depletion:
        depletion = float(req.initial_depletion_mm)  # حقيقة عميل ⇒ محاكاة
        depletion_source = "request_simulation"
    else:
        ledger_dr = await _latest_ledger_depletion(user, req.field_id)
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

    out: dict = {
        "decision": decision.to_dict(),
        "depletion_source": depletion_source,
        "mode": "simulation",
        "execution_allowed": False,
        "recommendation_only": True,
    }

    if req.submit:
        out["emit"] = {
            "status": "rejected_simulation",
            "detail": (
                "لا يُصدَر مرشّح محكوم من محاكاة. استخدم مسار التوصية الخادمي الذي "
                "يتحقق من جميع الحقائق؛ قراءة Dr من water_ledger وحدها لا تكفي."
            ),
        }
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
# التوصية العمليّة تُبنى **فقط** من حقائق SoR خادميّاً (لا حقائق عميل)، ومن **لقطةٍ
# واحدة متّسقة**: `resolve_canonical_water_state` يُصدِر الاستنزافَ والمرحلة وTAW/RAW
# والتنبّؤ معاً ببصماتها. نقصُ أيّ دليل ⇒ **blocked** بسببٍ يُسمّي الناقص (لا تلفيق)،
# و`operational_eligible=False` ⇒ blocked أيضاً: حكمُ المُنتِج على صلاحيّة لقطتِه
# للتشغيل، وتجاهلُه يُعيد ما أُزيل من `/plan` — سلطةً أقوى من دليلها.


def _facts_snapshot_hash(facts: object) -> str:
    """بصمة sha256 كاملة على canonical-JSON للقطة حقائق (نَسَب لا يُزوَّر)."""
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


async def _field_belongs_to_tenant(user: UserSchema, field_id: str) -> bool:
    """تحقّق ملكيّة الحقل للمستأجِر (RLS يحصر النطاق). fail-closed عند تعذّر القراءة."""
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow("SELECT 1 FROM fields WHERE field_id=$1", field_id)
        return row is not None
    except Exception:
        logger.warning("fields ownership read failed for field=%s", field_id, exc_info=True)
        return False  # fail-closed: لا نؤكّد الملكيّة ⇒ نمنع


async def _source_current_state(user: UserSchema, field_id: str) -> dict | None:
    """Dr + المرحلة من أحدث صفّ water_ledger (حقيقة الخادم). None إن لا صفّ صالح."""
    try:
        async with tenant_connection(user) as conn:
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


async def _source_canonical_water(
    user: UserSchema, field_id: str, horizon_days: int
) -> CanonicalWaterState | dict | None:
    """حالةُ الماء القانونيّة: مصدرُ TAW/RAW والتنبّؤ والاستنزاف معاً.

    حلّت محلّ `_source_soil_capacity` و`_source_forecast_horizon` اللتين كانتا
    `return None` **بلا شرط**، فكانت هذه النقطةُ المُحكَمة تُرجِع
    `insufficient_ground_truth` دائماً ولا تُختبَر إلّا بحقنٍ في الاختبارات — أي أنّ
    البابَ المُحكَم كان مقفلاً بنيويّاً والبابُ الوحيدُ المفتوح هو الذي لا يفحص شيئاً.

    والمُنتِجُ لم يُبنَ هنا: `resolve_canonical_water_state` قائمٌ ويستهلكه المسارُ
    الساعيُّ فعلاً عبر `irrigation_runtime_orchestrator`. المطلوبُ كان وصلَ المُنتِج
    القائم بالمستهلِك المُعطَّل لا مصدراً جديداً.

    ومصدرٌ **واحد** لا ثلاثة: TAW والتنبّؤ والاستنزاف تُشتقّ من لقطةٍ واحدة متّسقة
    ببصماتها، فلا يُركَّب قرارٌ من مصادر التقطت لحظاتٍ مختلفة.
    """
    async with tenant_connection(user) as conn:
        return await resolve_canonical_water_state(
            conn,
            tenant_id=user.tenant_id,
            field_id=field_id,
            horizon_days=horizon_days,
        )


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
    # H5.1: مصدر الماء **مُشتَقّ من الخادم** من جدول الوصل field_irrigation_source_assignments،
    # لا من العميل. هذا الحقل اختياريّ وإرشاديّ فقط: إن مُرِّر ولم يطابق ربط الحقل النشِط ⇒ block
    # (منع توجيه)؛ لا يمكن استخدامه لتجاوز البوّابة ولا لتوجيهها لمصدر أنظف.
    water_source_id: str | None = None
    submit: bool = False


async def _active_field_source_bindings(user: UserSchema, field_id: str) -> list[dict] | None:
    """ربط الحقل بمصادر الماء النشِطة خادميّاً (H5.1) — يُشتَقّ المصدر من SoR لا من العميل.

    يفتح اتّصالاً مقيَّداً بالمستأجِر (RLS عبر app.current_tenant) ويستدعي المُحلِّل النقيّ
    `resolve_active_bindings` (الذي يملك SQL جدول الوصل `field_irrigation_source_assignments`
    + سياسة انتقاء عيّنة قرار-درجة من `irrigation_water_quality_samples`، مربوطة بحدّ
    `irrigation_water_sources.maximum_allowed_ec_ds_m`). يُعيد None عند تعذّر القراءة (⇒
    fail-closed: لا نؤكّد حدّ الملوحة فلا نوصي)؛ قائمة فارغة = لا ربط نشِط لهذا الحقل.
    """
    try:
        async with tenant_connection(user) as conn:
            return await resolve_active_bindings(conn, field_id, now=datetime.now(UTC))
    except Exception:
        logger.warning(
            "active water-source bindings read failed for field=%s", field_id, exc_info=True
        )
        return None  # fail-closed: تعذّر التحقّق ⇒ لا توصية


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
    if not await _field_belongs_to_tenant(user, field_id):
        return {"status": "blocked", "reason": "field_not_owned", "field_id": field_id}

    # H5.1: بوّابة ملوحة fail-closed مبكّرة، **مصدرها مُشتَقّ من الخادم** — قبل أيّ حساب.
    # يُحلّ المصدر (المصادر) النشِط للحقل من جدول الوصل الخادميّ لا من قيمة العميل، فلا يستطيع
    # العميل التوجيه لمصدر أنظف (mismatch ⇒ block) ولا تجاوز البوّابة بحذف water_source_id.
    # لكلّ مصدر نشِط تُقيَّم البوّابة على عيّنة **قرار-درجة** (estimated/measured مرفوضة)؛ ECw>الحدّ
    # أو لا عيّنة قرار-درجة أو عيّنة قديمة ⇒ blocked. الخلط: تُحجب التوصية إن حُجِب أيّ مصدر.
    salinity_provenance: dict | None = None
    bindings = await _active_field_source_bindings(user, field_id)
    if bindings is None:
        return {
            "status": "blocked",
            "reason": "water_source_binding_unresolved",
            "field_id": field_id,
            "requires_expert_review": True,
            "detail": "تعذّرت قراءة ربط مصدر الماء الخادميّ للتحقّق من حدّ الملوحة — fail-closed.",
        }
    bound_source_ids = {b["water_source_id"] for b in bindings}
    if req.water_source_id and req.water_source_id not in bound_source_ids:
        # منع التوجيه: العميل لا يستطيع توجيه البوّابة لمصدر ليس ربطَ الحقل النشِط الخادميّ.
        return {
            "status": "blocked",
            "reason": "water_source_binding_mismatch",
            "field_id": field_id,
            "water_source_id": req.water_source_id,
            "active_source_ids": sorted(bound_source_ids),
            "requires_expert_review": True,
            "detail": "مصدر الماء المُمرَّر لا يطابق ربط الحقل النشِط الخادميّ — لا تجاوز للعميل.",
        }
    if bindings:
        source_verdicts: list[dict] = []
        any_blocked = False
        for b in bindings:
            gate = evaluate_water_salinity_gate(
                maximum_allowed_ec_ds_m=b["maximum_allowed_ec_ds_m"],
                water_quality=b["water_quality"],
                require_decision_grade=True,
                non_decision_grade_sample_present=b["non_decision_grade_sample_present"],
            )
            source_verdicts.append(
                {
                    "water_source_id": b["water_source_id"],
                    "priority": b["priority"],
                    "mixing_ratio": b["mixing_ratio"],
                    "status": gate["status"],
                    "blocking_reasons": gate["blocking_reasons"],
                    "water_ec_ds_m": gate["water_ec_ds_m"],
                    "maximum_allowed_ec_ds_m": gate["maximum_allowed_ec_ds_m"],
                    "water_quality_tier": gate["water_quality_tier"],
                }
            )
            if gate["status"] == "blocked":
                any_blocked = True
        if any_blocked:
            return {
                "status": "blocked",
                "reason": "water_salinity_gate_blocked",
                "field_id": field_id,
                "source_verdicts": source_verdicts,
                "requires_expert_review": True,
                "detail": (
                    "ملوحة ماء الريّ تتجاوز الحدّ (أو لا عيّنة قرار-درجة / عيّنة قديمة) على مصدر "
                    "مربوط خادميّاً — لا توصية حتى مراجعة خبير."
                ),
            }
        salinity_provenance = {
            "mode": "server_bound_sources",
            "enforced": True,
            "source_verdicts": source_verdicts,
        }
    else:
        # لا ربط نشِط: الحقل بلا مصدر ماء مُنمذَج ⇒ لا حدّ ملوحة يُفرَض. يُسجَّل بصدق — وليس تجاوزاً
        # قابلاً للتزوير من العميل: الروابط تُدار خادميّاً، فلا يفبركها العميل ولا يتجنّب موجوداً.
        salinity_provenance = {
            "mode": "unbound_no_active_source_assignment",
            "enforced": False,
        }

    canonical = await _source_canonical_water(user, field_id, req.horizon_days)
    if canonical is None or isinstance(canonical, dict):
        # المُنتِجُ القانونيّ يُرجِع حمولةَ حجبٍ **مُسمّاة** عند نقص أيّ دليل. تُمرَّر
        # كما هي: سببُه أدقُّ من `insufficient_ground_truth` عامّاً — يقول أيُّ دليلٍ
        # نقص (`canonical_rain_incomplete` · `canonical_field_elevation_missing` …).
        blocked = dict(canonical or {})
        blocked.update({"status": "blocked", "field_id": field_id})
        blocked.setdefault("reason", "insufficient_ground_truth")
        blocked.setdefault(
            "detail",
            "لا تُبنى توصية عمليّة إلّا من حقائق SoR كاملة (لا حقائق عميل). استعمل "
            "/simulate للمحاكاة اليدويّة، أو شغّل مصادر الحقائق الناقصة.",
        )
        return blocked

    if not canonical.operational_eligible:
        # حالةٌ متدهورة (دفترٌ بائت مثلاً) تُبنى منها **محاكاة** لا مرشّحٌ محكوم:
        # `operational_eligible` هو حكمُ المُنتِج على صلاحيّة لقطتِه للتشغيل، وتجاهلُه
        # يُعيد بالضبط ما أُزيل من `/plan` — سلطةً أقوى من دليلها.
        return {
            "status": "blocked",
            "reason": "canonical_water_state_not_operational",
            "field_id": field_id,
            "season_id": canonical.season_id,
            "quality_status": canonical.quality_status,
            "limitations": canonical.limitations,
        }

    state = {
        "depletion_mm": canonical.depletion_mm,
        "stage": canonical.growth_stage,
        "as_of": canonical.ledger_date,
    }
    soil = {
        "taw_mm": canonical.taw_mm,
        "raw_fraction": canonical.raw_fraction,
        "crop": canonical.crop,
    }
    forecast = canonical.forecast

    # بصماتُ المُنتِج نفسِه لا بصماتٌ تُحسَب هنا: النَّسَبُ يشير إلى اللقطة التي بُني
    # عليها القرارُ فعلاً، فيُطابَق لاحقاً بما خزّنه المُنتِج.
    ledger_snapshot_hash = canonical.water_state_digest
    weather_snapshot_hash = canonical.weather_snapshot_digest
    soil_snapshot_hash = canonical.soil_profile_digest

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
            "depletion_source": "canonical_water_state",
            "stage_source": "canonical_water_state",
            "taw_source": "canonical_root_zone_profile",
            "forecast_source": "canonical_water_state",
            "as_of": state.get("as_of"),
            "ledger_snapshot_hash": ledger_snapshot_hash,
            "weather_snapshot_hash": weather_snapshot_hash,
            "soil_snapshot_hash": soil_snapshot_hash,
            "water_salinity": salinity_provenance,
        },
    }
    if req.submit:
        if not bridge_enabled():
            out["emit"] = {"status": "disabled"}
        else:
            out["emit"] = await emit_mpc_candidate(decision, tenant_id=tenant_id)
    return out


# ═══════════════ WX-I1 wiring: hourly energy-aware MPC (server-owned) ═══════════════
# مسار أعلى دقّةً من `/recommendation` اليوميّ: يستهلك ETc الساعيّ الأصليّ من محرّك الطقس
# (WX-I1، لا تفكيك زمنيّ) + نوافذ الطاقة الساعيّة + بيان القدرة/التكليف، ويحلّ جدول M3
# الساعيّ الواعي بالطاقة. **توصية-فقط بنيويّاً** (`execution_allowed=False`): لا أمر مضخّة.
# كلّ الحقائق خادميّة (المنسّق يقرأ SoR: ميزان الماء، بيان القدرة، بوّابة التكليف، الطقس)؛
# `tenant_id` من JWT لا من الجسم؛ تحقّق ملكيّة الحقل؛ نقص أيّ حقيقة ⇒ blocked (لا تلفيق).


class HourlyRecommendationRequest(BaseModel):
    """توصية ساعيّة واعية بالطاقة — لا حقائق فيزيائيّة من العميل (كلّها SoR خادميّاً)."""

    horizon_hours: int = Field(default=48, ge=1, le=72)
    persist: bool = True  # المنسّق يحفظ جدولاً توصويّاً فقط (لا أمر تنفيذ)


@router.post("/api/v1/fields/{field_id}/irrigation/mpc/hourly-recommendation")
async def irrigation_mpc_hourly_recommendation(
    field_id: str,
    req: HourlyRecommendationRequest,
    user: UserSchema = Depends(get_current_user),
) -> dict:
    """توصية ريّ ساعيّة واعية بالطاقة قابلة للجدولة — كلّ الحقائق من SoR خادميّاً.

    يتحقّق من ملكيّة الحقل، ثمّ يفوّض المنسّق الخادميّ الذي يركّب: حالة الماء القانونيّة +
    أحدث بيان قدرة ريّ + بوّابة تكليف/تنفيذيّة + ETc الساعيّ الأصليّ (WX-I1) في جدول M3
    توصويّ-فقط. أيّ حقيقة ناقصة ⇒ blocked (لا اختلاق). `execution_allowed=False` دائماً.
    """
    tenant_id = user.tenant_id
    if not await _field_belongs_to_tenant(user, field_id):
        return {"status": "blocked", "reason": "field_not_owned", "field_id": field_id}
    async with tenant_connection(user) as conn:
        result = await orchestrate_irrigation_recommendation(
            conn,
            tenant_id=tenant_id,
            field_id=field_id,
            horizon_hours=req.horizon_hours,
            persist=req.persist,
        )
    # ثبات العقد: توصية-فقط صراحةً حتى لو أعاد المنسّق حمولة blocked مبكّرة.
    result.setdefault("recommendation_only", True)
    result.setdefault("execution_allowed", False)
    return result


# ═══════════ المسار الراجع القابل للقياس (Closed-loop reconciliation) ═══════════
# يشتقّ الحقيقة المُطبَّقة فعليّاً (as-applied) من إيصالات المتحكّم والقياسات الخادميّة،
# ثمّ يوفّق الماء المقيس المُتحقَّق منه **فقط** في دفتر الماء اليوميّ بشكل idempotent
# (v184 + irrigation_closed_loop_runtime). `tenant_id` من JWT؛ لا أمر تنفيذ — قياس بحت.


class ReconcileIrrigationRunRequest(BaseModel):
    """Trigger server-owned reconciliation for an already persisted execution run."""

    run_id: str = Field(min_length=36, max_length=36)


@router.post("/api/v1/irrigation/executions/reconcile")
async def reconcile_irrigation_execution(
    req: ReconcileIrrigationRunRequest,
    user: UserSchema = Depends(get_current_user),
) -> dict:
    """Derive measured as-applied truth and update the water ledger idempotently."""
    from api.irrigation_closed_loop_runtime import reconcile_irrigation_run

    async with tenant_connection(user) as conn:
        async with conn.transaction():
            return await reconcile_irrigation_run(conn, run_id=req.run_id)
