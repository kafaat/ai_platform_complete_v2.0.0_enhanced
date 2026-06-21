"""api/routers/irrigation_plan.py — نقطة تخطيط الريّ التنبّؤيّ (مركز المحاصيل)

# DECISION-PATH: adapter (feeds field-intelligence) — يحسب خطّة ريّ FAO-56 ويلتقطها
# في سلسلة النَّسَب (decision_record) لتُغذّي القرار/التوزيع لاحقاً. لا يُوزَّع للتنفيذ
# بنفسه؛ التنفيذ يمرّ بالمسار القانونيّ (run_field_intelligence ⇒ بوّابة الحَوكمة).

تربط طبقات خطّ «مركز المحاصيل» في نقطة واحدة قابلة للاستدعاء:
  نسيج+عمق ⇒ soil_water (TAW) ⇒ irrigation_policy (الهدف) ⇒ irrigation_mpc
  (جدول الريّ عبر أفق التنبّؤ، FAO-56 eq.85).

محفوظ النمط: مثل بقيّة الموجِّهات — ``Depends(get_current_user)`` (يمرّ حارس
المصادقة البنيويّ)، والدوالّ النقيّة تُستورَد من وحداتها مباشرةً (لا عبر main).
النموذج مُعرَّف هنا self-contained تفادياً للارتباط الدائريّ مع main.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.data_quality import assess_data_quality
from api.decision_lineage import ensure_decision_id, lineage_stage
from api.irrigation_mpc import ForecastDay, plan_irrigation
from api.main import UserSchema, get_current_user
from api.routers.decision_record import persist_decision_if_enabled
from api.soil_water import soil_water_params

router = APIRouter()


class ForecastDayModel(BaseModel):
    et0_mm: float
    kc: float
    rain_mm: float = 0.0
    runoff_mm: float = 0.0


class IrrigationPlanRequest(BaseModel):
    forecast: list[ForecastDayModel]
    # خصائص التربة (لاشتقاق TAW) — أو مرّر taw_mm مباشرةً لتجاوز الاشتقاق.
    soil_texture: str | None = None
    root_depth_m: float | None = None
    taw_mm: float | None = None
    raw_fraction: float = 0.5  # p — خاصّيّة محصول (FAO-56 Table 22)
    # السياسة والقيود.
    policy: str = "water_saving"  # water_saving | yield_max | profit
    initial_depletion_mm: float = 0.0
    max_application_mm: float | None = None
    season_budget_mm: float | None = None
    # اقتصاد (مطلوب فقط لسياسة profit).
    water_price_per_m3: float | None = None
    yield_value_per_ha: float | None = None
    decision_id: str | None = None  # نَسَب: يُمرَّر لإعادة استخدام السلسلة، أو يُسَكّ جديداً


def compute_irrigation_plan(
    req: IrrigationPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يخطّط جدول الريّ للأيّام القادمة عبر خطّ «مركز المحاصيل» كاملاً.

    يشتقّ TAW من النسيج×العمق (إن لم يُمرَّر taw_mm)، ثمّ يخطّط الريّ وفق السياسة.
    صدق: القيم المُشتقّة غير معايَرة يمنيّاً (موسومة calibrated=False في الكتلتَين). نقيّ
    بلا قاعدة؛ الإدامة في الغلاف async (irrigation_plan_endpoint) خلف علم تشغيليّ.
    """
    soil = soil_water_params(
        req.soil_texture, root_depth_m=req.root_depth_m, raw_fraction=req.raw_fraction
    )
    taw_mm = req.taw_mm if req.taw_mm is not None else soil["taw_mm"]

    plan = plan_irrigation(
        [
            ForecastDay(et0_mm=d.et0_mm, kc=d.kc, rain_mm=d.rain_mm, runoff_mm=d.runoff_mm)
            for d in req.forecast
        ],
        taw_mm=taw_mm,
        raw_fraction=req.raw_fraction,
        policy=req.policy,
        initial_depletion_mm=req.initial_depletion_mm,
        max_application_mm=req.max_application_mm,
        season_budget_mm=req.season_budget_mm,
        water_price_per_m3=req.water_price_per_m3,
        yield_value_per_ha=req.yield_value_per_ha,
    )
    plan_dict = plan.to_dict()

    # حقول جودة منظَّمة (بدل اشتقاق الواجهة من warnings_ar): الافتراضات المتحقَّقة خادميّاً.
    assumptions = ["uncalibrated_model", "no_moisture_sensor"]
    if req.taw_mm is None and not soil["texture_known"]:
        assumptions.insert(0, "default_soil")
    if req.taw_mm is None and (req.root_depth_m is None or req.root_depth_m <= 0):
        assumptions.append("estimated_root_depth")
    requested = (req.policy or "water_saving").strip().lower()
    if requested == "profit":
        requested = "profit_max"
    if plan_dict["policy"] != requested:
        assumptions.append("policy_fallback")

    did = ensure_decision_id(req.decision_id)
    return {
        "soil": soil,
        "taw_mm_used": round(taw_mm, 2),
        "quality": assess_data_quality(assumptions),
        "plan": plan_dict,
        "decision_id": did,
        "lineage": lineage_stage(did, "decision"),
    }


@router.post("/api/v1/irrigation-plan")
async def irrigation_plan_endpoint(
    req: IrrigationPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يخطّط الريّ ويلتقط القرار في السلسلة المُدامة تلقائيّاً عند المصدر.

    يحسب الخطّة نقيّاً (compute_irrigation_plan) ثمّ يُدِيمها إن فُعِّل علم الإدامة التلقائيّة
    — فيُلتقَط قرار الريّ في سلسلة النَّسَب بلا نداء /decision/record منفصل. الصدق: أثر جانبيّ
    best-effort؛ persisted=false عند الإطفاء أو تعذّر القاعدة (لا يكسر الخطّة).
    """
    out = compute_irrigation_plan(req=req, user=user)
    out["persisted"] = await persist_decision_if_enabled(
        user,
        decision_id=out["decision_id"],
        decision_type="irrigation_plan",
        decision_value=out,
    )
    return out
