"""تحقّق جغرافيّ — إسقاط Web Mercator (EPSG:3857) وتطبيع CRS (Production Hardening — المرحلة B).

يتحقّق أنّ ``shared/gis/crs_service.py`` يطابق صيغة الإسقاط القياسيّة (المستخدمة في
كلّ نظام تبليط slippy-map) وأنّ حارس التطبيع لا يُسرّب هندسةً غير 4326 — «أيّ انحراف
بسيط في EPSG/reprojection يُعطي قرارات زراعيّة خاطئة بالكامل».

المراسي:
- الإسقاط الأماميّ عند خطّ طول 180° = π·R = 20037508.342789 م (نصف محيط Web Mercator).
- خطّ الاستواء (0,0) ⇒ (0,0)؛ العرض يُقصّ إلى ±85.05112878° (حدّ Web Mercator).
- ``normalize_to_wgs84`` يجرّد أيّ ``crs`` قديم ويرفض CRS مُعلَنة غير 4326.
- ``transform_to_map_projection`` يضيف ``crs`` = 3857 ويرفض هدفاً غير مدعوم.

منطق فيزيائيّ صرف (بلا خدمات) — يُستورَد ``shared`` من جذر المستودع.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.gis.crs_service import (  # noqa: E402
    _is_wgs84,
    _lonlat_to_web_mercator,
    normalize_to_wgs84,
    transform_to_map_projection,
)

# نصف محيط Web Mercator: π·R حيث R = 6378137 م (نصف قطر EPSG:3857 الكرويّ).
_HALF_CIRCUMFERENCE = math.pi * 6378137.0  # ≈ 20037508.342789244


# ── الإسقاط الأماميّ: lon/lat° → x/y م (FAO/slippy-map القياسيّ) ─────────────
def test_web_mercator_origin_is_zero():
    x, y = _lonlat_to_web_mercator(0.0, 0.0)
    assert abs(x) < 1e-6 and abs(y) < 1e-6  # نقطة الأصل (0,0)


def test_web_mercator_antimeridian_is_half_circumference():
    # خطّ طول 180° ⇒ x = π·R (الحدّ الشرقيّ للمربّع)، −180° ⇒ −π·R.
    assert abs(_lonlat_to_web_mercator(180.0, 0.0)[0] - _HALF_CIRCUMFERENCE) < 1e-3
    assert abs(_lonlat_to_web_mercator(-180.0, 0.0)[0] + _HALF_CIRCUMFERENCE) < 1e-3


def test_web_mercator_x_is_linear_in_longitude():
    # x يتناسب خطّيّاً مع خطّ الطول (لا اعتماد على العرض).
    x90 = _lonlat_to_web_mercator(90.0, 0.0)[0]
    x45 = _lonlat_to_web_mercator(45.0, 0.0)[0]
    assert abs(x90 - 2 * x45) < 1e-6
    assert abs(x45 - _HALF_CIRCUMFERENCE / 4.0) < 1e-3


def test_web_mercator_latitude_sign_and_monotonic():
    # الشمال موجب، الجنوب سالب، ومتزايد رتيباً مع العرض.
    assert _lonlat_to_web_mercator(0.0, 45.0)[1] > 0
    assert _lonlat_to_web_mercator(0.0, -45.0)[1] < 0
    assert _lonlat_to_web_mercator(0.0, 60.0)[1] > _lonlat_to_web_mercator(0.0, 30.0)[1]


def test_web_mercator_clamps_latitude_to_cutoff():
    # القطبان خارج نطاق Mercator ⇒ يُقصّان إلى ±85.05112878° (لا لانهاية).
    assert _lonlat_to_web_mercator(0.0, 90.0) == _lonlat_to_web_mercator(0.0, 85.05112878)
    assert _lonlat_to_web_mercator(0.0, -90.0) == _lonlat_to_web_mercator(0.0, -85.05112878)
    # عند حدّ القصّ y ≈ نصف المحيط (المربّع شبه المتماثل).
    assert abs(_lonlat_to_web_mercator(0.0, 90.0)[1] - _HALF_CIRCUMFERENCE) < 1.0


# ── حارس CRS: قبول 4326 فقط ─────────────────────────────────────────────────
def test_is_wgs84_accepts_canonical_forms():
    for form in ("EPSG:4326", "epsg:4326", "WGS84", "CRS:84", None, ""):
        assert _is_wgs84(form) is True


def test_is_wgs84_rejects_projected_crs():
    for form in ("EPSG:3857", "EPSG:32638", "EPSG:32637", "MAGIC"):
        assert _is_wgs84(form) is False  # UTM/Web-Mercator/مجهول ليست 4326


# ── تطبيع GeoJSON إلى 4326 ──────────────────────────────────────────────────
def test_normalize_strips_legacy_crs_member():
    src = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
    }
    out = normalize_to_wgs84(src)
    assert "crs" not in out  # يُجرَّد على الإدخال (قانون التخزين 4326 فقط)
    assert "crs" in src  # لا يُطفَّر المُدخَل (deep copy)


def test_normalize_rejects_declared_non_wgs84():
    with pytest.raises(ValueError):
        normalize_to_wgs84(
            {
                "type": "Point",
                "coordinates": [0, 0],
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            }
        )


def test_normalize_requires_dict():
    with pytest.raises(ValueError):
        normalize_to_wgs84([1, 2, 3])  # ليس كائن GeoJSON


# ── الإسقاط إلى مسقط الخريطة (عقد الإخراج) ──────────────────────────────────
def test_transform_projects_and_tags_target_crs():
    out = transform_to_map_projection({"type": "Point", "coordinates": [180.0, 0.0]})
    assert out["crs"]["properties"]["name"] == "EPSG:3857"
    x, _y = out["coordinates"]
    assert abs(x - _HALF_CIRCUMFERENCE) < 1e-3  # نفس مرساة الإسقاط الأماميّ


def test_transform_rejects_unsupported_target():
    with pytest.raises(ValueError):
        transform_to_map_projection({"type": "Point", "coordinates": [0, 0]}, target="EPSG:4326")


def test_transform_rejects_declared_non_wgs84_input():
    # يمرّ عبر normalize_to_wgs84 أولاً ⇒ CRS مُعلَنة غير 4326 تُرفَض قبل الإسقاط.
    with pytest.raises(ValueError):
        transform_to_map_projection(
            {
                "type": "Point",
                "coordinates": [0, 0],
                "crs": {"type": "name", "properties": {"name": "EPSG:32638"}},
            }
        )
