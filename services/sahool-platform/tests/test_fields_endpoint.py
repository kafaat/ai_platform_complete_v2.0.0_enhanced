"""اختبارات نقطة الحقول (GET/POST /api/v1/fields) — الأجزاء الصرفة offline.

تغطّي: حساب المركز من bbox، تطبيع صفّ DB → FieldSummary (بما فيه فكّ
geometry من JSONB نصّاً)، وتحقّق الهندسة الذي يعتمد عليه POST (يرفض المضلّع
المتقاطع ذاتيّاً، يقبل مضلّعاً سليماً داخل اليمن). لا حاجة لقاعدة بيانات.
"""

import json

from api.geospatial_integrity import validate_field_geometry
from api.main import (
    _FIELD_ADVANCED_COLUMNS,
    _MIN_FIELD_OVERLAP_M2,
    FieldCreateRequest,
    FieldUpdateRequest,
    _build_field_update,
    _build_versioned_update,
    _centroid_from_bbox,
    _clamp_list_window,
    _row_to_field_summary,
    _significant_overlaps,
)
from api.season_models import SeasonCreateRequest, SeasonUpdateRequest, _row_to_season


def test_centroid_from_bbox_uses_lng_keys():
    # مفاتيح lng (لا lon) لمطابقة compute_bbox
    bbox = {"min_lat": 14.0, "max_lat": 16.0, "min_lng": 44.0, "max_lng": 46.0}
    lat, lon = _centroid_from_bbox(bbox)
    assert lat == 15.0
    assert lon == 45.0


def test_centroid_from_bbox_handles_missing():
    assert _centroid_from_bbox(None) == (None, None)
    assert _centroid_from_bbox({"min_lat": 1}) == (None, None)  # مفاتيح ناقصة


def test_row_to_field_summary_parses_jsonb_string():
    geom = {
        "type": "Polygon",
        "coordinates": [[[45.5, 15.0], [45.6, 15.0], [45.6, 15.1], [45.5, 15.0]]],
    }
    row = {
        "field_id": "fld_abc",
        "farm_id": None,
        "name": "حقل وادي سبأ",
        "area_ha": 12.5,
        "crop": "wheat",
        "soil_type": "loam",
        "manager": "أبو محمد",
        "lat": 15.05,
        "lon": 45.55,
        "geometry": json.dumps(geom),  # JSONB يرجع نصّاً من asyncpg افتراضيّاً
    }
    fs = _row_to_field_summary(row)
    assert fs.field_id == "fld_abc"
    assert fs.farm_id == ""  # None → "" (FieldSummary.farm_id إلزاميّ)
    assert fs.name_ar == "حقل وادي سبأ"
    assert fs.area_ha == 12.5
    assert fs.geometry == geom  # فُكّ النصّ إلى dict
    assert fs.lat == 15.05 and fs.lon == 45.55
    assert fs.soil_type == "loam"
    assert fs.manager == "أبو محمد"  # المسؤول يُمرَّر بدل ضياعه


def test_db_unavailable_maps_to_503():
    # أخطاء DB (هجرة/اتّصال) تُحوَّل إلى 503 موثَّق لا 500
    from api.main import _db_unavailable

    exc = _db_unavailable("قراءة الحقول", RuntimeError("connection reset"))
    assert exc.status_code == 503
    assert "قراءة الحقول" in exc.detail


def test_field_create_request_requires_geometry():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FieldCreateRequest(name="حقل", crop="wheat")  # geometry مفقود


def test_validate_geometry_accepts_good_yemen_polygon():
    # مضلّع صغير سليم داخل اليمن (إغلاق صريح)
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[45.50, 15.00], [45.52, 15.00], [45.52, 15.02], [45.50, 15.02], [45.50, 15.00]]
        ],
    }
    result = validate_field_geometry(geom)
    assert result.valid is True
    assert result.computed_bbox is not None
    lat, lon = _centroid_from_bbox(result.computed_bbox)
    assert 14.9 < lat < 15.1 and 45.4 < lon < 45.6


def test_validate_geometry_rejects_self_intersecting():
    # شكل الفراشة (bowtie) — تقاطع ذاتيّ ⇒ غير صالح
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[45.50, 15.00], [45.52, 15.02], [45.52, 15.00], [45.50, 15.02], [45.50, 15.00]]
        ],
    }
    result = validate_field_geometry(geom)
    assert result.valid is False


# ─── فحص التداخل الهندسيّ (v43) — منطق «التداخل المعتبَر» النقيّ ───────────


def test_significant_overlaps_filters_below_threshold():
    # تقاطع أصغر من الحدّ (ملامسة/انزياح) ⇒ لا يُعتبر تداخلاً.
    rows = [{"field_id": "f1", "name": "A", "overlap_m2": _MIN_FIELD_OVERLAP_M2 - 1}]
    assert _significant_overlaps(rows) == []


