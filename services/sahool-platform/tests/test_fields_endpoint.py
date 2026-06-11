"""اختبارات نقطة الحقول (GET/POST /api/v1/fields) — الأجزاء الصرفة offline.

تغطّي: حساب المركز من bbox، تطبيع صفّ DB → FieldSummary (بما فيه فكّ
geometry من JSONB نصّاً)، وتحقّق الهندسة الذي يعتمد عليه POST (يرفض المضلّع
المتقاطع ذاتيّاً، يقبل مضلّعاً سليماً داخل اليمن). لا حاجة لقاعدة بيانات.
"""

import json

from api.geospatial_integrity import validate_field_geometry
from api.main import FieldCreateRequest, _centroid_from_bbox, _row_to_field_summary


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
    geom = {"type": "Polygon", "coordinates": [[[45.5, 15.0], [45.6, 15.0], [45.6, 15.1], [45.5, 15.0]]]}
    row = {
        "field_id": "fld_abc",
        "farm_id": None,
        "name": "حقل وادي سبأ",
        "area_ha": 12.5,
        "crop": "wheat",
        "soil_type": "loam",
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


def test_field_create_request_requires_geometry():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FieldCreateRequest(name="حقل", crop="wheat")  # geometry مفقود


def test_validate_geometry_accepts_good_yemen_polygon():
    # مضلّع صغير سليم داخل اليمن (إغلاق صريح)
    geom = {
        "type": "Polygon",
        "coordinates": [[[45.50, 15.00], [45.52, 15.00], [45.52, 15.02], [45.50, 15.02], [45.50, 15.00]]],
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
        "coordinates": [[[45.50, 15.00], [45.52, 15.02], [45.52, 15.00], [45.50, 15.02], [45.50, 15.00]]],
    }
    result = validate_field_geometry(geom)
    assert result.valid is False
