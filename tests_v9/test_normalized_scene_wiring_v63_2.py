"""تحقّق V63.2 — وصل ``NormalizedScene`` في استجابة ``/imagery/timeseries`` (غير كاسر).

- الاستجابة تحمل ``normalized_scenes`` (عقد موحَّد: provider/acquisition_date/cog_ready)
  **بجانب** ``scenes`` الخام — لا يُسقِط المفتاح القديم (حارس انحدار للمستهلكين الحاليّين).
- تحويل ``normalize_search_result`` يطابق عدد المشاهد ويحمل تاريخ الالتقاط من STAC.

منطق صرف + حارس ساكن — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402


def _fake_search_result() -> dict:
    """يحاكي مخرَج ``stac_search`` (element84) كما يستهلكه مُعالِج timeseries."""
    return {
        "count": 2,
        "source": "element84-earth-search",
        "items": [
            {
                "item_id": "S2_A_20260701",
                "datetime": "2026-07-01T08:00:00Z",
                "cloud_cover_pct": 4.0,
                "bbox": [44.0, 16.0, 44.2, 16.2],
                "bands_urls": {"red": "http://x/r.tif", "nir": "http://x/n.tif"},
                "provider": "element84",
            },
            {
                "item_id": "S2_B_20260628",
                "datetime": "2026-06-28T08:00:00Z",
                "cloud_cover_pct": 22.0,
                "bbox": [44.0, 16.0, 44.2, 16.2],
                "bands_urls": {"red": "http://x/r2.tif"},
                "provider": "element84",
            },
        ],
    }


def test_timeseries_normalization_matches_raw_scene_count():
    search = _fake_search_result()
    normalized = [s.to_dict() for s in M.normalize_search_result(search)]
    assert len(normalized) == len(search["items"])  # لا فقدان/تكرار
    assert [n["scene_id"] for n in normalized] == ["S2_A_20260701", "S2_B_20260628"]


def test_normalized_scene_carries_provider_and_acquisition_date():
    search = _fake_search_result()
    n0 = [s.to_dict() for s in M.normalize_search_result(search)][0]
    assert n0["provider"] == "element84"
    assert n0["acquisition_date"] == "2026-07-01T08:00:00Z"  # تاريخ الالتقاط من STAC
    assert n0["cog_ready"] is True
    assert n0["cloud_cover"] == pytest.approx(4.0)


# ── حارس ساكن: الوصل موجود ولا يُسقِط المفتاح الخام ──────────────────────────────
def test_timeseries_route_wires_normalized_without_dropping_raw():
    src = (_RASTER / "routers" / "timeseries_routes.py").read_text(encoding="utf-8")
    assert "from raster_scene_model import normalize_search_result" in src, "يجب استيراد المطبِّع"
    assert '"normalized_scenes": normalized' in src, "الاستجابة يجب أن تحمل العقد الموحَّد"
    assert '"scenes": scenes' in src, "المفتاح الخام يجب أن يبقى (غير كاسر)"


# ── إثراء السِجِلّ: تغطية اليمن (وصفيّ) دون تفعيل مزوّد غير موصول ──────────────────
def test_yemen_capable_providers_are_registered_but_inactive():
    for p in ("wapor", "worldcereal", "nasa_hls"):
        meta = M.PROVIDER_REGISTRY[p]
        assert meta["coverage_yemen"] is True, f"{p} يغطّي اليمن (وصفيّ)"
        assert meta["active"] is False, f"{p} غير موصول ⇒ يجب أن يبقى غير نشط"
        assert meta["recommended_use"] and meta["resolution"], f"{p} يحمل استعمالاً/دقّة"


def test_planned_providers_lists_unwired_and_excludes_active():
    planned = M.planned_providers()
    for p in ("wapor", "worldcereal", "nasa_hls", "planetary_computer"):
        assert p in planned
    # لا تداخل بين النشط والمخطَّط.
    assert set(M.active_providers()).isdisjoint(planned)
    assert "element84" in M.active_providers() and "element84" not in planned


def test_wapor_worldcereal_never_leak_into_active():
    # صدق حاسم: لا تُفعَّل طبقات المياه/المحاصيل قبل مُحوِّل واختبار عقد.
    active = M.active_providers()
    assert "wapor" not in active and "worldcereal" not in active
