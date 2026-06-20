"""api/routers/crop_twin.py — حالة المحصول الموحّدة (Crop Twin Compose)

نقطة **تركيب** تكشف `crop_twin` الحاليّ كحالة محصول مقروءة في استجابة واحدة:
فينولوجيا + Kc ديناميكيّ من NDVI + حالة الماء (منطقة الجذور) + حالة العنصر (الامتصاص)
+ أعلام الإجهاد + جودة المدخلات. لا محرّك جديد — تجمع وحدات قائمة فقط:
  soil_water ⇒ kc_from_ndvi ⇒ crop_twin_state ⇒ assess_data_quality.

**POST /compose** عمداً لا GET: الحالة **حساب على مدخلات مركّبة** (طقس/تربة/NDVI/إدارة)
يمرّرها المستدعي — وما دام خطّ field-state لم يصر مصدر حقيقة حيّاً، فـGET قد يوحي
بلقطة حيّة وهي ليست كذلك بعد. GET /{field_id} يأتي لاحقاً عند اكتمال المصدر الحيّ.

محفوظ النمط: `Depends(get_current_user)` (يمرّ حارس المصادقة)، نموذج self-contained.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.crop_twin import TwinDay, crop_twin_state
from api.data_quality import assess_data_quality
from api.decision_lineage import ensure_decision_id, lineage_stage
from api.economic_state import economic_state
from api.irrigation_method import gross_irrigation_mm, method_profile
from api.irrigation_mpc import ForecastDay, plan_irrigation
from api.irrigation_policy import PolicyContext, resolve_policy
from api.main import UserSchema, get_current_user
from api.soil_water import soil_water_params
from api.unified_decision import unified_decision
from api.water_balance import KC_BY_CROP_STAGE, kc_from_ndvi

router = APIRouter()

# منحنى Kc عامّ آمن حين يكون المحصول غير مُعرّف (موسوم في الاستجابة).
_GENERIC_KC_MAP = {"initial": 0.40, "development": 0.75, "mid": 1.10, "late": 0.50}


class ComposeForecastDay(BaseModel):
    t_min_c: float
    t_max_c: float
    et0_mm: float
    kc: float | None = None  # إن غاب ويُتاح ndvi ⇒ يُشتقّ Kc ديناميكيّاً
    rain_mm: float = 0.0
    irrigation_mm: float = 0.0
    runoff_mm: float = 0.0


class ComposeSoil(BaseModel):
    texture: str | None = None
    root_depth_m: float | None = None
    raw_fraction: float = 0.5
    taw_mm: float | None = None


class ComposeManagement(BaseModel):
    target_uptake_kg_ha: float = 0.0
    initial_depletion_mm: float = 0.0
    auto_irrigate: bool = False


class CropTwinComposeRequest(BaseModel):
    field_id: str | None = None
    crop: str | None = None
    stage: str = "mid"
    forecast: list[ComposeForecastDay] = Field(default_factory=list)
    ndvi: float | None = None
    soil: ComposeSoil = Field(default_factory=ComposeSoil)
    management: ComposeManagement = Field(default_factory=ComposeManagement)


def _compose_state(req: CropTwinComposeRequest) -> dict:
    """تركيب مشترك (نقيّ في جوهره): soil_water ⇒ Kc ديناميكيّ ⇒ crop_twin ⇒ quality.

    يعيد القطع التي تحتاجها نقطتا compose وdecision (تفادي تكرار الغراء).
    """
    soil_in = req.soil
    sp = soil_water_params(
        soil_in.texture, root_depth_m=soil_in.root_depth_m, raw_fraction=soil_in.raw_fraction
    )
    taw_mm = soil_in.taw_mm if soil_in.taw_mm is not None else sp["taw_mm"]

    # Kc ديناميكيّ من NDVI (تطعيم fAPAR بين البدئيّ والذروة) أو ثابت للمرحلة.
    kc_map = KC_BY_CROP_STAGE.get((req.crop or "").strip().lower(), _GENERIC_KC_MAP)
    dyn_kc, kc_fapar = kc_from_ndvi(req.ndvi, kc_map, req.stage)

    def _kc(d: ComposeForecastDay) -> float:
        return d.kc if d.kc is not None else dyn_kc

    days = [
        TwinDay(
            t_min_c=d.t_min_c,
            t_max_c=d.t_max_c,
            et0_mm=d.et0_mm,
            kc=_kc(d),
            rain_mm=d.rain_mm,
            irrigation_mm=d.irrigation_mm,
            runoff_mm=d.runoff_mm,
        )
        for d in req.forecast
    ]

    twin = crop_twin_state(
        req.crop,
        days,
        taw_mm=taw_mm,
        raw_fraction=soil_in.raw_fraction,
        target_uptake_kg_ha=req.management.target_uptake_kg_ha,
        initial_depletion_mm=req.management.initial_depletion_mm,
        auto_irrigate=req.management.auto_irrigate,
    )

    # جودة المدخلات (نفس صدق irrigation-plan): افتراضات متحقَّقة خادميّاً.
    assumptions = ["uncalibrated_model", "no_moisture_sensor"]
    if soil_in.taw_mm is None and not sp["texture_known"]:
        assumptions.insert(0, "default_soil")
    if soil_in.taw_mm is None and (soil_in.root_depth_m is None or soil_in.root_depth_m <= 0):
        assumptions.append("estimated_root_depth")
    quality = assess_data_quality(assumptions)

    return {
        "twin": twin,
        "sp": sp,
        "taw_mm": taw_mm,
        "raw_fraction": soil_in.raw_fraction,
        "dyn_kc": dyn_kc,
        "kc_fapar": kc_fapar,
        "quality": quality,
        "kc_of": _kc,  # لإعادة استخدام Kc الفعّال في خطّة الريّ
    }


@router.post("/api/v1/crop-twin/compose")
def compose_crop_twin(
    req: CropTwinComposeRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يركّب حالة المحصول الموحّدة من مدخلات الطقس/التربة/NDVI/الإدارة — نقيّ في جوهره.

    صدق: Kc ديناميكيّ من NDVI إن توفّر وإلّا ثابت للمرحلة؛ كلّ القيم موسومة
    calibrated=False مع quality/assumptions صريحة (لا لقطة حيّة مُدّعاة).
    """
    st = _compose_state(req)
    twin = st["twin"]

    stress_flags: list[dict] = []
    if twin["water"]["needs_irrigation"]:
        stress_flags.append({"code": "water_deficit", "label_ar": "عجز مائيّ — الريّ مستحقّ"})
    if twin["phenology"]["past_maturity"]:
        stress_flags.append({"code": "past_maturity", "label_ar": "تجاوز النضج المتوقّع"})

    return {
        "field_id": req.field_id,
        "crop": twin["crop"],
        "crop_known": twin["crop_known"],
        "dynamic_kc": round(st["dyn_kc"], 3),
        "kc_fapar": round(st["kc_fapar"], 3) if st["kc_fapar"] is not None else None,
        "kc_source_ar": "ديناميكيّ من NDVI"
        if req.ndvi is not None
        else f"ثابت للمرحلة ({req.stage})",
        "crop_twin": twin,
        "phenology": twin["phenology"],
        "water_state": twin["water"],
        "nutrient_state": twin["nutrient"],
        "stress_flags": stress_flags,
        "quality": st["quality"],
        "calibrated": False,
        "assumptions": st["quality"]["assumptions"],
        "warnings_ar": twin["warnings_ar"],
    }


