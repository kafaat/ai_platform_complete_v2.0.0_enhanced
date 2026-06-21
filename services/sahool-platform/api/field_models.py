"""api/field_models.py — نماذج ومساعدات نطاق الحقول (Fields) — تفكيك B1.

العنقود الأكبر المُستخرَج من الوحدة الضخمة ``api/main.py`` (نمط B1: تقليص
god-module): نماذج Pydantic للحقل (ملخّص/تفاصيل/إنشاء/استيراد/تحديث/توصية) +
مُطبِّعات الصفوف (DB→نموذج) + بنّاء التحديث الجزئيّ + أعمدة SELECT + مُرشِّح
التداخل المعتبَر. كلّها **منطق نماذج صرف** (pydantic + stdlib فقط) بلا I/O وبلا
أيّ تبعيّة على ``api.main`` — فتُستورَد من ``routers/fields`` و``routers/recommendations``
والاختبارات مباشرةً.

تبقى في ``api.main`` المساعِدات العامّة غير الخاصّة بالحقل (``_clamp_list_window``،
``_build_versioned_update`` المشترك مع المواسم) ومساعِدات الترميز الجغرافيّ
(``_centroid_from_bbox``/``_reverse_geocode`` — يستخدمها أيضاً ``routers/geo``)،
ومعالِج الحفظ ``_persist_field`` (I/O على القاعدة) انتقل إلى ``routers/fields``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FieldSummary(BaseModel):
    """ملخّص حقل للقائمة (HomeScreen)."""

    field_id: str
    farm_id: str
    name_ar: str
    crop: str
    area_ha: float
    quality_grade: str  # READY/LIMITED/PENDING_LAB/BLOCKED
    last_observation_at: str | None = None
    pending_activities: int = 0
    health_summary_ar: str  # "صحّي" / "يحتاج ريّ" / "إجهاد ملحي"
    soil_type: str | None = None  # نوع التربة (يُمرَّر للواجهة بدل ضياعه)
    manager: str | None = None  # المسؤول عن الحقل
    # حقول مُثراة (v33): كود الحقل + مصدر الماء + الملكيّة + الكشف الآلي للموقع.
    field_code: str | None = None  # كود الحقل (مرجع المزارع)
    description: str | None = None  # وصف حرّ
    water_source: str | None = None  # well/canal/river/rainfed/tank/mixed
    ownership_type: str | None = None  # نوع الملكيّة
    country: str | None = None  # الدولة (مكتشفة آليّاً من المركز)
    region: str | None = None  # الإقليم/المحافظة (مكتشفة آليّاً من المركز)
    # حقول الخريطة (اختياريّة، توافق خلفيّ): مركز الحقل وهندسته لرسم المضلّع.
    lat: float | None = None
    lon: float | None = None
    geometry: dict | None = None


# ─── تفاصيل الحقل المتقدّمة (v37) — ملء تدريجيّ بعد الإنشاء ────────
# القائمة (list_fields) تبقى رشيقة؛ هذه الأعمدة تُقرأ عبر GET /fields/{id}
# وتُحدَّث جزئيّاً عبر PATCH /fields/{id}. مصدر واحد لأسماء الأعمدة (يُعاد
# استخدامه في SELECT التفصيليّ وفي بنّاء التحديث الجزئيّ + الاختبارات).
# أعمدة أساسيّة قابلة للتعديل عبر PATCH (اسم الحقل ومحصوله). منفصلة عن المتقدّمة
# لأنّ الأخيرة تُعاد استخدامها في _FIELD_DETAIL_SELECT الذي يسرد name/crop سلفاً —
# فإضافتهما هناك تُكرّر العمود. تُستعمل هذه فقط في بناء جملة UPDATE.
_FIELD_BASIC_COLUMNS: tuple[str, ...] = (
    "name",
    "crop",
)

_FIELD_ADVANCED_COLUMNS: tuple[str, ...] = (
    "soil_ph",
    "soil_ec",
    "soil_om",
    "soil_n",
    "soil_p",
    "soil_k",
    "elevation_m",
    "slope_pct",
    "aspect",
    "climate_zone",
    "zone_key",  # v49: مفتاح الإقليم القانوني (agro_climate_zones) — يُفعّل تحليل السوق الإقليمي
    "annual_rainfall_mm",
    "owner_name",
    "lease_years",
    "registry_no",
    # نموذج الريّ/المياه التفصيليّ (v41) — ملء تدريجيّ عبر PATCH (Progressive Profiling)
    "irrigation_type",
    "irrigation_efficiency_pct",
    "flow_rate_m3h",
    "pump_type",
    "well_depth_m",
    "water_ec",
    # ربط المدير بمستخدم حقيقيّ (v41) — إضافيّ بجانب manager النصّيّ
    "manager_user_id",
)

# حدّ التداخل المعتبَر (م²) — أكبر منه ⇒ تداخل حقيقيّ لا مجرّد ملامسة حدود/انزياح GPS.
_MIN_FIELD_OVERLAP_M2 = 25.0


def _significant_overlaps(overlaps, min_m2: float = _MIN_FIELD_OVERLAP_M2) -> list:
    """يُرشّح صفوف التداخل بحيث يبقى ما تجاوزت مساحة تقاطعه الحدّ — دالّة نقيّة (لا DB).

    يقبل صفوف asyncpg.Record أو dict (كلاهما يدعم o["overlap_m2"]). قيمة None تُعامَل
    كصفر. يُستخدَم لتحويل قرار «تداخل معتبَر» إلى منطق قابل للاختبار offline.
    """
    return [o for o in overlaps if (o["overlap_m2"] or 0.0) > min_m2]


class FieldDetail(FieldSummary):
    """تفاصيل حقل كاملة (لوحة التفاصيل) — يرث الملخّص ويضيف الأعمدة المتقدّمة.

    كلّها اختياريّة (ملء تدريجيّ): كيمياء التربة + المناخ الدقيق + الملكيّة.
    """

    # كيمياء التربة (نتائج مختبر)
    soil_ph: float | None = None
    soil_ec: float | None = None
    soil_om: float | None = None  # المادّة العضويّة %
    soil_n: float | None = None
    soil_p: float | None = None
    soil_k: float | None = None
    # المناخ الدقيق / التضاريس
    elevation_m: float | None = None
    slope_pct: float | None = None
    aspect: str | None = None
    climate_zone: str | None = None
    zone_key: str | None = None
    annual_rainfall_mm: float | None = None
    # تفاصيل الملكيّة
    owner_name: str | None = None
    lease_years: int | None = None
    registry_no: str | None = None
    # الريّ/المياه التفصيليّ (v41)
    irrigation_type: str | None = None  # drip/pivot/flood/sprinkler/rainfed/subsurface
    irrigation_efficiency_pct: float | None = None
    flow_rate_m3h: float | None = None  # تدفّق المضخّة م³/ساعة
    pump_type: str | None = None
    well_depth_m: float | None = None
    water_ec: float | None = None  # ملوحة الماء dS/m
    manager_user_id: int | None = None  # FK إلى users(id) (v47)
    row_version: int | None = None  # عمّاد التزامن التفاؤليّ (v61) — يتزايد كلّ تحديث


class FieldUpdateRequest(BaseModel):
    """طلب تحديث جزئيّ لتفاصيل حقل — كلّ الحقول اختياريّة (ملء تدريجيّ).

    تُحدَّث الأعمدة المُرسَلة فقط (الموجودة في الـpayload) — لا تُمسح غير المُرسَلة.
    التمييز بين «لم يُرسَل» و«أُرسِل null» عبر model_fields_set (انظر _build_field_update).
    """

    # أساسيّة قابلة للتعديل (اسم/محصول الحقل) — تُمكّن زرّ «تعديل الحقل» من الحفظ.
    name: str | None = Field(default=None, min_length=1, max_length=100)
    crop: str | None = Field(default=None, max_length=50)
    soil_ph: float | None = Field(default=None, ge=0, le=14)
    soil_ec: float | None = Field(default=None, ge=0)
    soil_om: float | None = Field(default=None, ge=0)  # المادّة العضويّة %
    soil_n: float | None = Field(default=None, ge=0)
    soil_p: float | None = Field(default=None, ge=0)
    soil_k: float | None = Field(default=None, ge=0)
    elevation_m: float | None = None
    slope_pct: float | None = Field(default=None, ge=0)
    aspect: str | None = Field(default=None, max_length=20)
    climate_zone: str | None = Field(default=None, max_length=40)
    zone_key: str | None = Field(default=None, max_length=64)
    annual_rainfall_mm: float | None = Field(default=None, ge=0)
    owner_name: str | None = Field(default=None, max_length=100)
    lease_years: int | None = Field(default=None, ge=0)
    registry_no: str | None = Field(default=None, max_length=50)
    # الريّ/المياه التفصيليّ (v41)
    irrigation_type: str | None = Field(default=None, max_length=20)
    irrigation_efficiency_pct: float | None = Field(default=None, ge=0, le=100)
    flow_rate_m3h: float | None = Field(default=None, ge=0)
    pump_type: str | None = Field(default=None, max_length=30)
    well_depth_m: float | None = Field(default=None, ge=0)
    water_ec: float | None = Field(default=None, ge=0)
    manager_user_id: int | None = Field(default=None, ge=1)  # FK users(id) (v47)
    # تزامن تفاؤليّ (v61، اختياريّ/متوافق رجعيّاً): إصدار الحقل الأساس وقت قراءة
    # العميل. إن مُرِّر ولم يطابق row_version الحاليّ ⇒ 409 تعارض (كشف تعديل متباعد
    # offline). ليس عموداً يُكتَب — مستثنى من _build_field_update (ليس في الأعمدة).
    base_version: int | None = Field(default=None, ge=1)
    # دمج آليّ 3-way (اختياريّ): قيم الأعمدة كما قرأها العميل وقت base_version. عند
    # تعارض الإصدار، إن كان الخادم لم يمسّ عموداً (server == base) فتغيير العميل عليه
    # آمن ⇒ يُدمَج آليّاً؛ التعارض الحقيقيّ فقط حين غيّر الطرفان العمود نفسه. ليس
    # عموداً يُكتَب — مستثنى من _build_field_update (ليس في الأعمدة).
    base_values: dict | None = Field(default=None)


def _build_field_update(req: FieldUpdateRequest) -> tuple[str, list]:
    """يبني جملة SET للتحديث الجزئيّ من الحقول المُرسَلة فقط — دالّة نقيّة (لا DB).

    يُرجِع (set_clause, values) حيث set_clause = "col1 = $1, col2 = $2 …" والقيم
    بالترتيب نفسه. تُستخدَم القيم لاحقاً بعد إلحاق معرّف الحقل ($N) في WHERE.
    يُميّز «لم يُرسَل» (يُتجاهَل) عن «أُرسِل null» (يُمسح العمود) عبر model_fields_set.

    يرفع ValueError لو لم تُرسَل أيّ حقول — لا UPDATE فارغ (يعالجه الـendpoint 422).
    """
    sent = req.model_fields_set
    data = req.model_dump()
    assignments: list[str] = []
    values: list = []
    idx = 1
    for col in (*_FIELD_BASIC_COLUMNS, *_FIELD_ADVANCED_COLUMNS):
        if col in sent:
            assignments.append(f"{col} = ${idx}")
            values.append(data[col])
            idx += 1
    if not assignments:
        raise ValueError("no fields to update")
    return ", ".join(assignments), values


class FieldRecommendationRequest(BaseModel):
    field_id: str
    farm_id: str = ""
    crop: str
    current_indicators: dict = Field(default_factory=dict)
    growth_stage: str | None = None
    district_id: str | None = None


def _row_to_field_summary(r) -> FieldSummary:
    """صفّ DB → FieldSummary (يفكّ geometry لو رجعت نصّاً من JSONB)."""
    import json as _json

    def _opt(key):
        # عمود اختياري قد يغيب (صفّ قديم/اختبار) — None بدل KeyError
        try:
            return r[key]
        except (KeyError, IndexError):
            return None

    geom = r["geometry"]
    if isinstance(geom, str):
        try:
            geom = _json.loads(geom)
        except (ValueError, TypeError):
            geom = None
    return FieldSummary(
        field_id=r["field_id"],
        farm_id=r["farm_id"] or "",
        name_ar=r["name"],
        crop=r["crop"] or "—",
        area_ha=float(r["area_ha"]) if r["area_ha"] is not None else 0.0,
        quality_grade="READY",
        health_summary_ar="—",
        soil_type=r["soil_type"],
        manager=r["manager"],
        field_code=_opt("field_code"),
        description=_opt("description"),
        water_source=_opt("water_source"),
        ownership_type=_opt("ownership_type"),
        country=_opt("country"),
        region=_opt("region"),
        lat=float(r["lat"]) if r["lat"] is not None else None,
        lon=float(r["lon"]) if r["lon"] is not None else None,
        geometry=geom,
    )


class FieldCreateRequest(BaseModel):
    """طلب إنشاء حقل من مضلّع مرسوم على الخريطة."""

    name: str = Field(min_length=1, max_length=100)
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    geometry: dict  # GeoJSON Polygon: {"type":"Polygon","coordinates":[[[lon,lat],...]]}
    farm_id: str | None = None
    gov: str | None = None
    # حقول مُثراة (v33): اختياريّة. country/region تُكتشف آليّاً إن لم تُرسَل.
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)


class FieldImportRequest(BaseModel):
    """طلب استيراد حدّ حقل من ملفّ (GeoJSON/KML) أو نقاط GPS بدل الرسم اليدويّ.

    format يحدّد المصدر: 'geojson'/'kml' يستخدمان content (نصّ الملفّ)؛ 'gps'
    يستخدم points ([[lon,lat],...] مسار المشي). بقيّة الحقول كـFieldCreateRequest
    (تُمرَّر لنفس مسار الحفظ المشترك).
    """

    format: Literal["geojson", "kml", "gps"]
    content: str | None = None
    points: list[list[float]] | None = None
    name: str = Field(min_length=1, max_length=100)
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    farm_id: str | None = None
    gov: str | None = None
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)


def _row_to_field_detail(r) -> FieldDetail:
    """صفّ DB (مع الأعمدة المتقدّمة) → FieldDetail. يعيد استخدام تطبيع الملخّص ثمّ
    يضيف الأعمدة المتقدّمة (v37). NUMERIC من asyncpg يأتي Decimal ⇒ float للـJSON."""
    base = _row_to_field_summary(r)

    def _f(key):
        try:
            v = r[key]
        except (KeyError, IndexError):
            return None
        return float(v) if v is not None else None

    def _s(key):
        try:
            return r[key]
        except (KeyError, IndexError):
            return None

    def _i(key):
        try:
            v = r[key]
        except (KeyError, IndexError):
            return None
        return int(v) if v is not None else None

    return FieldDetail(
        **base.model_dump(),
        soil_ph=_f("soil_ph"),
        soil_ec=_f("soil_ec"),
        soil_om=_f("soil_om"),
        soil_n=_f("soil_n"),
        soil_p=_f("soil_p"),
        soil_k=_f("soil_k"),
        elevation_m=_f("elevation_m"),
        slope_pct=_f("slope_pct"),
        aspect=_s("aspect"),
        climate_zone=_s("climate_zone"),
        zone_key=_s("zone_key"),
        annual_rainfall_mm=_f("annual_rainfall_mm"),
        owner_name=_s("owner_name"),
        lease_years=_i("lease_years"),
        registry_no=_s("registry_no"),
        irrigation_type=_s("irrigation_type"),
        irrigation_efficiency_pct=_f("irrigation_efficiency_pct"),
        flow_rate_m3h=_f("flow_rate_m3h"),
        pump_type=_s("pump_type"),
        well_depth_m=_f("well_depth_m"),
        water_ec=_f("water_ec"),
        manager_user_id=_i("manager_user_id"),
        row_version=_i("row_version"),
    )


# أعمدة SELECT لقراءة الحقل التفصيليّة: أساس الملخّص + الأعمدة المتقدّمة (v37).
_FIELD_DETAIL_SELECT = (
    "field_id, farm_id, name, area_ha, crop, soil_type, manager, "
    "field_code, description, water_source, ownership_type, country, region, "
    "lat, lon, geometry, row_version, " + ", ".join(_FIELD_ADVANCED_COLUMNS)
)
