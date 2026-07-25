"""كادينس المزامنة التلقائيّة: 24 ساعة من وقت التقاط الصورة السابقة.

يؤكّد شيئين نقيّين (بلا شبكة/قاعدة):
  1) ``_parse_capture_time`` يحلّل ISO8601 والتاريخ الخام ويعيد ``None`` بصدق على الفراغ/الخطأ.
  2) ``scan_all`` يتخطّى حقلاً مرّ على وقت التقاط صورته السابقة أقلّ من 24 ساعة — بلا ضرب
     raster-service — بينما يفحص حقلاً وقت التقاطه أقدم من النافذة.
والمُجدوِل يُسجّل ``scan_new_imagery`` كلّ 86400ث (24 ساعة).
"""

from datetime import UTC, datetime, timedelta

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد وحدات api
import pytest
from api.imagery_automation import ImageryAutomation, _parse_capture_time

pytestmark = pytest.mark.unit


def test_parse_capture_time_iso_date_and_invalid():
    iso = _parse_capture_time("2026-07-25T10:30:00Z")
    assert iso is not None and iso.tzinfo is not None and iso.year == 2026
    day = _parse_capture_time("2026-07-25")
    assert day is not None and day.tzinfo is not None  # التاريخ الخام يُثبَّت UTC
    assert _parse_capture_time(None) is None
    assert _parse_capture_time("") is None
    assert _parse_capture_time("not-a-date") is None


def test_scan_all_skips_field_within_24h_of_last_capture(monkeypatch):
    ia = ImageryAutomation()
    ia.register_field("recent", [44.30, 16.78, 44.36, 16.81])
    # وقت التقاط قبل 6 ساعات فقط ⇒ داخل نافذة الـ24 ساعة ⇒ يُتخطّى.
    ia._fields["recent"].last_image_date = (datetime.now(UTC) - timedelta(hours=6)).isoformat()

    async def _boom(*a, **k):  # يجب ألّا يُستدعى لحقل مُتخطّى
        raise AssertionError("scan_all ضرب raster-service لحقل داخل نافذة 24 ساعة")

    monkeypatch.setattr("api.imagery_automation.search_imagery_scenes", _boom)

    import asyncio

    res = asyncio.run(ia.scan_all())
    assert res["skipped"] == 1
    assert res["scanned"] == 0
    assert res["new_images"] == 0


def test_scan_all_scans_field_older_than_window(monkeypatch):
    ia = ImageryAutomation()
    ia.register_field("old", [44.30, 16.78, 44.36, 16.81])
    ia._fields["old"].last_image_date = (datetime.now(UTC) - timedelta(days=3)).isoformat()

    calls = {"n": 0}

    async def _search(*a, **k):
        calls["n"] += 1
        return {"items": []}  # لا صور جديدة — يكفي لإثبات أنّ الفحص جرى

    monkeypatch.setattr("api.imagery_automation.search_imagery_scenes", _search)

    import asyncio

    res = asyncio.run(ia.scan_all())
    assert res["skipped"] == 0
    assert res["scanned"] == 1
    assert calls["n"] == 1  # الحقل الأقدم من النافذة فُحص فعلاً
