"""Guard: docker-compose.v9.yml wires terrain/soil provisioning so the feature can
actually activate at runtime (external review P0#3 — env + mounts were missing).

Without SOILGRIDS_DIR + DEM/soil mounts the default deployment reports the terrain and
soil layers as available:false forever. Fail-closed defaults are honest; but the env
knobs + read-only mounts must exist so an operator can drop in DEM/SoilGrids data.
Pure static YAML scan — unit tier.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.v9.yml"


def _raster_service() -> dict:
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    return data["services"]["sahool-raster-service"]


def test_raster_service_declares_dem_and_soilgrids_env():
    env = _raster_service()["environment"]
    assert "FIELD_DEM_PATH" in env, "FIELD_DEM_PATH غير مُعلَن — التضاريس لا تُفعَّل"
    assert "SOILGRIDS_DIR" in env, "SOILGRIDS_DIR غير مُعلَن — طبقة التربة لا تُفعَّل"
    # الافتراضيّات fail-closed (مسار/مجلّد قد لا يوجد ⇒ available:false صادق) لا قيم مُلفَّقة.
    assert "SOILGRIDS_DIR" in str(env["SOILGRIDS_DIR"])
    assert "FIELD_DEM_PATH" in str(env["FIELD_DEM_PATH"])


def test_raster_service_mounts_dem_and_soilgrids_readonly():
    vols = _raster_service()["volumes"]
    joined = "\n".join(vols)
    assert "/data/dem:ro" in joined, "لا mount لـDEM (read-only)"
    assert "/data/soilgrids:ro" in joined, "لا mount لـSoilGrids (read-only)"


def test_raster_read_window_cap_configurable():
    env = _raster_service()["environment"]
    assert "RASTER_MAX_READ_DIM" in env, "سقف نافذة القراءة غير قابل للضبط"
