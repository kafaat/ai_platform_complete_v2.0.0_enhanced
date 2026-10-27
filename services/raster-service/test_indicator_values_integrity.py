"""قيم المؤشّر العلميّة مقابل بكسلات العرض (T8/T9/T10 — thumbnail-indicators-values).

T8: إحصاءات الحقل (stats) تُحسب من بكسلات المصدر الصالحة، لا متوسّطاً غير موزون لخلايا
    شبكة العرض المُصغَّرة؛ فلا تتغيّر بتغيّر ``grid``. إحصاء خلايا العرض يُعلَن منفصلاً.
T9: اتّجاه الشدّة (عالٍ = أسوأ؟) مصدره قاموس المُصيِّر نفسه؛ والمؤشّر بلا عتبات مُعلَنة
    لا يرث عتبات NDVI (MSI=1.5 كان «low» بينما يُلوَّن أحمر).
T10: قراءة النقطة تحترم القناع الداخليّ للبيانات (internal dataset mask)، لا nodata فقط.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import indicator_grid as ig  # noqa: E402
import layer_lookup  # noqa: E402
import tile_render  # noqa: E402

_IDENTITY_STORE = SimpleNamespace(to_gdal_path=lambda uri: uri)
_TRANSFORM = from_origin(44.0, 16.0, 0.001, 0.001)


def _write_scalar(path: Path, arr: np.ndarray, *, nodata=None, mask=None) -> str:
    profile = dict(
        driver="GTiff",
        width=arr.shape[1],
        height=arr.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=_TRANSFORM,
    )
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(str(path), "w", **profile) as ds:
        ds.write(arr.astype("float32"), 1)
        if mask is not None:
            ds.write_mask(mask)
    return str(path)


def _thirteen_valid_pixels() -> np.ndarray:
    # 4×4: ثلاث بكسلات nodata في الربع الأيسر العلويّ، بكسل واحد = 1، اثنا عشر = 0.
    a = np.zeros((4, 4), dtype="float32")
    a[:2, :2] = np.nan
    a[0, 0] = 1.0
    return a


# ─── T8 ─────────────────────────────────────────────────────────────────────


def test_t8_grid_from_array_stats_are_source_pixel_stats():
    a = _thirteen_valid_pixels().astype("float64")
    out = ig.grid_from_array(a, "ndvi", 2)
    # المتوسّط العلميّ = 1/13؛ متوسّط خلايا العرض غير الموزون كان 0.25.
    assert out["stats"]["mean"] == round(1 / 13, 4)
    assert out["stats"]["min"] == 0.0 and out["stats"]["max"] == 1.0
    # إحصاء خلايا العرض مُعلَن منفصلاً (لا يُقدَّم كمتوسّط الحقل).
    assert out["grid_stats"]["mean"] == 0.25


def test_t8_grid_from_cog_field_stats_invariant_to_display_grid(tmp_path):
    path = _write_scalar(tmp_path / "scalar.tif", _thirteen_valid_pixels(), nodata=np.nan)
    layer = {"cog_url": path, "field_id": "field", "geometry_revision": 1}
    g2 = layer_lookup.grid_from_cog(layer, "ndvi", "latest", 2, _IDENTITY_STORE)
    g4 = layer_lookup.grid_from_cog(layer, "ndvi", "latest", 4, _IDENTITY_STORE)
    assert g2 is not None and g4 is not None
    assert g2["stats"] == g4["stats"] == {"min": 0.0, "max": 1.0, "mean": round(1 / 13, 4)}
    assert g2["stats_basis"] == g4["stats_basis"] == "source_pixels"
    # خلايا العرض نفسها تبقى متوسّطات كتل (للخريطة) ومُعلَنة كإحصاء شبكة.
    assert g2["grid_stats"]["mean"] == 0.25
    assert g4["grid_stats"]["mean"] == round(1 / 13, 4)


def test_t8_field_stats_honour_internal_dataset_mask(tmp_path):
    vals = np.full((4, 4), 0.2, dtype="float32")
    vals[0, 0] = 0.9  # مخفيّ بالقناع الداخليّ ⇒ لا يدخل الإحصاء
    mask = np.full((4, 4), 255, dtype="uint8")
    mask[0, 0] = 0
    path = _write_scalar(tmp_path / "masked.tif", vals, mask=mask)
    layer = {"cog_url": path, "field_id": "field"}
    g = layer_lookup.grid_from_cog(layer, "ndvi", "latest", 4, _IDENTITY_STORE)
    assert g is not None
    assert g["stats"]["max"] == 0.2 and g["stats"]["mean"] == 0.2


# ─── T9 ─────────────────────────────────────────────────────────────────────


def test_t9_msi_is_not_classified_with_ndvi_fallback():
    out = ig.grid_from_array(np.array([[1.5]]), "msi", 1)
    # المُصيِّر يلوّنه أحمر (msi معكوس: عالٍ = إجهاد) — لا يجوز وسمه «low».
    assert tile_render.colorize(np.array([[1.5]]), "msi")[0, 0, 0] > 150
    assert all(z["severity"] != "low" for z in out["zones"])
    assert out["zones"] == []
    assert out["severity_supported"] is False


def test_t9_unknown_index_has_no_guessed_severity():
    out = ig.grid_from_array(np.array([[0.1]]), "not_an_index", 1)
    assert out["zones"] == [] and out["severity_supported"] is False


def test_t9_severity_direction_shares_renderer_dictionary():
    for index in ig._SEVERITY_THRESHOLDS:
        assert index in tile_render._INDEX_DOMAIN, index
        invert = tile_render._INDEX_DOMAIN[index][2]
        lo, hi = ig._SEVERITY_THRESHOLDS[index]
        worst = hi + 1.0 if invert else lo - 1.0
        best = lo - 1.0 if invert else hi + 1.0
        zones = ig.classify_zones([[worst, best]], index, 1, 2)
        sev = {tuple(c): z["severity"] for z in zones for c in z["cells"]}
        assert sev[(0, 0)] == "high" and sev[(0, 1)] == "low", index


def test_t9_supported_indices_still_classified():
    ndvi = ig.grid_from_array(np.array([[0.1, 0.8]]), "ndvi", 2)
    assert ndvi["severity_supported"] is True
    assert {z["severity"] for z in ndvi["zones"]} == {"high", "low"}
    sal = ig.grid_from_array(np.array([[0.5]]), "salinity", 1)
    assert sal["zones"][0]["severity"] == "high"


# ─── T10 ────────────────────────────────────────────────────────────────────


async def _pixel(monkeypatch, path: str, lon: float, lat: float) -> dict:
    import routers.fields as fields

    async def allow(*args, **kwargs):
        return None

    async def layer(*args, **kwargs):
        return {"cog_url": path, "acquisition_date": "2026-10-01", "source_format": "cog"}

    monkeypatch.setattr(fields, "_require_field_tenant", allow)
    monkeypatch.setattr(fields, "_resolve_field_layer", layer)
    return await fields.field_pixel_value(
        "fld-1", lat=lat, lon=lon, index="ndvi", date="latest", v=None
    )


@pytest.mark.asyncio
async def test_t10_point_read_rejects_internal_mask_pixel(monkeypatch, tmp_path):
    mask = np.full((4, 4), 255, dtype="uint8")
    mask[0, 0] = 0
    path = _write_scalar(tmp_path / "mask.tif", np.full((4, 4), 0.8), mask=mask)
    hidden = await _pixel(monkeypatch, path, lon=44.0005, lat=15.9995)
    assert hidden["valid"] is False and hidden["value"] is None
    assert hidden["reason"] == "nodata_or_masked"
    visible = await _pixel(monkeypatch, path, lon=44.0025, lat=15.9975)
    assert visible["valid"] is True
    assert visible["value"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_t10_point_read_rejects_scalar_nodata_and_nan(monkeypatch, tmp_path):
    a = np.full((4, 4), 0.5, dtype="float32")
    a[0, 0] = -9999.0
    a[3, 3] = np.nan
    path = _write_scalar(tmp_path / "nodata.tif", a, nodata=-9999.0)
    nd = await _pixel(monkeypatch, path, lon=44.0005, lat=15.9995)
    assert nd["valid"] is False and nd["value"] is None
    nan = await _pixel(monkeypatch, path, lon=44.0035, lat=15.9965)
    assert nan["valid"] is False and nan["value"] is None
    ok = await _pixel(monkeypatch, path, lon=44.0015, lat=15.9985)
    assert ok["valid"] is True and ok["value"] == pytest.approx(0.5)
