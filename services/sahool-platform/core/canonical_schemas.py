"""
sahool_core.canonical_schemas
==============================
عقود البيانات (Data Contracts) — التعريف الموحّد للكيانات الأساسية.

الفجوة المسدودة: التعريفات كانت موزّعة على dataclasses في وحدات
متفرّقة (RecommendationRecord في learning/، Activity في activity_log،
HistoricalRow في historical_loader). لا وثيقة موحّدة. التوسّع
لمستأجرين جدد، مديريات، تكاملات = ارتباك مستمرّ.

هذا الملف:
  • يعرّف الكيانات الجوهرية بـschema_version صريح
  • لا يستبدل الـdataclasses الموجودة (التوافق الخلفي محفوظ)
  • يوفّر validation hooks تستدعى عند الحدود (API، imports)
  • يُغذّي التوثيق الآلي ومراجعة العقود

المبادئ:
  • schema_version لكل كيان (تطوّر متتبَّع، لا breaking change صامت)
  • النواة محايدة: العقود تصف، لا تنفّذ
  • الصدق: required vs optional صريح، لا "غامض"
  • Multi-tenant مدمج: tenant_id إلزامي في كل كيان

الكيانات السبعة الجوهرية:
  1. Tenant          — حاوية المستأجر (شركة/جمعية/فرد)
  2. User            — مستخدم (سيدخل RBAC)
  3. Farm            — مزرعة (Farm hierarchy التالي)
  4. Field           — حقل (موجود، يُوحّد هنا)
  5. CropSeason      — موسم محصول (Crop Zone القياسي)
  6. Observation     — مشاهدة/قياس (EAV الموجود)
  7. Recommendation  — توصية (موجود في learning/، يُوحّد)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any


# ─── إصدارات schemas ─────────────────────────────────────────────
# كل تغيير في حقول إلزامية = bump version
# توافق خلفي: قراءة v1 ممكنة من v2 (defaults للحقول الجديدة)
SCHEMA_VERSIONS = {
    "Tenant":         "1.0",
    "User":           "1.0",
    "Farm":           "1.0",
    "Field":          "1.0",
    "CropSeason":     "1.0",
    "Observation":    "1.0",
    "Recommendation": "2.0",   # 2.0 بسبب إضافة provenance
}


# ─── Enums مشتركة ────────────────────────────────────────────────

class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class UserRole(str, Enum):
    """خمسة أدوار من المراجعة الاستراتيجية. ترتيب الصلاحيات تنازلي."""
    OWNER = "owner"             # كل الصلاحيات + إدارة الفريق
    MANAGER = "manager"         # إدارة الحقول والتوصيات
    AGRONOMIST = "agronomist"   # توصيات + معايرة + بحث، لا إدارة
    WORKER = "worker"           # تنفيذ الأنشطة، تسجيل القياسات
    VIEWER = "viewer"           # قراءة فقط


class FieldQuality(str, Enum):
    """من field_lifecycle الموجود — يُوحَّد هنا للمرجعية."""
    BLOCKED = "BLOCKED"
    LIMITED = "LIMITED"
    PENDING_LAB = "PENDING_LAB"
    READY = "READY"


class IrrigationMethod(str, Enum):
    FLOOD = "flood"
    DRIP = "drip"
    SPRINKLER = "sprinkler"
    RAINFED = "rainfed"
    SUPPLEMENTAL = "supplemental"   # تكميلي (موجود في supplemental_irrigation)
    PIVOT = "pivot"


class SeasonStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    HARVESTED = "harvested"
    FALLOW = "fallow"
    FAILED = "failed"


# ─── 1. Tenant ────────────────────────────────────────────────────

@dataclass
class TenantSchema:
    """حاوية المستأجر (شركة/جمعية/فرد).

    العزل التشغيلي: كل tenant معزول كلّياً عن غيره.
    لا يوجد cross-tenant queries في النواة (مُحرَّس آلياً)."""
    tenant_id: str                          # دائم، لا يتغيّر
    name_ar: str                            # الاسم العربي
    name_en: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: str = ""                    # ISO datetime
    id_uuid: str | None = None              # Dual-ID
    schema_version: str = SCHEMA_VERSIONS["Tenant"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"tenant_id", "name_ar"}


# ─── 2. User ──────────────────────────────────────────────────────

@dataclass
class UserSchema:
    """مستخدم — أساس RBAC.

    user_id + tenant_id يحدّد العضوية. مستخدم في عدّة tenants =
    سجلات منفصلة (تجنّب complexity الـmany-to-many في النواة)."""
    user_id: str
    tenant_id: str                          # عضوية tenant
    role: UserRole
    name_ar: str
    email: str | None = None
    phone: str | None = None
    farm_ids_access: list[str] = field(default_factory=list)  # null/empty = كل المزارع
    is_active: bool = True
    created_at: str = ""
    last_login_at: str | None = None
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["User"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"user_id", "tenant_id", "role", "name_ar"}


# ─── 3. Farm (Farm Hierarchy) ─────────────────────────────────────

@dataclass
class FarmSchema:
    """المزرعة — حاوية الحقول (Farm Hierarchy التالي).

    لا geometry مطلوبة على مستوى المزرعة (الحدود على الحقول).
    Property الكبير في Cropwise = مزرعة لدينا (نطاق سهول أبسط)."""
    farm_id: str
    tenant_id: str
    name_ar: str
    district_id: str | None = None          # المديرية الإدارية
    governorate_id: str | None = None       # المحافظة
    centroid_lon: float | None = None       # نقطة تعريفية فقط
    centroid_lat: float | None = None
    owner_user_id: str | None = None        # المالك في tenant_id
    created_at: str = ""
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["Farm"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"farm_id", "tenant_id", "name_ar"}


# ─── 4. Field ─────────────────────────────────────────────────────

@dataclass
class FieldSchema:
    """الحقل — الكيان المكاني الأساسي.

    boundary GeoJSON (لا PostGIS مطلوبة في النواة). area_ha
    محسوب لكن يُحفظ (مرجعية سريعة بدون geometry parsing)."""
    field_id: str
    tenant_id: str
    farm_id: str                            # ينتمي لمزرعة (Farm hierarchy)
    name_ar: str
    boundary_geojson: dict | None = None    # GeoJSON Polygon
    area_ha: float | None = None
    quality_state: FieldQuality = FieldQuality.BLOCKED
    soil_type: str | None = None            # من تحليل أو تقدير
    water_source: str | None = None
    notes_ar: str | None = None
    created_at: str = ""
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["Field"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"field_id", "tenant_id", "farm_id", "name_ar"}


# ─── 5. CropSeason (Crop Zone القياسي) ────────────────────────────

@dataclass
class CropSeasonSchema:
    """ربط حقل بمحصول لموسم. القيد العالمي: (field_id, season_id) فريد.

    يجسّد Crop Zone من Cropwise بشكل مبسّط مناسب لسياقنا."""
    season_id: str
    tenant_id: str
    field_id: str
    crop_id: str                            # من crop_cards/
    season_name_ar: str                     # "صيف 2026"، "شتاء 2025-2026"
    season_year: int
    variety_id: str | None = None
    planting_date: str | None = None        # ISO
    estimated_harvest_date: str | None = None
    actual_harvest_date: str | None = None
    irrigation_method: IrrigationMethod = IrrigationMethod.RAINFED
    seed_rate_kg_ha: float | None = None
    status: SeasonStatus = SeasonStatus.PLANNED
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["CropSeason"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"season_id", "tenant_id", "field_id", "crop_id",
                "season_name_ar", "season_year"}


# ─── 6. Observation (EAV الموجود) ─────────────────────────────────

class ObservationSource(str, Enum):
    MANUAL = "manual"           # إدخال يدوي
    SENSOR = "sensor"           # من مستشعر (sensor_intake)
    LAB = "lab"                 # تحليل مخبري (دليل)
    SATELLITE = "satellite"     # قمر صناعي (NDVI)
    DRONE = "drone"
    HISTORICAL = "historical"   # من historical_loader


@dataclass
class ObservationSchema:
    """قياس/مشاهدة. يتطابق مع جدول observations EAV الموجود.

    observable_id من ontology محدّدة (soil_ec_ds_m، ndvi، ...).
    قيمة مفردة + وحدة + ثقة + مصدر + موقع اختياري."""
    observation_id: str
    tenant_id: str
    field_id: str
    observable_id: str                      # المتغيّر المُقاس
    value: float
    unit: str                               # SI canonical
    source: ObservationSource
    confidence: str                         # low/medium/high
    measured_at: str                        # ISO
    method: str | None = None
    device_id: str | None = None
    lon: float | None = None
    lat: float | None = None
    created_at: str = ""
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["Observation"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"observation_id", "tenant_id", "field_id",
                "observable_id", "value", "unit", "source",
                "confidence", "measured_at"}


# ─── 7. Recommendation (مع Provenance v2.0) ──────────────────────

@dataclass
class RecommendationSchema:
    """توصية موحّدة. v2.0 يضمّن provenance (من recommendation_replay).

    التوصيات قبل v2.0 لا تحوي provenance — تُعامَل بشكل صريح
    في recommendation_replay (declared honestly، not invented)."""
    rec_id: str
    tenant_id: str
    field_id: str | None = None             # null = توصية مستوى مزرعة
    season_id: str | None = None
    crop: str | None = None
    issued_date: str = ""
    recommendation_ar: str = ""
    quality_grade: FieldQuality = FieldQuality.BLOCKED
    predicted_value: float | None = None
    predicted_unit: str | None = None
    confidence: str = "low"
    # forensic (v2.0)
    provenance: dict | None = None          # RecommendationProvenance
    # outcome (يُملأ لاحقاً)
    actual_value: float | None = None
    outcome_date: str | None = None
    error_pct: float | None = None
    id_uuid: str | None = None
    schema_version: str = SCHEMA_VERSIONS["Recommendation"]

    @staticmethod
    def required_fields() -> set[str]:
        return {"rec_id", "tenant_id", "issued_date", "recommendation_ar"}


# ─── Validation Hooks (تُستدعى عند الحدود) ───────────────────────

@dataclass
class ValidationResult:
    valid: bool
    missing_fields: list[str] = field(default_factory=list)
    invalid_values: list[str] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)


def validate_entity(entity_data: dict, schema_class) -> ValidationResult:
    """يتحقّق أن dict يلتزم بـschema. يُستدعى عند:
      • استيراد من API
      • قراءة من historical_loader
      • قبل INSERT في قاعدة البيانات

    لا يجبر — يبلّغ. القرار للطبقة الأعلى (يرفض/يحذّر/يقبل)."""
    result = ValidationResult(valid=True)

    required = schema_class.required_fields()
    for f_name in required:
        if f_name not in entity_data or entity_data[f_name] in (None, "", []):
            result.missing_fields.append(f_name)
            result.valid = False

    # تحقّقات نوعية بسيطة (الـschema dataclass يفعل الباقي)
    if "tenant_id" in entity_data:
        tid = entity_data["tenant_id"]
        if not isinstance(tid, str) or len(tid) < 3:
            result.invalid_values.append("tenant_id يجب أن يكون نصّاً (≥3 حروف)")
            result.valid = False

    # تحذيرات ناعمة
    if "schema_version" not in entity_data:
        result.warnings_ar.append(
            "schema_version غير محدّد — يُفترض الافتراضي الحالي")

    return result


def entities_catalog() -> dict:
    """فهرس بكل الكيانات + إصداراتها + حقولها الإلزامية.

    يستخدمه التوثيق الآلي + skills_registry لاحقاً."""
    return {
        "Tenant": {
            "version": SCHEMA_VERSIONS["Tenant"],
            "required": list(TenantSchema.required_fields()),
            "class": "TenantSchema",
        },
        "User": {
            "version": SCHEMA_VERSIONS["User"],
            "required": list(UserSchema.required_fields()),
            "class": "UserSchema",
        },
        "Farm": {
            "version": SCHEMA_VERSIONS["Farm"],
            "required": list(FarmSchema.required_fields()),
            "class": "FarmSchema",
        },
        "Field": {
            "version": SCHEMA_VERSIONS["Field"],
            "required": list(FieldSchema.required_fields()),
            "class": "FieldSchema",
        },
        "CropSeason": {
            "version": SCHEMA_VERSIONS["CropSeason"],
            "required": list(CropSeasonSchema.required_fields()),
            "class": "CropSeasonSchema",
        },
        "Observation": {
            "version": SCHEMA_VERSIONS["Observation"],
            "required": list(ObservationSchema.required_fields()),
            "class": "ObservationSchema",
        },
        "Recommendation": {
            "version": SCHEMA_VERSIONS["Recommendation"],
            "required": list(RecommendationSchema.required_fields()),
            "class": "RecommendationSchema",
        },
    }
