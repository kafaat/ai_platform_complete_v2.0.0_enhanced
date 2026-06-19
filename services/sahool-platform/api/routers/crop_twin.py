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
from api.main import UserSchema, get_current_user
from api.soil_water import soil_water_params
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


@router.post("/api/v1/crop-twin/compose")
def compose_crop_twin(
    req: CropTwinComposeRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يركّب حالة المحصول الموحّدة من مدخلات الطقس/التربة/NDVI/الإدارة — نقيّ في جوهره.

    صدق: Kc ديناميكيّ من NDVI إن توفّر وإلّا ثابت للمرحلة؛ كلّ القيم موسومة
    calibrated=False مع quality/assumptions صريحة (لا لقطة حيّة مُدّعاة).
    """
    soil_in = req.soil
    sp = soil_water_params(
        soil_in.texture, root_depth_m=soil_in.root_depth_m, raw_fraction=soil_in.raw_fraction
    )
    taw_mm = soil_in.taw_mm if soil_in.taw_mm is not None else sp["taw_mm"]

    # Kc ديناميكيّ من NDVI (تطعيم fAPAR بين البدئيّ والذروة) أو ثابت للمرحلة.
    kc_map = KC_BY_CROP_STAGE.get((req.crop or "").strip().lower(), _GENERIC_KC_MAP)
    dyn_kc, kc_fapar = kc_from_ndvi(req.ndvi, kc_map, req.stage)

    days = [
        TwinDay(
            t_min_c=d.t_min_c,
            t_max_c=d.t_max_c,
            et0_mm=d.et0_mm,
            kc=d.kc if d.kc is not None else dyn_kc,
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

    # أعلام الإجهاد (من حالة التوأم — لا اختلاق).
    stress_flags: list[dict] = []
    if twin["water"]["needs_irrigation"]:
        stress_flags.append({"code": "water_deficit", "label_ar": "عجز مائيّ — الريّ مستحقّ"})
    if twin["phenology"]["past_maturity"]:
        stress_flags.append({"code": "past_maturity", "label_ar": "تجاوز النضج المتوقّع"})

    # جودة المدخلات (نفس صدق irrigation-plan): افتراضات متحقَّقة خادميّاً.
    assumptions = ["uncalibrated_model", "no_moisture_sensor"]
    if soil_in.taw_mm is None and not sp["texture_known"]:
        assumptions.insert(0, "default_soil")
    if soil_in.taw_mm is None and (soil_in.root_depth_m is None or soil_in.root_depth_m <= 0):
        assumptions.append("estimated_root_depth")
    quality = assess_data_quality(assumptions)

    return {
        "field_id": req.field_id,
        "crop": twin["crop"],
        "crop_known": twin["crop_known"],
        "dynamic_kc": round(dyn_kc, 3),
        "kc_fapar": round(kc_fapar, 3) if kc_fapar is not None else None,
        "kc_source_ar": "ديناميكيّ من NDVI"
        if req.ndvi is not None
        else f"ثابت للمرحلة ({req.stage})",
        "crop_twin": twin,
        "phenology": twin["phenology"],
        "water_state": twin["water"],
        "nutrient_state": twin["nutrient"],
        "stress_flags": stress_flags,
        "quality": quality,
        "calibrated": False,
        "assumptions": quality["assumptions"],
        "warnings_ar": twin["warnings_ar"],
    }
