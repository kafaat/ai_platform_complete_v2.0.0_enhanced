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
    SeasonCreateRequest,
    _build_field_update,
    _centroid_from_bbox,
    _row_to_field_summary,
    _row_to_season,
    _significant_overlaps,
)


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


# ─── عقد أحداث domain (مسارات الكتابة تُصدر هذه الأنواع — يجب أن توجد) ─────


def test_domain_event_types_exist():
    # _emit_domain_event يبحث EventType[name]؛ خطأ مطبعيّ يُسقِط الحدث بصمت.
    from api.event_bus import EventType

    for name in ("FIELD_CREATED", "SEASON_CREATED", "ACTIVITY_RECORDED"):
        assert name in EventType.__members__, f"EventType.{name} مفقود"
    assert EventType.SEASON_CREATED.value == "season.created"
    assert EventType.ACTIVITY_RECORDED.value == "activity.recorded"
