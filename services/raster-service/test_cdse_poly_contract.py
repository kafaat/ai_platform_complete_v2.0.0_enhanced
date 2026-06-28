"""حارس عقد القصّ الموحَّد لمسارات CDSE (poly + قناع rasterio).

يمنع رجوع التضارب بين الواجهة والخادم (الذي أنتج صوراً «تعمل» لكنها غير دقيقة عند
حدّ الحقل). يُثبّت العقد المتّفق عليه:

  • الواجهة (HubMap + FieldIndicatorMap) تُصدِر ``poly=lng,lat;...`` لبلاطات cdse-tiles
    (لا ``geom=``).
  • الخادم (routers/cdse_tiles.py) يقبل بارامتر ``poly`` ولا يطلب ``geom`` للقصّ.
  • الخادم يطبّق قناع rasterio بكسليّ (``apply_polygon_mask``) على نفس المضلّع.
  • ``tile_render`` يُصدّر ``apply_polygon_mask``.

مسح مصدر ساكن (لا تشغيل/شبكة). يقرأ ملفّات الواجهة عبر مسار المستودع النسبيّ.
"""

import os

import pytest

pytestmark = pytest.mark.unit

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── الخادم ───────────────────────────────────────────────────────────
def test_backend_route_accepts_poly():
    src = _read("services/raster-service/routers/cdse_tiles.py")
    assert "poly: str | None = Query(None)" in src, "مسار cdse-tiles لا يقبل بارامتر poly"


def test_backend_no_geom_param_for_clipping():
    src = _read("services/raster-service/routers/cdse_tiles.py")
    assert "geom: str | None = Query" not in src, "ما زال بارامتر geom مطلوباً للقصّ (تضارب عقد)"


def test_backend_applies_rasterio_mask():
    src = _read("services/raster-service/routers/cdse_tiles.py")
    assert "apply_polygon_mask(" in src, "الخادم لا يطبّق قناع rasterio البكسليّ"


def test_tile_render_exports_polygon_mask():
    src = _read("services/raster-service/tile_render.py")
    assert "def apply_polygon_mask(" in src, "tile_render لا يُصدّر apply_polygon_mask"


def test_backend_parses_poly_lnglat():
    src = _read("services/raster-service/routers/cdse_tiles.py")
    assert "_parse_poly(" in src, "لا مُحلِّل poly في الخادم"


# ── الواجهة ──────────────────────────────────────────────────────────
def test_hubmap_emits_poly_not_geom():
    src = _read("frontend/src/components/maphub/HubMap.tsx")
    assert "&poly=" in src, "HubMap لا يُصدِر poly= لبلاطات cdse-tiles"
    assert "&geom=" not in src, "HubMap ما زال يُصدِر geom= (تضارب عقد)"


def test_field_indicator_map_emits_poly_not_geom():
    src = _read("frontend/src/components/FieldIndicatorMap.tsx")
    assert "&poly=" in src, "FieldIndicatorMap لا يُصدِر poly="
    assert "&geom=" not in src, "FieldIndicatorMap ما زال يُصدِر geom= (تضارب عقد)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