class CropDecisionRequest(CropTwinComposeRequest):
    """طلب القرار الموحّد = طلب التركيب + سياسة الريّ وقيوده."""

    policy: str = "water_saving"
    max_application_mm: float | None = None
    season_budget_mm: float | None = None
    water_price_per_m3: float | None = None
    yield_value_per_ha: float | None = None
    decision_id: str | None = None  # نَسَب: يُمرَّر لإعادة استخدام السلسلة، أو يُسَكّ جديداً


@router.post("/api/v1/crop-twin/decision")
def compose_crop_decision(
    req: CropDecisionRequest,
    user: UserSchema = Depends(get_current_user),
):
    """قرار المحصول الموحّد: ريّ + تسميد + مخاطر + ثقة من حالة محصول واحدة — تركيب نقيّ.

    يجمع crop_twin + خطّة الريّ (وفق السياسة) + حالة العنصر عبر unified_decision.
    الاقتصاد مؤجَّل (economic_state=not_configured محجوز، لا مُختلق).
    """
    st = _compose_state(req)
    kc_of = st["kc_of"]

    plan = plan_irrigation(
        [
            ForecastDay(et0_mm=d.et0_mm, kc=kc_of(d), rain_mm=d.rain_mm, runoff_mm=d.runoff_mm)
            for d in req.forecast
        ],
        taw_mm=st["taw_mm"],
        raw_fraction=st["raw_fraction"],
        policy=req.policy,
        initial_depletion_mm=req.management.initial_depletion_mm,
        max_application_mm=req.max_application_mm,
        season_budget_mm=req.season_budget_mm,
        water_price_per_m3=req.water_price_per_m3,
        yield_value_per_ha=req.yield_value_per_ha,
    )

    decision = unified_decision(st["twin"], plan.to_dict(), st["quality"])
    did = ensure_decision_id(req.decision_id)
    decision["field_id"] = req.field_id
    decision["dynamic_kc"] = round(st["dyn_kc"], 3)
    decision["irrigation_plan"] = plan.to_dict()
    decision["decision_id"] = did
    decision["lineage"] = lineage_stage(did, "decision", field_id=req.field_id)
    return decision


