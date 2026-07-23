"""api/season_models.py — نماذج ومساعدات المواسم الزراعيّة (Seasons) — v66.

مُستخرَجة من main.py ضمن تفكيك الوحدة الضخمة (B1، نقل عنقوديّ): نماذج Pydantic
لإنشاء/تحديث/تلخيص الموسم + مُطبِّع الصفّ (DB→نموذج) + أعمدة SELECT + نموذج ناتج
المحاكاة وثوابتها. يستهلكها routers/fields (CRUD المواسم) وrouters/seasons (المحاكاة)
مباشرةً — فيُقلّل اقتران الراوترات بالوحدة المركزيّة. منطق نماذج صرف: pydantic + stdlib
فقط (لا I/O ولا تبعيّة على main.py). المساعِد المشترك _assert_field_in_tenant يبقى في
main.py (يستخدمه عدّة راوترات، ليس خاصّاً بالمواسم).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# أنواع الريّ المقبولة — تطابق IRRIGATION_TYPES في الواجهة.
_IRRIGATION_TYPES = {"drip", "pivot", "flood", "sprinkler", "rainfed", "subsurface"}


class StageItem(BaseModel):
    name: str = ""
    date: str = ""
    notes: str = ""


class SeasonCreateRequest(BaseModel):
    """طلب إنشاء موسم زراعيّ لحقل (محاصيل/صنف/ريّ/تواريخ/مراحل)."""

    crops: list[str] = Field(default_factory=list)
    cultivar: str | None = Field(default=None, max_length=100)
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = Field(default=None, ge=0)
    land_leveling_date: str | None = None
    plowing_date: str | None = None
    sowing_date: str | None = None
    season_end: str | None = None
    custom_stages: list[StageItem] = Field(default_factory=list)
    # KPIs زراعيّة (v42) — أساس التحليلات، كلّها اختياريّة (ملء تدريجيّ)
    target_yield_kg_ha: float | None = Field(default=None, ge=0)
    plant_density: float | None = Field(default=None, ge=0)  # نبات/م²
    row_spacing_cm: float | None = Field(default=None, ge=0)
    seed_variety_source: str | None = Field(default=None, max_length=100)
    # حقول أغرونوميّة (v52، نمط FieldView) — كلّها اختياريّة
    maturity: str | None = Field(default=None, max_length=40)  # early/medium/late
    tillage_type: str | None = Field(default=None, max_length=40)
    actual_yield_kg_ha: float | None = Field(default=None, ge=0)  # الغلّة الفعليّة بعد الحصاد
    notes_ar: str | None = Field(default=None, max_length=2000)


class SeasonSummary(BaseModel):
    season_id: str
    field_id: str
    crops: list[str]
    cultivar: str | None = None
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = None
    land_leveling_date: str | None = None
    plowing_date: str | None = None
    sowing_date: str | None = None
    season_end: str | None = None
    stages: list[dict]
    status: str
    created_at: str | None = None
    # ─── KPIs زراعيّة (v42) — اختياريّة، ملء تدريجيّ ─
    target_yield_kg_ha: float | None = None
    plant_density: float | None = None
    row_spacing_cm: float | None = None
    seed_variety_source: str | None = None
    # ─── حقول أغرونوميّة (v52، نمط FieldView) — اختياريّة ─
    maturity: str | None = None
    tillage_type: str | None = None
    actual_yield_kg_ha: float | None = None
    notes_ar: str | None = None
    # ─── حارس تقويم الموسم (Season Calendar Guard) — إرشاديّ غير حاجب، يُحسَب عند الإنشاء ─
    # {status, requires_review, confidence, reason_ar, ...} أو None (محصول بلا تقويم/بلا بذار).
    calendar_check: dict | None = None
    # ─── نتائج محاكاة الموسم (v39) — تُملأ عند تشغيل /simulate، تقديريّة ─
    sim_yield_kg_ha: float | None = None
    sim_biomass_kg_ha: float | None = None
    sim_gdd_total: float | None = None
    sim_lai_max: float | None = None
    sim_water_mm: float | None = None
    sim_ran_at: str | None = None
    # عمّاد التزامن التفاؤليّ (v64) — يتزايد كلّ تحديث؛ يرسله العميل كـbase_version
    row_version: int | None = None


def _row_to_season(r) -> SeasonSummary:
    import json as _json

    keys = set(r.keys())

    def _arr(v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except (ValueError, TypeError):
                return []
        return v or []

    def _d(v):
        return v.isoformat() if v is not None else None

    def _num(col):  # عمود sim_* قد لا يكون في SELECT (مثلاً list_seasons) — None بأمان
        v = r[col] if col in keys else None
        return float(v) if v is not None else None

    return SeasonSummary(
        season_id=r["season_id"],
        field_id=r["field_id"],
        crops=_arr(r["crops"]),
        cultivar=r["cultivar"],
        irrigation_type=r["irrigation_type"],
        seed_rate_kg_ha=float(r["seed_rate_kg_ha"]) if r["seed_rate_kg_ha"] is not None else None,
        land_leveling_date=_d(r["land_leveling_date"]),
        plowing_date=_d(r["plowing_date"]),
        sowing_date=_d(r["sowing_date"]),
        season_end=_d(r["season_end"]),
        stages=_arr(r["stages"]),
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
        target_yield_kg_ha=_num("target_yield_kg_ha"),
        plant_density=_num("plant_density"),
        row_spacing_cm=_num("row_spacing_cm"),
        seed_variety_source=(r["seed_variety_source"] if "seed_variety_source" in keys else None),
        # v52 (محروسة بالمفاتيح — None إن لم تُحدَّد في SELECT)
        maturity=(r["maturity"] if "maturity" in keys else None),
        tillage_type=(r["tillage_type"] if "tillage_type" in keys else None),
        actual_yield_kg_ha=_num("actual_yield_kg_ha"),
        notes_ar=(r["notes_ar"] if "notes_ar" in keys else None),
        sim_yield_kg_ha=_num("sim_yield_kg_ha"),
        sim_biomass_kg_ha=_num("sim_biomass_kg_ha"),
        sim_gdd_total=_num("sim_gdd_total"),
        sim_lai_max=_num("sim_lai_max"),
        sim_water_mm=_num("sim_water_mm"),
        sim_ran_at=(
            r["sim_ran_at"].isoformat()
            if "sim_ran_at" in keys and r["sim_ran_at"] is not None
            else None
        ),
        row_version=(
            int(r["row_version"])
            if "row_version" in keys and r["row_version"] is not None
            else None
        ),
    )


class SeasonUpdateRequest(BaseModel):
    """تحديث موسم قائم (تحديث جزئيّ — الحقول الممرَّرة فقط). status بانتقال محقَّق."""

    status: str | None = None
    crops: list[str] | None = None
    cultivar: str | None = Field(default=None, max_length=100)
    irrigation_type: str | None = None
    seed_rate_kg_ha: float | None = Field(default=None, ge=0)
    sowing_date: str | None = None
    season_end: str | None = None
    target_yield_kg_ha: float | None = Field(default=None, ge=0)
    plant_density: float | None = Field(default=None, ge=0)
    row_spacing_cm: float | None = Field(default=None, ge=0)
    seed_variety_source: str | None = Field(default=None, max_length=100)
    # حقول أغرونوميّة (v52، نمط FieldView) — اختياريّة
    maturity: str | None = Field(default=None, max_length=40)
    tillage_type: str | None = Field(default=None, max_length=40)
    actual_yield_kg_ha: float | None = Field(default=None, ge=0)
    notes_ar: str | None = Field(default=None, max_length=2000)
    # تزامن تفاؤليّ (v64، اختياريّ/متوافق رجعيّاً): إصدار الموسم الأساس وقت قراءة
    # العميل. إن مُرِّر ولم يطابق row_version الحاليّ ⇒ 409 تعارض (كشف تعديل offline
    # متباعد). ليس عموداً يُكتَب — لا يدخل قائمة updates في update_season.
    base_version: int | None = Field(default=None, ge=1)


_SEASON_SELECT_COLS = (
    "season_id, field_id, crops, cultivar, irrigation_type, seed_rate_kg_ha, "
    "land_leveling_date, plowing_date, sowing_date, season_end, stages, status, "
    "created_at, target_yield_kg_ha, plant_density, row_spacing_cm, seed_variety_source, "
    "maturity, tillage_type, actual_yield_kg_ha, notes_ar, "
    "sim_yield_kg_ha, sim_biomass_kg_ha, sim_gdd_total, sim_lai_max, sim_water_mm, sim_ran_at, "
    "row_version"
)

# سقف نافذة المحاكاة (يوم) حين يغيب season_end — دورة موسميّة معقولة.
_SIM_MAX_WINDOW_DAYS = 160


class SeasonSimResponse(BaseModel):
    """ناتج محاكاة الموسم — تقديرات نموذجيّة بنطاق وثقة وافتراضات صريحة."""

    season_id: str
    crop: str
    crop_recognized: bool
    days_simulated: int
    gdd_total: float
    gdd_to_maturity: float
    maturity_reached: bool
    lai_max: float
    biomass_kg_ha: float
    yield_kg_ha: float
    yield_low_kg_ha: float
    yield_high_kg_ha: float
    water_need_mm: float
    water_supply_mm: float | None
    water_stress_factor: float
    confidence: float
    rationale_ar: str
    assumptions_ar: list[str]
    warnings_ar: list[str]
    sim_ran_at: str
    # صدق العرض (season_integrity #6): إشارات صريحة تمنع عرض التقدير كحقيقة معايَرة.
    # النموذج RUE/FAO-56 إرشاديّ غير معاير محلّيّاً ⇒ يتطلّب تحقّقاً حقليّاً دائماً.
    estimate_only: bool = True
    requires_field_validation: bool = True
    model_role: str = "screening_only"
    eligible_for_calibration: bool = False
    canonical_yield_engine: str = "pcse_wofost"
    estimate_disclaimer_ar: str = (
        "تقدير نموذجيّ (RUE/FAO-56) غير معاير محلّيّاً — يُعرَض بنطاق وثقة، ويتطلّب تحقّقاً "
        "حقليّاً قبل اعتماده قراراً. ليس غلّة فعليّة."
    )
    # WS-C.1c: نَسَب نواة GDD (مصدر/إصدار/عتبات + مقارنة ظلّيّة) حين تُجلَب من المحرّك.
    gdd_provenance: dict | None = None
    # WS-C.1b: نَسَب سلسلة ET0 (مصدر=weather-engine/إصدار الصيغة/أيّام محسوبة) — لا Hargreaves محلّيّ.
    et0_provenance: dict | None = None
    # HISTORICAL-SEASON-BRIDGE-01: lineage إلى حزمة الإدخال وسجل التشغيل.
    simulation_run_id: str | None = None
    input_digest: str | None = None
    historical_context_used: bool = False
    manual_irrigation_used: bool = False
    observed_fapar_used: bool = False
    decision_context_status: str = "not_attempted"
    decision_historical_snapshot_id: str | None = None
