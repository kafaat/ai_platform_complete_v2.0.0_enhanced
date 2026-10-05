"""شواهدُ عيوب مسار Element84→VRT — اختباراتُ قبولٍ تنتظر الإصلاح (``xfail(strict=True)``).

منقولةٌ من ``probe.py`` في المراجعة المستقلّة (``d6488d89``) وأُعيد تشغيلها على شجرة المستودع:
``stac_vrt.build_band_vrt`` و``raster_pixel_processing.process_pixels`` و``band_math``/
``soil_indices`` واستراتيجية قناع الغيوم **حقيقيّة**، على راسترات اصطناعيّة صغيرة معلومة
الحقيقة. الحفظُ والتحقّقُ من عقد المنتج وQA التضاريس وكتابةُ COG بدائلُ اختباريّة: الشاهد
يُثبت مسار الأرقام لا قبول API/DB.

كلُّ اختبارٍ هنا يكتب **السلوكَ الصحيح** ويُعلَّم ``xfail(strict=True)`` بمعرّف فجوته: يفشل
اليوم لأنّ العيب قائم. حين يُصلَح العيب يمرّ الاختبار، فيُحمِّر ``strict`` الجناحَ حتّى تُنزَع
العلامة — فيصير الشاهدُ اختبارَ قبول الإصلاح تلقائيّاً، ولا يُغلَق عيبٌ بلا دليل.

الاحتواء (``radiometry_containment``) يمنع الإنتاج من بلوغ هذا المسار؛ هذه الشواهد تستدعي
الدوالّ مباشرةً عمداً — هي التي ستُثبت أنّ رفع الاحتواء صار آمناً.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

pytestmark = pytest.mark.unit

SCALE = "ELEMENT84-VRT-REFLECTANCE-SCALE-NOT-APPLIED-01"
GRID = "ELEMENT84-VRT-BAND-GRID-MISALIGNED-01"
NODATA = "ELEMENT84-VRT-NODATA-NOT-PROPAGATED-01"
CLAIM = "ELEMENT84-VRT-NORMALIZED-CLAIM-UNSUPPORTED-01"
CACHE = "RASTER-SHARED-CACHE-KEY-OMITS-TRANSFORM-01"

INDICES = ["evi", "msavi", "savi", "tgi", "bi", "bi2", "satvi"]
VALUES = {"red": 1000, "nir": 3000, "green": 1500, "blue": 500, "swir1": 2000, "swir2": 1800}


class _HTTPError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(f"{status}: {detail}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    import band_math
    import cog_writer
    import raster_pixel_processing as pp
    import raster_validated_product as vp
    import raw_data_processing as raw
    import stac_vrt

    monkeypatch.setattr(pp, "_topographic_qa_for_indicator", lambda *a, **k: {}, raising=False)
    monkeypatch.setattr(raw, "compute_quality_score", lambda **k: {"quality_score": 1.0})
    monkeypatch.setattr(raw, "build_quality_flags", lambda **k: k)
    monkeypatch.setattr(
        vp, "build_validated_raster_product", lambda **k: NS(model_dump=lambda **_: k)
    )
    monkeypatch.setattr(vp, "assert_indicator_accepts_validated_product", lambda _p: None)
    monkeypatch.setattr(cog_writer, "write_cog", lambda *a, **k: {"written": False})
    ctx = NS(
        band_math=band_math,
        HTTPException=_HTTPError,
        _INDICATOR_FORMULAS={i: i for i in ["ndvi", *INDICES]},
        _quality_from_cloud_pct=lambda *a, **k: {
            "confidence": 0,
            "quality": "probe",
            "reason": "probe",
        },
        RASTER_NODATA=-9999,
        UPLOAD_DIR=str(tmp_path),
        logger=logging.getLogger("witness"),
    )
    return NS(pp=pp, stac_vrt=stac_vrt, ctx=ctx, dir=tmp_path)


def _tif(env, name, array, pixel=10, nodata=0, scale=None):
    path = env.dir / f"{name}.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=array.shape[1],
        height=array.shape[0],
        count=1,
        dtype=array.dtype,
        crs="EPSG:32638",
        transform=from_origin(500000, 1800000, pixel, pixel),
        nodata=nodata,
    ) as dst:
        dst.write(array, 1)
        if scale is not None:
            dst.scales = (scale,)
    return str(path)


def _bands(**present):
    names = ["red", "nir", "green", "blue", "swir1", "swir2", "rededge", "scl", "clm", "clp"]
    return NS(**{n: present.get(n) for n in names})


def _req(index, *, scale=None, mask=False, bands=None):
    return NS(
        indicator=NS(value=index),
        reflectance_scale=scale,
        reflectance_offset=None,
        bands=bands or _bands(red=1, nir=2, green=3, blue=4, swir1=5, swir2=6, scl=7),
        clip_polygon_geojson=None,
        apply_cloud_mask=mask,
        source_format="sentinel2_l2a",
        raster_url="witness",
        field_id="witness",
        raw_qa_required=False,
    )


def _run(env, src, req, cache=None):
    try:
        stats, *_ = env.pp.process_pixels(
            env.ctx, req, "witness", shared_src=src, shared_cache=cache
        )
    except _HTTPError as exc:
        return {"status": exc.status, "detail": exc.detail}
    product = stats.get("validated_raster_product") or {}
    return {
        "mean": stats["mean"],
        "valid_pixels": stats["valid_pixels"],
        "reflectance_normalized": product.get("reflectance_normalized"),
    }


@pytest.fixture
def uniform_vrt(env):
    hrefs = {
        k: _tif(env, k, np.full((4, 4), v, dtype="uint16"), scale=0.0001) for k, v in VALUES.items()
    }
    hrefs["scl"] = _tif(env, "scl", np.full((4, 4), 4, dtype="uint16"))
    path, _mapping = env.stac_vrt.build_band_vrt(hrefs, str(env.dir))
    return path


@pytest.mark.xfail(strict=True, reason=SCALE)
@pytest.mark.parametrize("index", INDICES)
def test_the_vrt_path_computes_reflectance_indices(env, uniform_vrt, index):
    """القيمةُ عبر الـVRT = القيمة بمقياسٍ صريح (0.0001). اليوم: EVI 0.952 بدل 0.328 …"""
    with rasterio.open(uniform_vrt) as src:
        default = _run(env, src, _req(index))
        explicit = _run(env, src, _req(index, scale=0.0001))
    assert default["mean"] == pytest.approx(explicit["mean"], abs=1e-6)


def test_a_ratio_index_is_insensitive_to_a_shared_scale(env, uniform_vrt):
    """الضابط: NDVI لا يتأثّر بمقياسٍ مشترك — فاحمرارُ الشواهد أعلاه ليس عطباً في الأداة."""
    with rasterio.open(uniform_vrt) as src:
        default = _run(env, src, _req("ndvi"))
        explicit = _run(env, src, _req("ndvi", scale=0.0001))
    assert default["mean"] == pytest.approx(0.5) == pytest.approx(explicit["mean"])


@pytest.mark.xfail(strict=True, reason=SCALE)
def test_the_quality_mask_accepts_a_clear_scene(env, uniform_vrt):
    """قناع التشبّع (>1.20) يرفض DN الخام: اليوم 422 raw_raster_no_valid_pixels لا 16 بكسلاً."""
    with rasterio.open(uniform_vrt) as src:
        result = _run(env, src, _req("evi", mask=True))
    assert result.get("valid_pixels") == 16


@pytest.mark.xfail(strict=True, reason=CLAIM)
def test_normalized_is_not_claimed_for_unscaled_digital_numbers(env, uniform_vrt):
    """``reflectance_normalized=True`` يُمرَّر ثابتاً — حتّى والقيمُ DN خام لم تُطبَّع."""
    with rasterio.open(uniform_vrt) as src:
        result = _run(env, src, _req("evi"))
    assert result["reflectance_normalized"] is not True


@pytest.mark.xfail(strict=True, reason=CACHE)
def test_the_shared_cache_does_not_reuse_a_different_transform(env, uniform_vrt):
    """المفتاح ``(reflectance, band)`` بلا التحويل: طلبٌ بمقياسٍ صريح يرث قراءةَ DN السابقة.
    شرطيّ — لم يثبت أنّ مستدعياً إنتاجيّاً يغيّر التحويل داخل الدفعة نفسها."""
    cache: dict = {}
    with rasterio.open(uniform_vrt) as src:
        _run(env, src, _req("evi"), cache=cache)
        second = _run(env, src, _req("evi", scale=0.0001), cache=cache)
    assert second["mean"] == pytest.approx(0.32786885, abs=1e-6)


@pytest.mark.xfail(strict=True, reason=NODATA)
def test_vrt_preserves_source_nodata(env):
    missing = np.array([[1000, 0], [0, 0]], dtype="uint16")
    hrefs = {"red": _tif(env, "nd_red", missing), "nir": _tif(env, "nd_nir", missing * 3)}
    path, _mapping = env.stac_vrt.build_band_vrt(hrefs, str(env.dir))
    with rasterio.open(path) as src:
        result = _run(env, src, _req("ndvi", bands=_bands(red=1, nir=2)))
    assert result["valid_pixels"] == 1 and result["mean"] == pytest.approx(0.5)


@pytest.mark.xfail(strict=True, reason=GRID)
def test_twenty_metre_bands_are_resampled_onto_the_ten_metre_grid(env):
    hrefs = {
        "red": _tif(env, "g_red", np.full((4, 4), 1000, dtype="uint16")),
        "scl": _tif(env, "g_scl", np.array([[4, 9], [3, 11]], dtype="uint8"), pixel=20),
    }
    path, mapping = env.stac_vrt.build_band_vrt(hrefs, str(env.dir))
    with rasterio.open(path) as src:
        observed = src.read(mapping["scl"])
    expected = np.repeat(np.repeat(np.array([[4, 9], [3, 11]]), 2, axis=0), 2, axis=1)
    assert np.array_equal(observed, expected)
