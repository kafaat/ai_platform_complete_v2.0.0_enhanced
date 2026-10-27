"""/v1/fields/{field_id}/change — محاذاة الشبكتين وبوّابة الجودة قبل الطرح (S2-a/S2-b).

يكشف المسار التغيّر بطرح شبكة تاريخ من آخر. تساوي rows/cols وحده لا يُثبت أنّ الخلايا
تقابل الأرض نفسها: شبكتان 2×2 من موقعين مختلفين ونسختي هندسة مختلفتين كانتا تُرجِعان
real_data=true و«تدهور 100%». العقد المُعاد استعماله هو عقد ``/v1/change/detect``
(``ChangeGridIdentity``: CRS + affine + geometry_revision + rows/cols)، وكلّ جانب يجب أن
يجتاز بوّابة جودته (``eligible_observation_product``) — وإلّا ``not_assessable`` بلا أرقام.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import routers.fields as fields  # noqa: E402
from raster_api_models import FieldChangeRequest  # noqa: E402

pytestmark = pytest.mark.unit

_IDENT = {
    "crs": "EPSG:32638",
    "transform": [10.0, 0.0, 500000.0, 0.0, -10.0, 1700000.0],
    "geometry_revision": 1,
    "rows": 2,
    "cols": 2,
}


def _grid(date: str, value: float, *, identity=_IDENT, gate: bool = True, bbox=None) -> dict:
    return {
        "date": date,
        "rows": 2,
        "cols": 2,
        "grid": [[value, value], [value, value]],
        "bbox": bbox or [44.0, 15.0, 44.01, 15.01],
        "grid_identity": identity,
        "real_data": True,
        "indicator_product": {
            "source": "raster-service",
            "estimated": False,
            "real_data": True,
            "quality_gate_passed": gate,
            "valid_pixel_ratio": 1.0 if gate else None,
        },
    }


def _install(monkeypatch, grid_a: dict | None, grid_b: dict | None) -> None:
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)
    by_date = {"2026-01-01": grid_a, "2026-02-01": grid_b}

    async def fake_grid(field_id, index, date, grid):
        return by_date[date]

    monkeypatch.setattr(fields, "_real_field_grid", fake_grid)


def _req() -> FieldChangeRequest:
    return FieldChangeRequest(index="ndvi", date_a="2026-01-01", date_b="2026-02-01", grid=2)


def _assert_not_assessable(out: dict, reason: str) -> None:
    assert out["available"] is False, out
    assert out["real_data"] is False
    assert out["status"] == "not_assessable"
    assert reason in out["reason_codes"], out["reason_codes"]
    # لا أرقام تغيّر حين لا يُقارَن: لا delta/نِسَب تُقرأ كرصد.
    for key in ("delta_grid", "change_grid", "degraded_pct", "improved_pct", "mean_delta"):
        assert key not in out


@pytest.mark.asyncio
async def test_s2a_disjoint_locations_and_geometry_versions_are_not_subtracted(monkeypatch):
    """شاهد التدقيق نفسه: أصلان جغرافيّان مختلفان + نسختا هندسة 1/2 ⇒ لا «تدهور 100%»."""
    ident_b = {
        **_IDENT,
        "transform": [10.0, 0.0, 610000.0, 0.0, -10.0, 1810000.0],
        "geometry_revision": 2,
    }
    _install(
        monkeypatch,
        _grid("2026-01-01", 0.8),
        _grid("2026-02-01", 0.2, identity=ident_b, bbox=[45.0, 16.0, 45.01, 16.01]),
    )
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_mismatch")


@pytest.mark.parametrize(
    "override",
    [
        {"crs": "EPSG:32639"},
        {"transform": [10.0, 0.0, 500010.0, 0.0, -10.0, 1700000.0]},
        {"transform": [20.0, 0.0, 500000.0, 0.0, -20.0, 1700000.0]},
        {"geometry_revision": 2},
    ],
    ids=["crs", "origin", "resolution", "geometry_revision"],
)
@pytest.mark.asyncio
async def test_s2a_each_identity_component_is_enforced(monkeypatch, override):
    _install(
        monkeypatch,
        _grid("2026-01-01", 0.8),
        _grid("2026-02-01", 0.2, identity={**_IDENT, **override}),
    )
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_mismatch")


@pytest.mark.parametrize("missing_side", ["a", "b"])
@pytest.mark.asyncio
async def test_s2a_missing_identity_is_not_assessable(monkeypatch, missing_side):
    """بلا هويّة مكانيّة لا يمكن إثبات التقابل ⇒ not_assessable (كعقد /v1/change/detect)."""
    a = _grid("2026-01-01", 0.8, identity=None if missing_side == "a" else _IDENT)
    b = _grid("2026-02-01", 0.2, identity=None if missing_side == "b" else _IDENT)
    _install(monkeypatch, a, b)
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_required")


@pytest.mark.asyncio
async def test_dimension_mismatch_is_not_assessable_instead_of_409(monkeypatch):
    """أبعاد مختلفة جزءٌ من الهويّة: رفض صادق بحمولة not_assessable (كان 409 قبل العقد)."""
    b = _grid("2026-02-01", 0.2, identity={**_IDENT, "rows": 3})
    b["rows"], b["grid"] = 3, [[0.2, 0.2], [0.2, 0.2], [0.2, 0.2]]
    _install(monkeypatch, _grid("2026-01-01", 0.8), b)
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_mismatch")


@pytest.mark.asyncio
async def test_declared_identity_must_match_actual_grid_shape(monkeypatch):
    a = _grid("2026-01-01", 0.8)
    a["grid"] = [[0.8, 0.8]]
    _install(monkeypatch, a, _grid("2026-02-01", 0.2))
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_dimensions_mismatch")


@pytest.mark.asyncio
async def test_invalid_identity_is_not_assessable(monkeypatch):
    bad = {**_IDENT, "transform": [float("nan"), 0.0, 500000.0, 0.0, -10.0, 1700000.0]}
    _install(monkeypatch, _grid("2026-01-01", 0.8, identity=bad), _grid("2026-02-01", 0.2))
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_invalid")


@pytest.mark.asyncio
async def test_s2a_singular_transform_is_rejected(monkeypatch):
    singular = {**_IDENT, "transform": [0.0, 0.0, 500000.0, 0.0, -10.0, 1700000.0]}
    _install(
        monkeypatch,
        _grid("2026-01-01", 0.8, identity=singular),
        _grid("2026-02-01", 0.2, identity=singular),
    )
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_singular_transform")


@pytest.mark.parametrize("failed_side", ["a", "b"])
@pytest.mark.asyncio
async def test_s2b_quality_gate_failure_on_either_side_is_honoured(monkeypatch, failed_side):
    a = _grid("2026-01-01", 0.8, gate=failed_side != "a")
    b = _grid("2026-02-01", 0.2, gate=failed_side != "b")
    _install(monkeypatch, a, b)
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_quality_gate_failed")
    failed_date = "2026-01-01" if failed_side == "a" else "2026-02-01"
    assert out["quality_failed_dates"] == [failed_date]


@pytest.mark.asyncio
async def test_s2b_missing_indicator_product_is_not_quality_eligible(monkeypatch):
    a = _grid("2026-01-01", 0.8)
    a.pop("indicator_product")
    _install(monkeypatch, a, _grid("2026-02-01", 0.2))
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_quality_gate_failed")


@pytest.mark.asyncio
async def test_aligned_quality_passed_grids_are_assessed_on_common_support(monkeypatch):
    a = _grid("2026-01-01", 0.8)
    a["grid"] = [[0.8, None], [0.8, 0.8]]
    _install(monkeypatch, a, _grid("2026-02-01", 0.2))
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    assert out["available"] is True and out["real_data"] is True
    assert out["status"] == "assessed"
    assert out["grid_identity"] == _IDENT
    assert out["percentage_denominator"] == "common_valid_pixels"
    assert out["valid_pixels"] == 3
    assert out["coverage_pct"] == 75.0
    assert out["degraded_pct"] == 100.0


@pytest.mark.asyncio
async def test_missing_grid_still_reports_unavailable(monkeypatch):
    _install(monkeypatch, None, _grid("2026-02-01", 0.2))
    out = await fields.field_change("f", _req(), x_agent_token="ok")
    assert out["available"] is False and out["real_data"] is False
    assert out["missing_dates"] == ["2026-01-01"]


@pytest.mark.asyncio
async def test_real_cogs_misregistered_by_origin_are_not_assessable(tmp_path, monkeypatch):
    """شبكتان حقيقيّتان من grid_from_cog بنفس الأبعاد لكن بأصل مُزاح ⇒ لا طرح."""
    from types import SimpleNamespace

    import layer_lookup
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    def cog(name: str, origin_x: float, value: float) -> dict:
        path = tmp_path / name
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=4,
            width=4,
            count=1,
            dtype="float32",
            crs="EPSG:32638",
            transform=from_origin(origin_x, 1600000, 10, 10),
        ) as dst:
            dst.write(np.full((4, 4), value, dtype="float32"), 1)
        return {
            "cog_url": str(path),
            "field_id": "fld_1",
            "geometry_revision": 3,
            "valid_pixel_ratio": 1.0,
            "source_format": "geotiff",
        }

    store = SimpleNamespace(to_gdal_path=lambda p: p)
    layers = {
        "2026-01-01": cog("a.tif", 400000, 0.8),
        "2026-02-01": cog("b.tif", 400000, 0.2),
    }

    async def real_grid(field_id, index, date, grid):
        return layer_lookup.grid_from_cog(layers[date], index, date, grid, store)

    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)
    monkeypatch.setattr(fields, "_real_field_grid", real_grid)
    aligned = await fields.field_change("fld_1", _req(), x_agent_token="ok")
    assert aligned["status"] == "assessed" and aligned["degraded_pct"] == 100.0

    layers["2026-02-01"] = cog("b_shifted.tif", 400040, 0.2)
    out = await fields.field_change("fld_1", _req(), x_agent_token="ok")
    _assert_not_assessable(out, "change_grid_spatial_identity_mismatch")
