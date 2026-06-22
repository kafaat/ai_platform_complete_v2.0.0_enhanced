"""تفعيل أتمتة صور Sentinel عند إنشاء الحقل (F — تفعيل البيانات الحقيقيّة).

نختبر المساعِدتين النقيّتين دون رفع القاعدة/raster:
  • _bbox_from_geometry: bbox صحيح من Polygon، وNone للمدخل التالف.
  • _kick_imagery_scan: يستدعي imagery_automation.scan_all، وأفضل-جهد (لا يرمي عند فشل raster).
لا شبكة ولا تلفيق — scan_all مُظلَّل.
"""

import asyncio

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.fields import _bbox_from_geometry, _kick_imagery_scan

pytestmark = pytest.mark.unit


def test_bbox_from_geometry_polygon():
    geom = {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.2, 15.0], [44.2, 15.1], [44.0, 15.1], [44.0, 15.0]]],
    }
    assert _bbox_from_geometry(geom) == [44.0, 15.0, 44.2, 15.1]


@pytest.mark.parametrize("bad", [{}, None, {"coordinates": "x"}, {"coordinates": [[]]}, "nope"])
def test_bbox_from_geometry_invalid_returns_none(bad):
    assert _bbox_from_geometry(bad) is None


def test_kick_imagery_scan_calls_scan_all(monkeypatch):
    import api.imagery_automation as ia

    calls: list[int] = []

    async def _ok(lookback_days: int = 14):
        calls.append(lookback_days)
        return {"scanned": 0}

    monkeypatch.setattr(ia.imagery_automation, "scan_all", _ok)
    asyncio.run(_kick_imagery_scan())
    assert calls == [14]


def test_kick_imagery_scan_is_best_effort(monkeypatch):
    import api.imagery_automation as ia

    async def _boom(lookback_days: int = 14):
        raise RuntimeError("raster down")

    monkeypatch.setattr(ia.imagery_automation, "scan_all", _boom)
    # أفضل-جهد: فشل raster لا يرفع استثناءً (لا يكسر مسار إنشاء الحقل).
    asyncio.run(_kick_imagery_scan())
