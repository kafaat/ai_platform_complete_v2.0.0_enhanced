"""Guard: GLO-30 DEM provisioning helper — correct tile naming + honest, no-fabrication.

`scripts/provision/fetch_glo30_dem.py` downloads real Copernicus GLO-30 COG tiles from
AWS Open Data (anonymous HTTPS) and mosaics them into one COG for FIELD_DEM_PATH — so
the terrain layers activate with real ESA data (never fabricated). Only the pure tile-key
logic is unit-tested here (no network in CI).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision" / "fetch_glo30_dem.py"


def _load():
    spec = importlib.util.spec_from_file_location("fetch_glo30_dem", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tile_name_matches_copernicus_convention():
    m = _load()
    # SW-corner naming (1°×1° tiles), zero-padded lat(2)/lon(3).
    assert m.tile_name(15, 44) == "Copernicus_DSM_COG_10_N15_00_E044_00_DEM"
    assert m.tile_name(0, 6) == "Copernicus_DSM_COG_10_N00_00_E006_00_DEM"
    assert m.tile_name(-16, -1) == "Copernicus_DSM_COG_10_S16_00_W001_00_DEM"


def test_tiles_for_bbox_covers_all_degree_cells():
    m = _load()
    # Al-Jawf-ish bbox spanning 2 lon × 2 lat degree cells → 4 tiles (43..45, 15..17).
    tiles = m.tiles_for_bbox([43.5, 15.5, 45.2, 16.8])
    assert (15, 43) in tiles and (16, 45) in tiles
    assert len(tiles) == 3 * 2  # lon 43,44,45 × lat 15,16


def test_url_uses_anonymous_aws_open_data_host():
    m = _load()
    url = m.tile_url(15, 44)
    assert url.startswith("https://copernicus-dem-30m.s3")
    assert url.endswith("Copernicus_DSM_COG_10_N15_00_E044_00_DEM.tif")
