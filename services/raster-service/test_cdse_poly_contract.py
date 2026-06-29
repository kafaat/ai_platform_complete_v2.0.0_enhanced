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
# توحيد main↔cert: بعد الدمج صار عقد cdse-tiles مركزيّاً في باني api.ts
# ``fieldCdseTileUrl`` (مصدر الحقيقة الوحيد لرابط بلاطة CDSE: يضبط poly من هندسة الحقل
# ولا يُصدِر geom). أيّ مكوّن يصيّر بلاطات CDSE يستدعيه. HubMap (نسخة cert) يصيّر بلاطات
# COG المحلّيّة عبر ``/tiles/`` بتصميمه؛ بلاطات CDSE الحيّة (poly) عبر هذا الباني.
def _cdse_builder_block() -> str:
    api = _read("frontend/src/services/api.ts")
    start = api.index("export const fieldCdseTileUrl")
    rest = api[start + len("export const fieldCdseTileUrl") :]
    end = rest.index("\nexport const ")
    return api[start : start + len("export const fieldCdseTileUrl") + end]


def test_cdse_tile_builder_emits_poly_not_geom():
    """مصدر الحقيقة لرابط بلاطة CDSE (fieldCdseTileUrl) يضبط poly ولا يُمرّر geom كاستعلام."""
    block = _cdse_builder_block()
    assert "params.set('poly'" in block, "fieldCdseTileUrl لا يضبط poly"
    assert "/cdse-tiles/" in block, "fieldCdseTileUrl لا يبني مسار cdse-tiles"
    assert "set('geom'" not in block and "&geom=" not in block, (
        "fieldCdseTileUrl ما زال يُصدِر geom (تضارب عقد)"
    )


def test_field_indicator_map_uses_cdse_builder():
    """FieldIndicatorMap يصيّر بلاطات CDSE عبر باني poly المركزيّ (لا geom)."""
    comp = _read("frontend/src/components/FieldIndicatorMap.tsx")
    assert "fieldCdseTileUrl(" in comp, (
        "FieldIndicatorMap لا يستخدم باني cdse-tiles (fieldCdseTileUrl)"
    )
    assert "&geom=" not in comp, "FieldIndicatorMap يُصدِر geom= (تضارب عقد)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
