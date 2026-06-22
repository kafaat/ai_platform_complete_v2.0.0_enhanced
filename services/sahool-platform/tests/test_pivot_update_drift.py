"""اختبارات وحدة لمنع انحراف مضلّع الحقل المحوريّ عند التعديل (item B).

تختبر منطق القرار النقيّ في ``api.pivot_geometry.resolve_pivot_update_geometry``
(كشف المحوريّة + إعادة الاشتقاق مقابل الرفض) دون قاعدة بيانات حيّة — مصدر الحقيقة
للحقل المحوريّ هو المركز/نصف القطر/الزوايا لا المضلّع المُحرَّر مباشرةً.
"""

import pytest
from api.gis_geometry_guard import guard_field_geometry
from api.pivot_geometry import (
    PivotPolygonDriftError,
    is_pivot_irrigation,
    resolve_pivot_update_geometry,
)

pytestmark = pytest.mark.unit


_RAW_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
}
_PIVOT_PARAMS = {"pivot": {"center": {"lon": 44.0, "lat": 15.0}, "radius_m": 500, "vertices": 48}}


def test_is_pivot_irrigation_normalizes_case_and_none():
    assert is_pivot_irrigation("PIVOT")
    assert is_pivot_irrigation(None, "pivot")
    assert is_pivot_irrigation("drip", "Pivot")
    assert not is_pivot_irrigation(None, "drip")
    assert not is_pivot_irrigation()


def test_non_pivot_field_returns_none_no_intervention():
    # حقل غير محوريّ (المخزَّن drip، الطلب بلا نوع ريّ) ⇒ لا تدخُّل ⇒ المسار العاديّ.
    result = resolve_pivot_update_geometry(
        {"geometry": _RAW_POLYGON},
        field_irrigation_type="drip",
        request_irrigation_type=None,
    )
    assert result is None


def test_pivot_field_with_params_rederives_canonical_polygon():
    # حقل محوريّ مخزَّن + بارامترات في الطلب ⇒ يُعاد اشتقاق مضلّع canonical صالح.
    payload = {"geometry": _RAW_POLYGON, **_PIVOT_PARAMS}
    derived = resolve_pivot_update_geometry(
        payload,
        field_irrigation_type="pivot",
        request_irrigation_type=None,
    )
    assert derived is not None
    assert derived["type"] == "Polygon"
    # المضلّع المُشتقّ ليس المضلّع الخام المُرسَل (مصدر الحقيقة البارامترات).
    assert derived["coordinates"] != _RAW_POLYGON["coordinates"]
    # ناتج canonical يجتاز حارس الهندسة (مساحة دائرة نصف قطرها 500م ~ 78 هكتار).
    guarded = guard_field_geometry(derived, repair=False)
    assert guarded.area_ha > 70


def test_pivot_field_raw_polygon_only_is_rejected():
    # حقل محوريّ مخزَّن + مضلّع خام فقط (بلا بارامترات) ⇒ رفض (يُترجَم 422 في المسار).
    with pytest.raises(PivotPolygonDriftError) as exc:
        resolve_pivot_update_geometry(
            {"geometry": _RAW_POLYGON},
            field_irrigation_type="pivot",
            request_irrigation_type=None,
        )
    assert "المضلّع" in exc.value.message_ar


def test_request_irrigation_type_can_mark_field_pivot():
    # الـPATCH يحوّل الحقل إلى محوريّ (request_irrigation_type) دون تخزين سابق ⇒
    # مضلّع خام فقط ⇒ رفض كذلك (لا تخزين صامت لمضلّع منحرف).
    with pytest.raises(PivotPolygonDriftError):
        resolve_pivot_update_geometry(
            {"geometry": _RAW_POLYGON},
            field_irrigation_type=None,
            request_irrigation_type="pivot",
        )


def test_request_irrigation_type_pivot_with_params_rederives():
    payload = {"geometry": _RAW_POLYGON, **_PIVOT_PARAMS}
    derived = resolve_pivot_update_geometry(
        payload,
        field_irrigation_type=None,
        request_irrigation_type="pivot",
    )
    assert derived is not None
    assert derived["type"] == "Polygon"
