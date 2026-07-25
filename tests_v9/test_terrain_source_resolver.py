"""Unit: multi-resolution terrain source registry + resolver + anti-phantom-resolution lineage.

Owner decision (TERRAIN): free global 30 m baseline (Copernicus GLO-30) with support for
validated 10 m / 5 m when supplied. Precedence: validated 5 m → validated 10 m → GLO-30 30 m,
gated by AOI coverage. No phantom resolution: a 30 m source resampled to a 5 m grid keeps
effective_resolution_m = 30 and is_upsampled = true — the encoding never raises real accuracy.

Runtime is OPERATOR_BLOCKED until DEM data is provisioned: with nothing provisioned the
resolver returns resolved=false with an honest reason (no fabricated terrain).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
CONFIG = ROOT / "config" / "terrain_sources.yml"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import terrain_source_registry as tsr  # noqa: E402


def _provisioned_sources() -> list[dict]:
    return [
        {
            "id": "copernicus-glo30",
            "model_type": "DSM",
            "native_resolution_m": 30,
            "coverage_type": "global",
            "source_kind": "public_baseline",
            "priority": 100,
            "status": "active",
            "provisioned": True,
            "uri": "/x/glo30.tif",
            "vertical_datum": "EGM2008",
        },
        {
            "id": "supplied-10m",
            "model_type": "DTM",
            "native_resolution_m": 10,
            "coverage_type": "selected_areas",
            "source_kind": "supplied",
            "priority": 200,
            "status": "validated",
            "provisioned": True,
            "uri": "/x/10m.tif",
            "coverage_bbox": [44.0, 15.0, 44.2, 15.2],
        },
        {
            "id": "supplied-5m",
            "model_type": "DTM",
            "native_resolution_m": 5,
            "coverage_type": "selected_areas",
            "source_kind": "supplied",
            "priority": 300,
            "status": "validated",
            "provisioned": True,
            "uri": "/x/5m.tif",
            "coverage_bbox": [44.0, 15.0, 44.05, 15.05],
        },
    ]


def test_registry_config_has_glo30_baseline_and_optional_hi_res():
    sources = tsr.load_terrain_sources(config_path=CONFIG, field_dem_path="")
    ids = {s["id"] for s in sources}
    assert "copernicus-glo30" in ids, "GLO-30 must be the declared global baseline"
    assert {"supplied-10m", "supplied-5m"} <= ids, "10 m + 5 m optional sources must be declared"
    baseline = next(s for s in sources if s["id"] == "copernicus-glo30")
    assert baseline["native_resolution_m"] == 30
    assert baseline["coverage_type"] == "global"
    # Nothing is provisioned in-repo — honest OPERATOR_BLOCKED default.
    assert all(not s.get("provisioned") for s in sources)


def test_unprovisioned_resolves_false_operator_blocked():
    sources = tsr.load_terrain_sources(config_path=CONFIG, field_dem_path="")
    r = tsr.resolve_terrain_source(sources, field_bbox=[44.0, 15.0, 44.1, 15.1])
    assert r["resolved"] is False
    assert r["dem_path"] is None
    assert r["reason"] == "no_provisioned_terrain_source_covers_field"


def test_precedence_5m_beats_10m_beats_30m_by_coverage():
    sources = _provisioned_sources()
    # inside 5 m coverage → 5 m
    r5 = tsr.resolve_terrain_source(sources, field_bbox=[44.0, 15.0, 44.04, 15.04])
    assert r5["lineage"]["terrain_source_id"] == "supplied-5m"
    assert r5["native_resolution_m"] == 5.0
    # inside 10 m but outside 5 m → 10 m
    r10 = tsr.resolve_terrain_source(sources, field_bbox=[44.1, 15.1, 44.15, 15.15])
    assert r10["lineage"]["terrain_source_id"] == "supplied-10m"
    # outside both selected areas → global 30 m baseline
    r30 = tsr.resolve_terrain_source(sources, field_bbox=[50.0, 20.0, 50.1, 20.1])
    assert r30["lineage"]["terrain_source_id"] == "copernicus-glo30"
    assert r30["native_resolution_m"] == 30.0


def test_partial_coverage_does_not_use_hi_res():
    # A field straddling the 5 m edge is NOT fully covered → must fall through to 10 m.
    sources = _provisioned_sources()
    r = tsr.resolve_terrain_source(sources, field_bbox=[44.04, 15.04, 44.08, 15.08])
    assert r["lineage"]["terrain_source_id"] == "supplied-10m"


def test_anti_phantom_resolution_effective_is_max():
    # 30 m native stored/displayed at 5 m pixels: effective stays 30 m, flagged upsampled.
    assert tsr.effective_resolution_m(30, 5) == 30.0
    assert tsr.is_upsampled(30, 5) is True
    # a true 5 m source at 5 m storage is not upsampled
    assert tsr.effective_resolution_m(5, 5) == 5.0
    assert tsr.is_upsampled(5, 5) is False
    lin = tsr.terrain_lineage(_provisioned_sources()[0], storage_pixel_size_m=5)
    assert lin["native_resolution_m"] == 30.0
    assert lin["effective_resolution_m"] == 30.0
    assert lin["is_upsampled"] is True


def test_terrain_rgb_roundtrip_and_metadata_keeps_native():
    for h in (-412.5, 0.0, 1234.5, 3000.0):
        r, g, b = tsr.encode_terrain_rgb(h)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
        assert abs(tsr.decode_terrain_rgb(r, g, b) - h) < 0.05
    lin = tsr.terrain_lineage(_provisioned_sources()[0], storage_pixel_size_m=5)
    meta = tsr.terrain_rgb_metadata(lin)
    assert meta["encoding"] == "terrain-rgb"
    # encoding must NOT claim raised resolution
    assert meta["native_resolution_m"] == 30.0
    assert meta["effective_resolution_m"] == 30.0
    assert meta["is_upsampled"] is True


def test_field_dem_path_backcompat_provisions_baseline(tmp_path):
    dem = tmp_path / "glo30.tif"
    dem.write_bytes(b"\x00")  # existence is enough for the resolver's file check
    sources = tsr.load_terrain_sources(config_path=CONFIG, field_dem_path=str(dem))
    baseline = next(s for s in sources if s["id"] == "copernicus-glo30")
    assert baseline["provisioned"] is True
    assert baseline["uri"] == str(dem)
    r = tsr.resolve_terrain_source(sources, field_bbox=[44.0, 15.0, 44.1, 15.1])
    assert r["resolved"] is True
    assert r["dem_path"] == str(dem)
    assert r["native_resolution_m"] == 30.0


def test_resolution_policy_summary_shape():
    policy = tsr.resolution_policy(tsr.load_terrain_sources(config_path=CONFIG, field_dem_path=""))
    assert policy["baseline"]["dataset"] == "copernicus-glo30"
    assert policy["baseline"]["native_resolution_m"] == 30
    assert policy["selection_policy"] == ["validated_5m", "validated_10m", "glo30_30m"]
    assert {s["native_resolution_m"] for s in policy["optional_sources"]} == {10, 5}
