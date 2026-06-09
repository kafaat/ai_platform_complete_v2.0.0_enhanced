"""
sahool_core.skills_registry
============================
مفهرس القدرات الزراعية — Tool-Orchestrated Agronomic Intelligence.

الفجوة المسدودة: لدينا 12 محرّكاً + 4 موصّلاً، لكن:
  • لا توقيع موحّد (signature) — كل واحد يأخذ مدخلات مختلفة بدون عقد صريح
  • لا اكتشاف برمجي — recommendation_engine يربطها بـimports مباشرة
  • لا introspection — لا طريقة لمعرفة "ما الـskills المتاحة لحقل READY؟"
  • لا تتبّع للنسخ — أيّ نسخة من كل محرّك مستخدمة؟

هذه ليست chatbot ولا LLM orchestrator. هي **catalog معماري**:
  • يصف كل skill بتوقيع موحّد (name, version, inputs, outputs, requires)
  • يحرس الـrestraint (مبدأ AI Workaholic: لا توصية بدون ضرورة)
  • يخدم recommendation_replay (model_versions يأتي من هنا)
  • يخدم RBAC اللاحق (أيّ دور يستطيع تشغيل أيّ skill؟)

المبادئ المحفوظة:
  • النواة محايدة: registry يقرأ الـmetadata، لا يستدعي شيئاً
  • صفر اختراع: skill بدون توقيع موثّق → لا يُسجَّل
  • Setup before prompting: التحقّق من المتطلّبات قبل التشغيل
  • التفسير: كل skill يحمل نصّاً عربياً يشرح غرضه للمزارع

التكامل (دون كسر):
  ← recommendation_engine يستعلم عن الـskills المتاحة لحالة الحقل
  ← recommendation_replay يستخدم model_versions من registry
  ← التوثيق الذاتي: docs تُولَّد من registry آلياً
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class SkillCategory(str, Enum):
    """فئة الـskill — يحدّد متى يُستدعى."""
    AGRONOMIC = "agronomic"       # توصية زراعية مباشرة (ري، تسميد، ...)
    SAFETY = "safety"             # حارس سلامة (PHI، حدود الملوحة)
    SPATIAL = "spatial"           # تحليل مكاني (مناطق اهتمام، خرائط)
    DIAGNOSTIC = "diagnostic"     # تقدير حالة (BSI، تربة، نسيج)
    DATA = "data"                 # استيراد/تحقّق بيانات
    LEARNING = "learning"         # معايرة وتعلّم
    CONNECTOR = "connector"       # مصدر بيانات خارجي


class ConfidenceCeiling(str, Enum):
    """سقف الثقة الذي يمكن أن يبلغه الـskill."""
    NONE = "none"          # لا ثقة دون شرط (مثل: بدون مختبر = none)
    LOW = "low"            # قرينة (استشعار، تيروير)
    MEDIUM = "medium"      # حسّاس أو نموذج معاير
    HIGH = "high"          # دليل مخبري + بيانات كاملة


@dataclass
class SkillSignature:
    """توقيع موحّد لأيّ قدرة زراعية في النواة."""
    name: str                          # "fao56_etc", "pesticide_phi_gate"
    version: str                       # "v2.1" — حيوي لـreplay drift detection
    category: SkillCategory
    description_ar: str                # شرح للمزارع/المهندس بالعربية
    required_inputs: list              # ["etc_mm", "kc", "ks_salinity"]
    optional_inputs: list              # ["soil_moisture", "leaf_wetness"]
    outputs: list                      # ["irrigation_mm", "confidence", "reason_ar"]
    requires_quality_grade: str        # "READY"/"LIMITED"/"PENDING_LAB" — أدنى مستوى مطلوب
    confidence_ceiling: ConfidenceCeiling
    safety_critical: bool = False      # هل خطؤه يضرّ المستهلك/البيئة؟
    handler: Callable | None = None    # الدالة الفعلية (اختياري — قد تُسجَّل بدون)
    cost_class: str = "free"           # "free"/"low_cost"/"paid" (للموصّلات)
    tags_ar: list = field(default_factory=list)


# ─── السجلّ المركزي ─────────────────────────────────────────────
# قاموس الـskills المتاحة. التسجيل صريح (لا magic auto-discovery)
# لأنّ ذلك يحقّق "Setup before prompting": كل skill يُراجَع قبل الإضافة.
_REGISTRY: dict[str, SkillSignature] = {}


def register(signature: SkillSignature) -> None:
    """يسجّل skill في الـcatalog. يرفض التكرار بصراحة (لا overwrite صامت)."""
    if signature.name in _REGISTRY:
        raise ValueError(
            f"Skill '{signature.name}' مُسجَّلة بالفعل — "
            f"النسخة الحالية {_REGISTRY[signature.name].version}، "
            f"الجديدة {signature.version}. استخدم unregister أولاً.")
    _REGISTRY[signature.name] = signature


def unregister(name: str) -> bool:
    """يحذف skill من السجلّ. يُرجع True إن وُجدت."""
    return _REGISTRY.pop(name, None) is not None


def get(name: str) -> SkillSignature | None:
    """يستعلم عن skill بالاسم."""
    return _REGISTRY.get(name)


def all_skills() -> list[SkillSignature]:
    """قائمة بكل الـskills المسجّلة (نسخة، آمنة من التعديل الخارجي)."""
    return list(_REGISTRY.values())


def by_category(category: SkillCategory) -> list[SkillSignature]:
    """الـskills في فئة معيّنة (لتقسيم العرض في الواجهة)."""
    return [s for s in _REGISTRY.values() if s.category == category]


def available_for_field(quality_grade: str, available_inputs: set
                        ) -> list[SkillSignature]:
    """ما الـskills المتاحة لحقل بحالة معيّنة + بيانات متوفّرة؟

    يحقّق "Setup before prompting": لا نعرض الـskill إن كانت متطلّباته
    غير متوفّرة. هذا يمنع توصيات تنفجر منتصف الطريق."""
    # ترتيب درجات الجودة (أعلى يشمل الأدنى)
    grade_levels = {"BLOCKED": 0, "LIMITED": 1, "PENDING_LAB": 2, "READY": 3}
    field_level = grade_levels.get(quality_grade, 0)

    eligible = []
    for skill in _REGISTRY.values():
        # ١. الحالة كافية؟
        required_level = grade_levels.get(skill.requires_quality_grade, 0)
        if field_level < required_level:
            continue
        # ٢. المدخلات الإلزامية متوفّرة؟
        if not set(skill.required_inputs).issubset(available_inputs):
            continue
        eligible.append(skill)
    return eligible


def safety_critical_skills() -> list[SkillSignature]:
    """الـskills الحرجة للسلامة — تستحقّ مراجعة بشرية إضافية."""
    return [s for s in _REGISTRY.values() if s.safety_critical]


def model_versions_snapshot() -> dict[str, str]:
    """لقطة للنسخ الحالية — تُحفظ في RecommendationProvenance.

    هذا الجسر إلى recommendation_replay: يضمن أن drift detection
    يعمل على البيانات الفعلية بدل التخمين."""
    return {s.name: s.version for s in _REGISTRY.values()}


def registry_health() -> dict:
    """فحص صحّي للسجلّ — يكشف الـskills الناقصة التوثيق.

    مبدأ AI Workaholic: نواة بـskills غير موثّقة = خطر تشغيلي."""
    issues = []
    for s in _REGISTRY.values():
        if not s.description_ar:
            issues.append(f"{s.name}: لا وصف عربي")
        if not s.required_inputs and not s.optional_inputs:
            issues.append(f"{s.name}: لا مدخلات موثّقة")
        if not s.outputs:
            issues.append(f"{s.name}: لا مخرجات موثّقة")

    by_cat: dict[str, int] = {}
    for s in _REGISTRY.values():
        by_cat[s.category.value] = by_cat.get(s.category.value, 0) + 1

    return {
        "total_skills": len(_REGISTRY),
        "by_category": by_cat,
        "safety_critical_count": len(safety_critical_skills()),
        "issues": issues,
        "summary_ar": (f"إجمالي {len(_REGISTRY)} skill، "
                       f"{len([s for s in _REGISTRY.values() if s.safety_critical])} "
                       f"حرجة للسلامة"
                       + (f"، {len(issues)} ناقصة التوثيق" if issues else
                          "، التوثيق كامل")),
    }


# ─── التسجيل الافتراضي للـskills الموجودة ────────────────────────
# مبدأ صريح: تسجيل يدوي لا تلقائي. كل skill مُراجَع قبل الإضافة.
# (هذه عيّنة — تُكمَل تدريجياً مع نمو النواة)

def _bootstrap_default_skills() -> None:
    """يسجّل الـskills الموجودة في النواة. يُستدعى مرّة عند الاستيراد."""

    # ─── المحرّكات الزراعية ───
    register(SkillSignature(
        name="fao56_etc",
        version="v2.1",
        category=SkillCategory.AGRONOMIC,
        description_ar="حساب الاحتياج المائي للمحصول (Penman-Monteith + Maas-Hoffman)",
        required_inputs=["et0", "kc", "growth_stage"],
        optional_inputs=["salinity_ec", "rainfall_mm", "leaching_factor"],
        outputs=["etc_adj_mm", "leaching_mm", "confidence"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["ري", "احتياج_مائي", "ملوحة"],
    ))

    register(SkillSignature(
        name="pesticide_phi_gate",
        version="v1.3",
        category=SkillCategory.SAFETY,
        description_ar="بوّابة PHI — تمنع الحصاد قبل انقضاء فترة الأمان",
        required_inputs=["last_spray_date", "phi_days", "harvest_planned_date"],
        optional_inputs=["product_name"],
        outputs=["status", "days_to_safe", "warning_ar"],
        requires_quality_grade="READY",
        confidence_ceiling=ConfidenceCeiling.HIGH,
        safety_critical=True,
        tags_ar=["مبيدات", "سلامة", "حصاد"],
    ))

    register(SkillSignature(
        name="supplemental_irrigation",
        version="v1.0",
        category=SkillCategory.AGRONOMIC,
        description_ar="حساب الريّ التكميلي للمناطق المطرية (فجوة ETc-Rainfall)",
        required_inputs=["etc_mm", "rainfall_mm", "growth_stage"],
        optional_inputs=["soil_water_storage_mm"],
        outputs=["recommended_mm", "needs_supplemental", "note_ar"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["ري_تكميلي", "مطر", "مدرّجات"],
    ))

    register(SkillSignature(
        name="deficit_irrigation",
        version="v1.2",
        category=SkillCategory.AGRONOMIC,
        description_ar="إدارة عجز الري ↔ الملوحة للمناطق المرويّة فقط",
        required_inputs=["etc_mm", "available_water_mm", "is_irrigated"],
        optional_inputs=["salinity_ec_ds_m"],
        outputs=["deficit_pct", "salinity_risk", "recommendation_ar"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["عجز_ري", "ملوحة", "ري"],
    ))

    register(SkillSignature(
        name="fertility_om_decay",
        version="v1.1",
        category=SkillCategory.AGRONOMIC,
        description_ar="حساب نصف عمر المواد العضوية في التربة (Q10 فيزياء حقيقية)",
        required_inputs=["soil_organic_matter_pct", "soil_temp_c"],
        optional_inputs=["clay_pct", "moisture_pct"],
        outputs=["half_life_days", "n_release_kg_ha", "confidence"],
        requires_quality_grade="PENDING_LAB",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["خصوبة", "مادة_عضوية", "نيتروجين"],
    ))

    register(SkillSignature(
        name="suitability_assessment",
        version="v2.0",
        category=SkillCategory.AGRONOMIC,
        description_ar="ملاءمة المحصول للموقع (حاكمات S3/S4/I3 + معدلات fuzzy)",
        required_inputs=["crop_id", "soil_ph", "salinity_ec"],
        optional_inputs=["chilling_hours", "elevation_m"],
        outputs=["suitability_class", "limiting_factors", "score"],
        requires_quality_grade="PENDING_LAB",
        confidence_ceiling=ConfidenceCeiling.HIGH,
        safety_critical=True,
        tags_ar=["ملاءمة", "محصول", "تقييم"],
    ))

    register(SkillSignature(
        name="planting_window",
        version="v1.0",
        category=SkillCategory.AGRONOMIC,
        description_ar="نافذة الزراعة المثلى لتجنّب الإجهاد الحراري",
        required_inputs=["crop_id", "location", "season_year"],
        optional_inputs=["historical_weather"],
        outputs=["window_start", "window_end", "frost_risk_ar"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["موعد_زراعة", "إجهاد_حراري"],
    ))

    register(SkillSignature(
        name="yield_interval_conformal",
        version="v1.5",
        category=SkillCategory.AGRONOMIC,
        description_ar="مجال الإنتاج بـConformal Prediction (لا رقم مفرد)",
        required_inputs=["crop_id", "calibration_residuals"],
        optional_inputs=["alpha_level"],
        outputs=["lower_bound", "upper_bound", "confidence_level"],
        requires_quality_grade="READY",
        confidence_ceiling=ConfidenceCeiling.HIGH,
        tags_ar=["إنتاجية", "مجال_ثقة", "تنبّؤ"],
    ))

    # ─── المكانية ───
    register(SkillSignature(
        name="zone_detection",
        version="v1.4",
        category=SkillCategory.SPATIAL,
        description_ar="كشف مناطق الاهتمام داخل الحقل (connected components)",
        required_inputs=["indicator_grid", "threshold"],
        optional_inputs=["min_cluster_size"],
        outputs=["zones", "areas_ha", "reasons_ar"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.LOW,
        tags_ar=["مناطق", "ndvi", "مكاني"],
    ))

    register(SkillSignature(
        name="raster_export",
        version="v1.0",
        category=SkillCategory.SPATIAL,
        description_ar="تصدير المؤشّر كـPNG imageOverlay (None→شفّاف)",
        required_inputs=["grid", "indicator", "bounds"],
        optional_inputs=[],
        outputs=["png_bytes", "transparent_pixels", "coverage_pct"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.LOW,
        tags_ar=["خريطة", "بكسلية", "عرض"],
    ))

    # ─── البيانات ───
    register(SkillSignature(
        name="sensor_intake",
        version="v1.0",
        category=SkillCategory.DATA,
        description_ar="استقبال قراءات المستشعرات (نطاق فيزيائي، سقف medium)",
        required_inputs=["tenant_id", "field_id", "sensor_type", "value"],
        optional_inputs=["device_id", "lon", "lat", "timestamp"],
        outputs=["accepted", "observation", "rejection_reason_ar"],
        requires_quality_grade="BLOCKED",   # حتى الحقول BLOCKED تستقبل قراءات
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        tags_ar=["مستشعرات", "iot", "بيانات"],
    ))

    register(SkillSignature(
        name="historical_loader",
        version="v1.0",
        category=SkillCategory.DATA,
        description_ar="استيراد بيانات المواسم السابقة من CSV/JSON",
        required_inputs=["file_content", "format"],
        optional_inputs=[],
        outputs=["accepted_rows", "rejections", "summary"],
        requires_quality_grade="BLOCKED",
        confidence_ceiling=ConfidenceCeiling.HIGH,   # بيانات تاريخية موثّقة = دليل
        tags_ar=["استيراد", "مواسم_سابقة", "csv"],
    ))

    # ─── التعلّم ───
    register(SkillSignature(
        name="calibration_loop",
        version="v2.0",
        category=SkillCategory.LEARNING,
        description_ar="معايرة zone_factor من الحصاد الفعلي + التاريخ",
        required_inputs=["yield_history", "predictions"],
        optional_inputs=["district_id"],
        outputs=["zone_factor", "confidence", "method_used"],
        requires_quality_grade="READY",
        confidence_ceiling=ConfidenceCeiling.HIGH,
        tags_ar=["معايرة", "حصاد", "تعلّم"],
    ))

    register(SkillSignature(
        name="recommendation_replay",
        version="v1.0",
        category=SkillCategory.LEARNING,
        description_ar="forensic — لماذا خرجت التوصية؟ + كشف انحراف النموذج",
        required_inputs=["rec_record"],
        optional_inputs=["current_model_versions"],
        outputs=["explanation_ar", "drift_detected", "drift_reasons_ar"],
        requires_quality_grade="BLOCKED",   # يعمل على أيّ توصية مسجّلة
        confidence_ceiling=ConfidenceCeiling.HIGH,
        tags_ar=["تتبّع", "forensic", "drift"],
    ))

    # ─── الموصّلات ───
    register(SkillSignature(
        name="weather_openmeteo",
        version="v1.2",
        category=SkillCategory.CONNECTOR,
        description_ar="بيانات الطقس من Open-Meteo (مجاني، بلا مفتاح)",
        required_inputs=["lat", "lon", "date_range"],
        optional_inputs=["variables"],
        outputs=["temperature", "rainfall", "humidity", "et0"],
        requires_quality_grade="BLOCKED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        cost_class="free",
        tags_ar=["طقس", "مجاني", "open_meteo"],
    ))

    register(SkillSignature(
        name="copernicus_sentinel2",
        version="v1.1",
        category=SkillCategory.CONNECTOR,
        description_ar="صور Sentinel-2 من Copernicus (مؤشّرات نباتية)",
        required_inputs=["polygon", "date_range"],
        optional_inputs=["cloud_threshold_pct"],
        outputs=["ndvi", "ndmi", "ndwi", "cloud_coverage"],
        requires_quality_grade="LIMITED",
        confidence_ceiling=ConfidenceCeiling.MEDIUM,
        cost_class="low_cost",
        tags_ar=["أقمار", "ndvi", "sentinel2"],
    ))


# تشغيل التسجيل عند الاستيراد (يحدث مرّة واحدة)
_bootstrap_default_skills()