class ProfitAwareDecisionRequest(CropDecisionRequest):
    """طلب القرار الواعي بالربح = طلب القرار + مدخلات اقتصاديّة + اختيار سياسة آليّ.

    auto_policy=True يدع الاقتصاد/السياق يختار السياسة (resolve_policy) بدل policy المُمرَّر.
    """

    auto_policy: bool = False
    water_source: str | None = None  # surface | shallow_well | deep_well | rain
    water_cost: str | None = None  # cheap | moderate | expensive
    energy_cost: str | None = None  # cheap | moderate | expensive
    region: str | None = None
    expected_yield_t_ha: float | None = None
    crop_price_per_t: float | None = None
    energy_kwh_ha: float | None = None
    energy_price_per_kwh: float | None = None
    fertilizer_price_per_kg: float | None = None
    irrigation_method: str | None = None  # flood|furrow|sprinkler|pivot|drip — يصحّح الماء الإجماليّ


@router.post("/api/v1/crop-twin/decision/profit-aware")
def compose_profit_aware_decision(
    req: ProfitAwareDecisionRequest,
    user: UserSchema = Depends(get_current_user),
):
    """القرار الموحّد الواعي بالربح: يملأ economic_state ويسمح للاقتصاد بتعديل السياسة.

    إن auto_policy=True ⇒ resolve_policy يختار السياسة من سياق التكلفة (بئر عميق/ماء
    غالٍ ⇒ profit_max...). يحسب economic_state من ماء الخطّة (م³/ها) والتسميد المتبقّي
    والأسعار المُمرَّرة. صدق: لا أسعار مُختلقة — الغائب يظهر missing_inputs/partial.
    """
    st = _compose_state(req)
    kc_of = st["kc_of"]

    # ١) السياسة: آليّة من سياق التكلفة، أو المُمرَّرة.
    policy = req.policy
    policy_reasons: list[str] = []
    policy_auto = False
    if req.auto_policy:
        chosen, policy_reasons = resolve_policy(
            PolicyContext(
                region=req.region,
                crop=req.crop,
                water_source=req.water_source,
                water_cost=req.water_cost,
                energy_cost=req.energy_cost,
            )
        )
        policy = chosen.value
        policy_auto = True

    plan = plan_irrigation(
        [
            ForecastDay(et0_mm=d.et0_mm, kc=kc_of(d), rain_mm=d.rain_mm, runoff_mm=d.runoff_mm)
            for d in req.forecast
        ],
        taw_mm=st["taw_mm"],
        raw_fraction=st["raw_fraction"],
        policy=policy,
        initial_depletion_mm=req.management.initial_depletion_mm,
        max_application_mm=req.max_application_mm,
        season_budget_mm=req.season_budget_mm,
        water_price_per_m3=req.water_price_per_m3,
        yield_value_per_ha=req.yield_value_per_ha,
    )
    plan_dict = plan.to_dict()

    # ٢) economic_state من كمّيّات الخطّة + الأسعار المُمرَّرة (لا اختلاق).
    nut = st["twin"]["nutrient"]
    fert_remaining = max(
        0.0,
        (nut.get("target_uptake_kg_ha", 0.0) or 0.0)
        - (nut.get("uptake_to_date_kg_ha", 0.0) or 0.0),
    )
    # الماء الإجماليّ المسحوب = الصافي ÷ كفاءة التطبيق (Ea). طريقة مجهولة/غير ممرَّرة ⇒
    # كفاءة عامّة محافظة (0.70) — يبقى الصافي مصحَّحاً بـEa عامّة (مقبول وموسوم calibrated=false).
    gross_total_mm = gross_irrigation_mm(plan_dict["total_irrigation_mm"], req.irrigation_method)
    econ = economic_state(
        expected_yield_t_ha=req.expected_yield_t_ha,
        crop_price_per_t=req.crop_price_per_t,
        irrigation_m3_ha=gross_total_mm * 10.0,  # إجماليّ مسحوب (لا الصافي) ⇒ تكلفة ماء صادقة
        water_price_per_m3=req.water_price_per_m3,
        energy_kwh_ha=req.energy_kwh_ha,
        energy_price_per_kwh=req.energy_price_per_kwh,
        fertilizer_kg_ha=fert_remaining if fert_remaining > 0 else None,
        fertilizer_price_per_kg=req.fertilizer_price_per_kg,
    )

    decision = unified_decision(st["twin"], plan_dict, st["quality"], economic=econ)
    did = ensure_decision_id(req.decision_id)
    decision["field_id"] = req.field_id
    decision["dynamic_kc"] = round(st["dyn_kc"], 3)
    decision["irrigation_plan"] = plan_dict
    decision["irrigation_method"] = method_profile(req.irrigation_method)["method"]
    decision["gross_irrigation_mm"] = round(gross_total_mm, 2)
    decision["decision_id"] = did
    decision["lineage"] = lineage_stage(did, "decision", field_id=req.field_id)
    decision["policy_decision"] = {
        "resolved_policy": policy,  # ما اختاره الاقتصاد/السياق
        "applied_policy": plan_dict["policy"],  # ما طبّقته الخطّة فعلاً (قد يتراجع لنقص الأسعار)
        "auto": policy_auto,
        "reasons_ar": policy_reasons,
    }
    return decision
