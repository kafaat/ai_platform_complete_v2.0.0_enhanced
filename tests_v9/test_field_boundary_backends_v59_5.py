"""تحقّق V59.5 — طبقة backends لحدود الحقل (سقالة FTW، سقوط آمن).

يختبر النصف الحتميّ القابل للاختبار داخل الصندوق:
- ``pixel_to_lonlat`` (أفاين البلاطة → EPSG:4326).
- ``connected_components`` + ``mask_to_polygons`` (قناع → مضلّع لكلّ حقل).
- بوّابة ``ftw_available`` (غير متاح بلا أوزان/torch ⇒ False).
- **السقوط الآمن:** اختيار backend=ftw بلا نموذج ⇒ ``propose_boundaries`` يُرجع
  المقترح الحتميّ نفسه (العقد ثابت، لا تحطّم).
- ثبات العقد: المسار الافتراضيّ (بلا راية) لم يتغيّر.

منطق صرف (numpy/torch غير مطلوبَين) — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import field_boundary_ai as FBA  # noqa: E402
from services.ai_agronomist import field_boundary_backends as B  # noqa: E402


# ── pixel → lon/lat ─────────────────────────────────────────────────────────
def test_pixel_to_lonlat_maps_corners_to_bbox():
    bbox = [10.0, 20.0, 14.0, 24.0]
    assert B.pixel_to_lonlat(0, 0, bbox, 4, 4) == [10.0, 24.0]  # top-left = lon_min, lat_max
    assert B.pixel_to_lonlat(4, 0, bbox, 4, 4) == [14.0, 24.0]  # top-right
    assert B.pixel_to_lonlat(4, 4, bbox, 4, 4) == [14.0, 20.0]  # bottom-right
    assert B.pixel_to_lonlat(0, 4, bbox, 4, 4) == [10.0, 20.0]  # bottom-left = lon_min, lat_min


# ── connected components ─────────────────────────────────────────────────────
def test_connected_components_separates_fields():
    mask = [
        [1, 1, 0, 1],
        [1, 1, 0, 1],
        [0, 0, 0, 0],
        [1, 0, 0, 0],
    ]
    comps = B.connected_components(mask)
    sizes = sorted(len(c) for c in comps)
    assert sizes == [1, 2, 4]  # three separate fields (4-connectivity)


# ── mask → polygons ──────────────────────────────────────────────────────────
def test_full_mask_polygon_is_whole_bbox():
    bbox = [0.0, 0.0, 4.0, 4.0]
    mask = [[1] * 4 for _ in range(4)]
    polys = B.mask_to_polygons(mask, bbox, min_area_px=1)
    assert len(polys) == 1
    ring = polys[0]["coordinates"][0]
    assert ring[0] == ring[-1]  # closed
    assert ring[:4] == [[0.0, 4.0], [4.0, 4.0], [4.0, 0.0], [0.0, 0.0]]
    assert polys[0]["pixel_area"] == 16


def test_two_fields_yield_two_polygons_within_bbox():
    bbox = [44.0, 15.0, 44.4, 15.4]
    mask = [
        [1, 1, 0, 0],
        [1, 1, 0, 0],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
    ]
    polys = B.mask_to_polygons(mask, bbox, min_area_px=1)
    assert len(polys) == 2
    for p in polys:
        for lon, lat in p["coordinates"][0]:
            assert 44.0 <= lon <= 44.4 and 15.0 <= lat <= 15.4


def test_min_area_filter_drops_specks_and_empty_mask():
    bbox = [0.0, 0.0, 4.0, 4.0]
    mask = [[0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert B.mask_to_polygons(mask, bbox, min_area_px=4) == []  # 1-px speck dropped
    assert len(B.mask_to_polygons(mask, bbox, min_area_px=1)) == 1  # kept when threshold low
    assert B.mask_to_polygons([], bbox, min_area_px=1) == []  # empty


# ── FTW gate + backend registry ─────────────────────────────────────────────
def test_ftw_unavailable_without_weights(monkeypatch):
    monkeypatch.delenv("SAHOOL_FTW_WEIGHTS", raising=False)
    assert B.ftw_available() is False
    monkeypatch.setenv("SAHOOL_FTW_WEIGHTS", "/nonexistent/ftw.pt")
    assert B.ftw_available() is False  # file missing ⇒ still unavailable


def test_backend_selection_defaults_and_clamps(monkeypatch):
    monkeypatch.delenv("SAHOOL_FIELD_BOUNDARY_BACKEND", raising=False)
    assert B.select_backend_name() == "deterministic"
    monkeypatch.setenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "ftw")
    assert B.select_backend_name() == "ftw"
    monkeypatch.setenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "magic-model")
    assert B.select_backend_name() == "deterministic"  # unknown ⇒ safe default


def test_ftw_propose_returns_none_when_unavailable(monkeypatch):
    monkeypatch.delenv("SAHOOL_FTW_WEIGHTS", raising=False)
    out = B.ftw_propose({"bbox": [44.1, 15.1, 44.2, 15.2]}, field_id="f")
    assert out is None  # signals fallback


# ── fail-safe integration through the tool contract ─────────────────────────
def test_propose_boundaries_falls_back_to_deterministic_when_ftw_unavailable(monkeypatch):
    monkeypatch.setenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "ftw")
    monkeypatch.delenv("SAHOOL_FTW_WEIGHTS", raising=False)
    out = FBA.propose_boundaries(
        {"bbox": [44.18, 16.16, 44.19, 16.17], "source": "truecolor"},
        field_id="field-1",
        imagery_context={"total_dates": 5},
    )
    assert out["requires_user_confirmation"] is True
    assert out["proposed_boundaries"][0]["geometry"]["type"] == "Polygon"
    assert out["proposed_boundaries"][0]["confidence"] >= 0.7  # deterministic path intact
    assert "backend" not in out or out.get("backend") != "ftw"  # did NOT claim FTW


def test_default_backend_output_unchanged(monkeypatch):
    monkeypatch.delenv("SAHOOL_FIELD_BOUNDARY_BACKEND", raising=False)
    out = FBA.propose_boundaries({"bbox": [44.18, 16.16, 44.19, 16.17]}, field_id="field-1")
    assert out["persistence"] == "proposal_only_until_user_confirms"
    assert out["proposed_boundaries"][0]["area_ha"] == FBA.area_ha_for_bbox(
        [44.18, 16.16, 44.19, 16.17]
    )