def test_significant_overlaps_keeps_above_threshold():
    rows = [{"field_id": "f1", "name": "A", "overlap_m2": _MIN_FIELD_OVERLAP_M2 + 50}]
    assert len(_significant_overlaps(rows)) == 1


def test_significant_overlaps_treats_none_as_zero():
    rows = [{"field_id": "f1", "name": "A", "overlap_m2": None}]
    assert _significant_overlaps(rows) == []


# ─── أعمدة الريّ/المياه المتقدّمة (v41) — مسار PATCH ──────────────────────


def test_advanced_columns_include_irrigation_water_model():
    for col in (
        "irrigation_type",
        "irrigation_efficiency_pct",
        "flow_rate_m3h",
        "pump_type",
        "well_depth_m",
        "water_ec",
        "manager_user_id",
    ):
        assert col in _FIELD_ADVANCED_COLUMNS


def test_build_field_update_emits_only_sent_advanced_columns():
    req = FieldUpdateRequest(irrigation_type="drip", well_depth_m=120.0)
    set_clause, values = _build_field_update(req)
    assert "irrigation_type = $1" in set_clause
    assert "well_depth_m = $2" in set_clause
    assert values == ["drip", 120.0]  # فقط المُرسَل، بالترتيب


# ─── تزامن تفاؤليّ: row_version + كشف تعارض offline (v61) ────────────────


def test_versioned_update_always_bumps_row_version():
    """بلا base_version: يُرفع row_version دائماً، WHERE = field_id فقط (سلوك رجعيّ)."""
    set_clause, values = _build_field_update(FieldUpdateRequest(irrigation_type="drip"))
    sql, exec_values = _build_versioned_update(set_clause, values, "field_01", None)
    assert "row_version = row_version + 1" in sql
    assert "WHERE field_id = $2" in sql
    assert "AND row_version" not in sql  # لا حارس تزامن
    assert exec_values == ["drip", "field_01"]


def test_versioned_update_adds_optimistic_guard_when_base_version_given():
    """مع base_version: يُضاف AND row_version = $N والقيمة تُلحَق آخر exec_values."""
    set_clause, values = _build_field_update(FieldUpdateRequest(irrigation_type="drip"))
    sql, exec_values = _build_versioned_update(set_clause, values, "field_01", 7)
    assert "row_version = row_version + 1" in sql
    assert "WHERE field_id = $2 AND row_version = $3" in sql
    assert exec_values == ["drip", "field_01", 7]


def test_field_update_request_accepts_base_version():
    """base_version اختياريّ (ge=1) وليس عموداً يُكتَب (غائب عن جملة SET)."""
    req = FieldUpdateRequest(irrigation_type="drip", base_version=3)
    assert req.base_version == 3
    set_clause, _ = _build_field_update(req)
    assert "base_version" not in set_clause  # ليس عمود DB


# ─── حدّ نافذة القائمة (limit/offset) — تقييد القوائم غير المحدودة ────────


def test_clamp_list_window_defaults_when_absent():
    """غياب limit/offset ⇒ الافتراضيّ (100) وoffset=0."""
    assert _clamp_list_window(None, None) == (100, 0)


def test_clamp_list_window_caps_at_maximum():
    """limit فوق السقف يُقصَر إلى 500 (يمنع over-fetch مهما طلب العميل)."""
    assert _clamp_list_window(10_000, 0) == (500, 0)


def test_clamp_list_window_enforces_floor_and_nonneg_offset():
    """limit<1 ⇒ 1، وoffset سالب ⇒ 0 (قيم آمنة للاستعلام)."""
    assert _clamp_list_window(0, -5) == (1, 0)
    assert _clamp_list_window(-3, -1) == (1, 0)


def test_clamp_list_window_passes_through_valid():
    """قيم ضمن المجال تمرّ كما هي."""
    assert _clamp_list_window(50, 20) == (50, 20)


# ─── KPIs الموسم (v42) ───────────────────────────────────────────────────


def test_season_create_request_accepts_kpis():
    req = SeasonCreateRequest(
        crops=["wheat"],
        target_yield_kg_ha=4200.0,
        plant_density=250.0,
        row_spacing_cm=20.0,
        seed_variety_source="ICARDA",
    )
    assert req.target_yield_kg_ha == 4200.0
    assert req.plant_density == 250.0
    assert req.row_spacing_cm == 20.0
    assert req.seed_variety_source == "ICARDA"


