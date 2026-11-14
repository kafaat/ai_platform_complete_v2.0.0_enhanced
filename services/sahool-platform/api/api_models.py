"""api/api_models.py — نماذج request/response المنقولة من main.py (تفكيك — سلوك محفوظ).

نُقِلت تعريفات Pydantic (BaseModel) من main.py حرفيّاً بلا تغيير سلوك،
وتُعاد استيرادها في main.py كي يبقى `main.<Model>` يَحُلّ كما كان.
الترتيب النسبيّ محفوظ (النماذج المتداخلة تسبق مستهلِكيها).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from core.irrigation_water_analysis import WaterSourceType
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator


class LoginRequest(BaseModel):
    user_id: str
    tenant_id: str
    role: str = "agronomist"
    name_ar: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RecommendationRequest(BaseModel):
    tenant_id: str
    farm_id: str
    field_id: str
    crop: str
    validation: dict
    current_indicators: dict = Field(default_factory=dict)
    district_id: str | None = None


class ObservationRequest(BaseModel):
    tenant_id: str
    farm_id: str | None = None
    field_id: str | None = None
    observable_id: str
    value: float
    unit: str = ""
    source: str = "manual"  # manual/sensor/lab/satellite
    confidence: str = "medium"
    measured_at: str  # ISO datetime
    method: str | None = None


class SyncBatchRequest(BaseModel):
    """دفعة عمليات من العميل offline-first.

    tenant_id is accepted only as a deprecated legacy echo. The authoritative
    tenant is always derived from the authenticated JWT/session.
    """

    tenant_id: str | None = None
    operations: list[dict]


class ActivityCreateRequest(BaseModel):
    """طلب تسجيل عمليّة زراعيّة لحقل (نوع/عنوان/تفاصيل/تواريخ/موسم اختياريّ)."""

    activity_type: str
    title_ar: str | None = Field(default=None, max_length=200)
    details: dict = Field(default_factory=dict)
    scheduled_for: str | None = None
    performed_on: str | None = None
    season_id: str | None = None


class ActivitySummary(BaseModel):
    activity_id: str
    field_id: str
    season_id: str | None = None
    activity_type: str
    title_ar: str | None = None
    details: dict
    scheduled_for: str | None = None
    performed_on: str | None = None
    status: str
    created_at: str | None = None


class SatelliteSource(BaseModel):
    asset_id: str
    scene_id: str
    acquisition_date: str
    index_name: str
    satellite: str | None = None
    algorithm_version: str | None = None
    geometry_revision: int | None = None


class TerrainSource(BaseModel):
    source_key: str
    kind: Literal["dem_product", "field_record"]
    product_id: str | None = None
    dem_version: str | None = None
    geometry_hash: str | None = None
    generated_at: str | None = None
    cell_size_m: float | None = None
    algorithm_version: str | None = None
    summaries: dict[str, dict[str, float]] = Field(default_factory=dict)
    elevation_m: float | None = None
    slope_pct: float | None = None
    aspect: str | None = None


class TaskSummary(BaseModel):
    terrain_sources: list[TerrainSource] = Field(default_factory=list)
    satellite_sources: list[SatelliteSource] = Field(default_factory=list)
    task_id: str
    field_id: str
    task_type: str
    priority: int = 3
    status: str
    recommended_date: str | None = None
    estimated_duration_min: int | None = None
    estimated_cost_usd: float | None = None
    source_scouting_pin_id: str | None = None
    actual_cost_usd: float | None = None
    assigned_to: str | None = None
    notes: str | None = None
    photo_url: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class TaskListResponse(BaseModel):
    """غلاف {tasks:[...]} — يطابق عقد الواجهة (useTasks يقرأ data.tasks).

    حقول الترقيم اختياريّة (مغلّف F5-06): تُملأ فقط عند تمرير ``?limit`` وإلّا تبقى None،
    فيبقى العقد متوافقاً للخلف تماماً (المستهلكون القدامى يتجاهلون الحقول الإضافيّة).
    ``next_cursor`` = الإزاحة التالية كنصّ، أو None عند بلوغ النهاية.
    """

    tasks: list[TaskSummary]
    irrigation_observations: list[dict] | None = None
    total: int | None = None
    limit: int | None = None
    next_cursor: str | None = None


# انتقالاتُ حالة المهمّة المسموحة (الحالةُ نفسُها مسموحةٌ دائماً — إعادةٌ صادقة). الإنجازُ
# المباشر من pending مسموح (الجوّال يُرسِله)؛ إعادةُ فتح المنجَزة تمسح completed_at؛ المنجَزةُ
# لا تُلغى والملغاةُ لا تُنجَز (تُعاد إلى pending أوّلاً). غيرُ ذلك ⇒ 409.
TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "completed", "cancelled"}),
    "in_progress": frozenset({"pending", "completed", "cancelled"}),
    "completed": frozenset({"pending", "in_progress"}),
    "cancelled": frozenset({"pending"}),
}
#: انحرافُ ساعة الجهاز المقبول لـ``completed_at`` القادم من صندوق الإرسال دون اتّصال.
TASK_COMPLETED_AT_SKEW = timedelta(minutes=5)


def task_transition_allowed(current: str | None, target: str) -> bool:
    """هل يُسمَح بالانتقال؟ الحالةُ الفارغة (صفوفٌ قديمة) تُعامَل ``pending``."""
    current = current or "pending"
    return current == target or target in TASK_TRANSITIONS.get(current, frozenset())


def task_allowed_sources(target: str) -> list[str]:
    """الحالاتُ التي يجوز منها الانتقالُ إلى ``target`` (لشرط ``UPDATE`` الذرّيّ)."""
    return sorted(s for s in TASK_TRANSITIONS if task_transition_allowed(s, target))


_TASK_COST = TypeAdapter(Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)])


class TaskUpdateRequest(BaseModel):
    """تحديث مهمّة (جزئيّ): الحالة و/أو صورة و/أو ملاحظة.

    ``completed_at`` (اختياريّ): وقتُ الإنجاز الفعليّ على الجهاز للمزامنة دون اتّصال — لا
    يتجاوز «الآن» إلا بانحراف ساعةٍ صغير، ويُقبَل فقط مع ``status=completed``. بغيابه يُختَم
    بوقت الخادم. ``actual_cost_usd`` (اختياريّ، ≥0): التكلفةُ الفعليّة عند الإنجاز.
    """

    status: str | None = None
    photo_url: str | None = None
    notes: str | None = None
    completed_at: datetime | None = None
    actual_cost_usd: float | None = Field(default=None, ge=0, le=99_999_999.99, allow_inf_nan=False)

    @field_validator("actual_cost_usd", mode="before")
    @classmethod
    def _validate_cost_precision(cls, value):
        # Validate NUMERIC(10,2) before converting to the legacy JSON number.
        return None if value is None else _TASK_COST.validate_python(value)

    @field_validator("completed_at")
    @classmethod
    def _completed_at_not_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:  # صندوقُ إرسالٍ بلا منطقة ⇒ UTC
            v = v.replace(tzinfo=UTC)
        if v > datetime.now(UTC) + TASK_COMPLETED_AT_SKEW:
            raise ValueError("completed_at cannot be in the future")
        return v

    @model_validator(mode="after")
    def _completion_fields_need_completed(self):
        if (self.completed_at is not None or self.actual_cost_usd is not None) and (
            self.status != "completed"
        ):
            raise ValueError("completed_at/actual_cost_usd require status=completed")
        return self


class NDVIObservationIn(BaseModel):
    """مشاهدة NDVI زمنيّة واحدة (من سلسلة Sentinel-2)."""

    date: str = Field(min_length=4, max_length=32)
    ndvi: float
    days_after_planting: int | None = Field(default=None, ge=0)


class GrowthNarrativeRequest(BaseModel):
    """سرد نموّ فينولوجي من سلسلة NDVI + مظروف متوقَّع اختياريّ."""

    observations: list[NDVIObservationIn]
    crop: str = Field(min_length=1, max_length=50)
    peak_ndvi_floor: float | None = Field(default=None, ge=-1, le=1)
    expected_peak_dap_min: int | None = Field(default=None, ge=0)


class SoilLabTestCreateRequest(BaseModel):
    """طلب فحص تربة جديد (يبدأ بحالة requested)."""

    lab_name: str | None = Field(default=None, max_length=120)
    sampled_on: str | None = None
    notes_ar: str | None = None
    result: dict | None = None


class SoilLabTestUpdateRequest(BaseModel):
    """تحديث فحص تربة (انتقال حالة محقَّق + بيانات اختياريّة)."""

    status: str | None = None
    lab_name: str | None = Field(default=None, max_length=120)
    sampled_on: str | None = None
    notes_ar: str | None = None
    result: dict | None = None


class SoilLabTestSummary(BaseModel):
    test_id: str
    field_id: str
    status: str
    lab_name: str | None = None
    sampled_on: str | None = None
    result: dict = Field(default_factory=dict)
    notes_ar: str | None = None
    approved_by: str | None = None
    published_at: str | None = None
    created_at: str | None = None


class NotificationPreferences(BaseModel):
    """تفضيلات إشعار المستخدم — القنوات المُفعَّلة + عناوينها + أنواع الأحداث.

    تُستخدم للقراءة والتحديث (PUT يستبدل الصفّ كاملاً — upsert). العناوين/الأرقام
    اختياريّة؛ القناة المُفعَّلة بلا عنوان تُسجَّل كغير قابلة للتسليم (صدق، لا ابتلاع).
    """

    email_enabled: bool = False
    email_address: str | None = Field(default=None, max_length=255)
    sms_enabled: bool = False
    sms_number: str | None = Field(default=None, max_length=32)
    push_enabled: bool = False
    push_token: str | None = None
    whatsapp_enabled: bool = False
    whatsapp_number: str | None = Field(default=None, max_length=32)
    event_types: list[str] = Field(default_factory=list)
    min_severity: str | None = None


class FarmCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str | None = None
    area_ha: float | None = None
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    # تنظيم المزرعة (v34) — حقول اختياريّة لشاشة «إنشاء مزرعة».
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=40)
    # غير اختياريّ بقيمة افتراضيّة 'metric' — يطابق DEFAULT في الـmigration ويمنع
    # إدراج NULL صريح، ومُقيَّد بالقيم المسموحة (تحقّق ساكن للواجهة أيضاً).
    units: Literal["metric", "imperial"] = "metric"
    currency: str | None = Field(default=None, max_length=10)
    description: str | None = None
    activity_type: str | None = Field(default=None, max_length=40)


class RotationRequest(BaseModel):
    crop: str = Field(min_length=1, max_length=80)
    season_label: str | None = None
    sequence_order: int | None = None
    planted_at: str | None = None
    harvested_at: str | None = None
    notes: str | None = None


class TrueUpRequest(BaseModel):
    field_id: str
    operation_id: str
    crop: str
    actual_weight_kg: float
    actual_moisture_pct: float
    measured_weight_kg: float
    measured_yield_kg_ha: float
    sample_area_ha: float | None = None
    notes_ar: str | None = None


class GeometryValidateRequest(BaseModel):
    geojson: dict
    declared_crs: str | None = None


class ZoneInput(BaseModel):
    zone_id: str
    zone_class: str  # "low" | "medium" | "high" | "problem"
    area_ha: float
    ndvi_mean: float | None = None
    soil_ph: float | None = None
    soil_ec: float | None = None
    soil_om: float | None = None
    soil_n_ppm: float | None = None
    soil_texture: str | None = None
    soil_depth_cm: int | None = None


class NitrogenRxRequest(BaseModel):
    field_id: str
    season_id: str
    crop: str
    zones: list[ZoneInput]


class YieldEstimateRequest(BaseModel):
    field_id: str
    crop: str
    days_in_growing: int = 0
    irrigation_count: int = 0
    moisture_stress_events: int = 0
    pest_alerts: int = 0
    fertilizer_applications: int = 0
    avg_ndvi_growing: float | None = None
    drought_streak_days: int = 0
    rain_events: int = 0


class NdviConfidenceRequest(BaseModel):
    ndvi_value: float
    observation_date: str  # ISO
    field_area_ha: float
    cloud_pct: float = 0
    cloud_shadow_pct: float = 0
    cirrus_pct: float = 0
    has_ground_truth: bool = False


class IrrigationConfRequest(BaseModel):
    ndvi_confidence: float | None = None
    et0_confidence: float | None = None
    soil_moisture_confidence: float | None = None
    weather_forecast_confidence: float | None = None


class FailureCheckRequest(BaseModel):
    cloud_pct: float | None = None
    days_since_observation: int | None = None
    weather_hours_since_update: int | None = None
    soil: dict | None = None


class MeasurementInput(BaseModel):
    source: str  # DataSource value
    timestamp: str  # ISO
    value: float | None = None


class TemporalCheckRequest(BaseModel):
    measurements: list[MeasurementInput]
    crop: str | None = None
    stage: str | None = None


class ReportFieldInput(BaseModel):
    field_id: str
    field_name_ar: str
    farm_id: str = ""
    tenant_id: str = ""
    area_ha: float = 0
    crop: str = ""
    season_label: str = ""
    planting_date: str | None = None
    harvest_date: str | None = None
    lifecycle_stage: str = "CREATED"
    irrigation_events: int = 0
    total_water_m3: float = 0
    fertilizer_events: int = 0
    total_nitrogen_kg: float = 0
    avg_ndvi: float | None = None
    estimated_yield_kg_ha: float | None = None


class OperationReportRequest(BaseModel):
    tenant_id: str
    operation_name_ar: str
    period_start: str
    period_end: str
    fields: list[ReportFieldInput]
    lang: str = "ar"


class TransitionCheckRequest(BaseModel):
    from_stage: str
    to_stage: str


class ReplayRequest(BaseModel):
    entity_type: str
    entity_id: str
    events: list[dict]  # [{event_type, occurred_at, payload}, ...]


class TimelineRequest(BaseModel):
    field_id: str
    events: list[dict]
    newest_first: bool = True
    category_filter: list[str] | None = None


class WhatIfRequest(BaseModel):
    """طلب محاكاة what-if.

    ``scenario`` كان ``str`` حرّاً يُعاد صدىً في الاستجابة ولا يُقرأ عند بناء
    المحاكاة (WOFOST-SCENARIO-IS-DECORATIVE-01): ``reduce_irrigation`` و
    ``no_irrigation`` كانا يُنتِجان **الأرقام نفسها بالضبط**. صار مجموعةً مغلقة
    لكلٍّ منها نسبة ريّ مُعلَنة تُمرَّر إلى المحرّك فعلاً — والقيم الثلاث هي كلّ
    ما كان يُرسَل قبلاً (المُوائم يُرسل ``recommended_action``)، فلا مستهلك
    شرعيّ يُرفَض بهذا الإغلاق.
    """

    field_id: str
    crop: str = "قمح صلب"
    lat: float | None = None
    lon: float | None = None
    soil_type: str = "loam"
    planting_date: str | None = None  # ISO؛ افتراض بداية الموسم
    scenario: Literal["reduce_irrigation", "no_irrigation", "recommended_action"] = (
        "reduce_irrigation"
    )


class PinCreateRequest(BaseModel):
    pin_id: str
    field_id: str
    lat: float
    lng: float
    issue_category: str
    severity: str = "medium"
    status: str = "new"
    persistence: str = "seasonal"
    crop: str | None = None
    issue_code: str | None = None
    note_ar: str | None = None
    photo_uri: str | None = None
    color: str | None = None
    created_by: str | None = None
    # v257: مصدر الموقع ودقّته. عميل قديم لا يرسلهما ⇒ unknown (لا استنتاج من الإحداثيّات).
    location_source: Literal["gps", "manual", "field_centroid", "unknown"] = "unknown"
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)


class EquipmentInput(BaseModel):
    terrace_area_m2: float | None = None
    cap_weight_kg: float | None = None
    tank_capacity_l: float | None = None
    tree_spacing_m2: float | None = None
    can_capacity_l: float | None = None
    concentration_kg_l: float | None = None


class ZoneRateInputModel(BaseModel):
    zone_id: str
    rate_kg_ha: float
    area_ha: float
    zone_class: str = "medium"


class WalkPlanRequest(BaseModel):
    field_id: str
    crop: str
    method: str  # broadcast_terrace | backpack_spray | per_tree
    zones: list[ZoneRateInputModel]
    equipment: EquipmentInput
    product_name_ar: str = "السماد"
    minutes_per_ha: float = 60.0


class ShareKeyRequest(BaseModel):
    scope: str = "read"  # read | read_write
    third_party_name: str | None = None
    third_party_type: str | None = None  # advisor | dealer | ministry | researcher | other
    allowed_field_ids: list[str] = []
    expires_in_days: int = 30


class SharingKeyCreateRequest(BaseModel):
    scope: str = "read"
    valid_days: int = 30
    third_party_name: str | None = None
    third_party_type: str | None = None
    allowed_field_ids: list[str] = []


class Soil4RRequest(BaseModel):
    caco3_pct: float | None = None
    ph: float | None = None
    p_ppm: float | None = None
    fe_ppm: float | None = None
    zn_ppm: float | None = None
    om_pct: float | None = None
    nutrients: list[str] | None = None


class ZoneCellInput(BaseModel):
    cell_id: str
    value: float
    confidence: float = 1.0


class ZoningRequest(BaseModel):
    cells: list[ZoneCellInput]
    n_zones: int = 3


class DailyTempInput(BaseModel):
    t_min_c: float
    t_max_c: float


class GDDRequest(BaseModel):
    crop: str
    temps: list[DailyTempInput]


class DiagnoseRequest(BaseModel):
    crop: str
    symptoms: list[str]
    # تغذية آمنة اختياريّة: عند تمرير field_id نُرفِق سياق الحالة القانونيّة
    # الموحّدة بالاستجابة. غيابه (None) ⇒ السلوك الحاليّ تماماً (لا إرفاق).
    field_id: str | None = None


class EngineSignalInput(BaseModel):
    engine: str
    has_recommendation: bool
    confidence: float
    blocking_reason_ar: str | None = None
    data_gaps_ar: list[str] = []


class ConfidenceGateRequest(BaseModel):
    signals: list[EngineSignalInput]


class EscalationAssessRequest(BaseModel):
    """تقييم تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG)."""

    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = Field(min_length=1, max_length=60)
    has_answer: bool = True
    uncertain_points: list[str] = Field(default_factory=list)


class ExternalPriorBlendRequest(BaseModel):
    """مزج سابقة خارجيّة منشورة (مشروع/ورقة) ببيانات اليمن المتراكمة — وزن تدرّجي."""

    external_prior: float | None = None
    local_estimate: float | None = None
    n_local: int = Field(default=0, ge=0)
    crop_grown_in_yemen: bool
    external_credibility: float = Field(default=0.5, ge=0, le=1)


class ReadinessRequest(BaseModel):
    provided_fields: list[str]


class CropSuitabilityRequest(BaseModel):
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True
    crops: list[str] | None = None


class WhatIfTempRequest(BaseModel):
    crop: str
    stage: str = "mid"
    t_min_c: float
    t_max_c: float
    temp_shift_c: float
    rain_mm: float = 0.0
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int | None = None  # None ⇒ من التاريخ الفعليّ (resolve_day_of_year)، لا 100


class WhatIfPlantingRequest(BaseModel):
    crop: str
    temps_baseline: list[dict]  # [{t_min_c, t_max_c}, ...]
    temps_scenario: list[dict]


class WhatIfRainRequest(BaseModel):
    crop: str
    stage: str = "mid"
    t_min_c: float
    t_max_c: float
    rain_baseline_mm: float
    rain_scenario_mm: float
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int | None = None  # None ⇒ من التاريخ الفعليّ (resolve_day_of_year)، لا 100


class EvidenceInput(BaseModel):
    etype: str  # lab_field|regional_prior|remote_sensing|field_obs|historical
    agrees: bool
    note_ar: str = ""


class CorroborationRequest(BaseModel):
    evidences: list[EvidenceInput]
    recommendation_key: str = "general"
    test_type_ar: str = "تربة"


class OutcomeRecordRequest(BaseModel):
    """تسجيل نتيجة توصية — يغذّي معايرة التنبّؤ وبوّابة تفعيل التعلّم (مسار الكتابة).

    crop + field_id إلزاميّان (سياق التوصية) — يمنعان صفوفاً فارغة تشوّه العدّادات.
    """

    crop: str = Field(min_length=1, max_length=50)
    field_id: str = Field(min_length=1, max_length=50)
    farm_id: str | None = Field(default=None, max_length=50)
    season_id: str | None = Field(default=None, max_length=50)
    recommendation_id: str | None = Field(default=None, max_length=64)
    predicted_yield_t_ha: float | None = Field(default=None, ge=0)
    actual_yield_t_ha: float | None = Field(default=None, ge=0)
    accepted: bool = False
    matured_within_lag: bool = False


class TemporalCoherenceRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    planting_date: str | None = None
    gdd_days_counted: int | None = None


class AstronomicalCrossCheckRequest(BaseModel):
    current_date: str  # YYYY-MM-DD
    gdd_stage: str | None = None
    anchor: str = "suhail_rising"


class ChemicalCheckRequest(BaseModel):
    chemical: str
    dose_kg_ha: float | None = None


class RegisterCameraRequest(BaseModel):
    camera_id: str
    field_id: str
    name_ar: str
    camera_type: str = "fixed"  # fixed|mobile|timelapse
    lat: float | None = None
    lon: float | None = None
    capture_interval_min: int | None = None
    note_ar: str = ""


class SnapshotEvidenceRequest(BaseModel):
    snapshot_id: str
    camera_id: str
    field_id: str
    media_uri: str
    captured_at: str
    linked_pin_id: str | None = None
    note_ar: str = ""


class StressRiskRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float


class IntegratedAdviceRequest(BaseModel):
    crop: str = "wheat"
    stage_key: str
    depletion_pct: float
    net_irrigation_mm: float | None = None


class SalinityRequest(BaseModel):
    ece_dsm: float | None = None  # ملوحة التربة
    ecw_dsm: float | None = None  # ملوحة ماء الريّ
    sar: float | None = None  # نسبة امتصاص الصوديوم
    crop_threshold_ece: float | None = None  # عتبة تحمّل المحصول


class SeedSourceRequest(BaseModel):
    certified: bool
    purity_pct: float | None = None
    germination_pct: float | None = None


class FieldFitRequest(BaseModel):
    crop: str
    ph: float
    ec_dsm: float
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True


class InternalAIAdviceEventRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    field_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    selected_imagery_date: str | None = None
    endpoint_mode: str = "chat"
    model_output: str | None = Field(default=None, max_length=32768)


class ImageryFieldRegister(BaseModel):
    field_id: str
    bbox: list[float]  # [west, south, east, north]


class OnboardingSubmitRequest(BaseModel):
    field_id: str | None = None
    answers: dict = {}


class WaterAnalysisRequest(BaseModel):
    sample_id: str
    # نوع مصدر الماء: مفردات v168 (WaterSourceType في core، WATER_SOURCE_OPTIONS في الواجهة)
    # — لا نصّ حرّ: «field:<اسم>» ليس مصدر ماء، والربط بحقل مسار المختبر لا هذا الحساب.
    source: WaterSourceType = "well"
    # حسابٌ لا يُخزَّن: لا ربط بحقل هنا. كان field_id يُسقَط صامتاً فيُظَنّ الربط قائماً؛
    # الآن يُرفض صراحةً (422) ويُوجَّه إلى مسار المختبر المُخزَّن المرتبط بحقل المستأجِر.
    field_id: None = Field(
        default=None,
        description=(
            "Not accepted: water-analysis is a calculation and is not stored or bound to a"
            " field. Record a field-bound result via /api/v1/lab/samples and"
            " /api/v1/lab/water-results."
        ),
    )

    @field_validator("field_id", mode="before")
    @classmethod
    def _field_binding_not_supported(cls, value):
        if value is not None:
            raise ValueError(
                "water-analysis is a calculation and is not saved to a field; record a"
                " field-bound lab water result via /api/v1/lab/water-results"
            )
        return value

    na: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ca: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    mg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    hco3: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    co3: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cl: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ec_dsm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ph: float | None = Field(default=None, ge=0, le=14, allow_inf_nan=False)
    sampled_at: str | None = None


class PestEscalationRequest(BaseModel):
    workflow_id: str
    field_id: str | None = None
    season_id: str | None = None
    diagnosis_ref: str | None = None
    evidence_ref: str | None = None
    pest_type: str | None = None
    severity: float = 0.0
    # للاستئناف بعد التعليق: موافقة الخبير (approved) أو رفضه (rejected)
    approval_status: str | None = None