def test_row_to_season_maps_kpis():
    row = {
        "season_id": "ssn_1",
        "field_id": "fld_1",
        "crops": json.dumps(["wheat"]),
        "cultivar": "Saba",
        "irrigation_type": "drip",
        "seed_rate_kg_ha": 150.0,
        "land_leveling_date": None,
        "plowing_date": None,
        "sowing_date": None,
        "season_end": None,
        "stages": json.dumps([]),
        "status": "active",
        "created_at": None,
        "target_yield_kg_ha": 4200.0,
        "plant_density": 250.0,
        "row_spacing_cm": 20.0,
        "seed_variety_source": "ICARDA",
    }
    s = _row_to_season(row)
    assert s.target_yield_kg_ha == 4200.0
    assert s.plant_density == 250.0
    assert s.row_spacing_cm == 20.0
    assert s.seed_variety_source == "ICARDA"


# ─── تزامن تفاؤليّ للموسم (v64) — يكمّل v61 (fields) ──────────────────────


def test_season_update_request_accepts_base_version():
    """base_version اختياريّ (ge=1) ولا يُحسب حقلاً يُحدَّث (لا يدخل model_fields_set كعمود)."""
    req = SeasonUpdateRequest(cultivar="Saba", base_version=5)
    assert req.base_version == 5
    # base_version عمّاد تزامن لا عمود seasons ⇒ يجب ألّا يُعدّ ضمن أعمدة DB القابلة
    # للتحديث (update_season يبني updates من مفاتيح بعينها، base_version ليس منها).
    db_cols = {
        "crops",
        "cultivar",
        "irrigation_type",
        "seed_rate_kg_ha",
        "sowing_date",
        "season_end",
        "target_yield_kg_ha",
        "plant_density",
        "row_spacing_cm",
        "seed_variety_source",
        "maturity",
        "tillage_type",
        "actual_yield_kg_ha",
        "notes_ar",
    }
    assert "base_version" not in db_cols


def test_season_update_request_base_version_defaults_none():
    """غياب base_version ⇒ None (سلوك رجعيّ: لا فحص تعارض)."""
    assert SeasonUpdateRequest(cultivar="Saba").base_version is None


def test_row_to_season_maps_row_version():
    """_row_to_season يمرّر row_version (الإصدار الحاليّ يعود للعميل لمزامنته التالية)."""
    row = {
        "season_id": "ssn_1",
        "field_id": "fld_1",
        "crops": json.dumps(["wheat"]),
        "cultivar": "Saba",
        "irrigation_type": "drip",
        "seed_rate_kg_ha": None,
        "land_leveling_date": None,
        "plowing_date": None,
        "sowing_date": None,
        "season_end": None,
        "stages": json.dumps([]),
        "status": "active",
        "created_at": None,
        "row_version": 7,
    }
    assert _row_to_season(row).row_version == 7
    # غياب العمود (مثلاً SELECT قديم) ⇒ None بأمان (محروس بالمفاتيح).
    row.pop("row_version")
    assert _row_to_season(row).row_version is None


# ─── عقد أحداث domain (مسارات الكتابة تُصدر هذه الأنواع — يجب أن توجد) ─────


def test_domain_event_types_exist():
    # _emit_domain_event يبحث EventType[name]؛ خطأ مطبعيّ يُسقِط الحدث بصمت.
    from api.event_bus import EventType

    for name in (
        "FIELD_CREATED",
        "FIELD_DELETED",
        "SEASON_CREATED",
        "SEASON_CLOSED",
        "ACTIVITY_RECORDED",
    ):
        assert name in EventType.__members__, f"EventType.{name} مفقود"
    assert EventType.SEASON_CREATED.value == "season.created"
    assert EventType.SEASON_CLOSED.value == "season.closed"
    assert EventType.FIELD_DELETED.value == "field.deleted"
    assert EventType.ACTIVITY_RECORDED.value == "activity.recorded"


# ─── ربط نوع النشاط بحدث عمليّة (تغطية أحداث كاملة — الخيار أ) ─────────────


def test_activity_event_type_mapping():
    from api.event_bus import EventType
    from api.main import _activity_event_type

    cases = {
        ("irrigation", "done"): "IRRIGATION_COMPLETED",
        ("irrigation", "planned"): "IRRIGATION_STARTED",
        ("planting", "done"): "PLANTING_COMPLETED",
        ("harvest", "done"): "HARVEST_COMPLETED",
        ("fertilization", "done"): "FERTILIZER_APPLIED",
        ("spraying", "done"): "PESTICIDE_APPLIED",
        ("pruning", "done"): "ACTIVITY_RECORDED",  # لا حدث عمليّة محدَّد
        ("scouting", "planned"): "ACTIVITY_RECORDED",
    }
    for (atype, status), expected in cases.items():
        name = _activity_event_type(atype, status)
        assert name == expected, f"{atype}/{status} → {name} (المتوقّع {expected})"
        # كلّ اسم مُرجَع يجب أن يكون عضو EventType حقيقيّاً (وإلّا يُسقَط الحدث).
        assert name in EventType.__members__
    # FIELD_UPDATED المستعمَل في update_field موجود أيضاً.
    assert "FIELD_UPDATED" in EventType.__members__
