#!/usr/bin/env python3
"""Guard: raster indicator QA must carry honest topographic QA provenance."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIXEL = ROOT / "services/raster-service/raster_pixel_processing.py"
RAW = ROOT / "services/raster-service/raw_data_processing.py"
MODELS = ROOT / "services/raster-service/raster_api_models.py"
ORCH = ROOT / "services/raster-service/raster_job_orchestration.py"
TOPO = ROOT / "services/raster-service/raster_topographic_qa.py"
SMOKE = ROOT / "scripts/ci/runtime_real_smoke.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    pixel = _read(PIXEL)
    raw = _read(RAW)
    models = _read(MODELS)
    orch = _read(ORCH)
    topo = _read(TOPO)
    smoke = _read(SMOKE)

    required_topo = [
        "def build_topographic_qa",
        "def compute_topographic_risk_from_dem",
        "def compute_cast_shadow_mask_from_dem",
        "def build_topographic_qa_from_dem_array",
        '"schema": "sahool.raster_topographic_qa/1"',
        '"fabricated_topographic_mask": False',
        "dem_not_aligned_to_indicator_grid",
        "terrain_shadow_risk_unavailable",
        "slope_risk_unavailable",
        "dem_hillshade_slope",
        "dem_cast_shadow_hillshade_slope",
        "shadow_hillshade_threshold",
        "cast_shadow_risk_pct",
        "cast_shadow_available",
        "cast_shadow_max_steps",
    ]
    missing = [token for token in required_topo if token not in topo]
    if missing:
        raise SystemExit(f"raster_topographic_qa.py missing honest topographic contract: {missing}")

    required_pixel = [
        "import raster_topographic_qa",
        "def _topographic_qa_for_indicator",
        "FIELD_DEM_PATH",
        "reproject(",
        "build_topographic_qa_from_dem_array",
        "sun_azimuth_deg",
        "sun_altitude_deg",
        '"topographic_qa"',
        "topographic_qa_applied",
        "terrain_shadow_risk_pct",
        "cast_shadow_risk_pct",
        "slope_risk_pct",
        "topographic_qa_sources",
    ]
    missing = [token for token in required_pixel if token not in pixel]
    if missing:
        raise SystemExit(f"raster_pixel_processing.py missing topographic QA wiring: {missing}")


    required_models = [
        "sun_azimuth_deg",
        "sun_altitude_deg",
        "ge=0.0, le=360.0",
        "ge=-90.0, le=90.0",
    ]
    missing = [token for token in required_models if token not in models]
    if missing:
        raise SystemExit(f"raster_api_models.py missing sun geometry request contract: {missing}")

    required_orch = [
        "sun_azimuth_deg=getattr(req,",
        "sun_altitude_deg=getattr(req,",
    ]
    missing = [token for token in required_orch if token not in orch]
    if missing:
        raise SystemExit(f"raster_job_orchestration.py does not propagate sun geometry in batch processing: {missing}")

    required_raw = [
        "terrain_shadow_risk_pct",
        "cast_shadow_risk_pct",
        "slope_risk_pct",
        "topographic_qa_applied",
        '"topographic_qa"',
        '"fabricated_topographic_mask": False',
        "terrain_shadow_penalty",
        "slope_risk_penalty",
    ]
    missing = [token for token in required_raw if token not in raw]
    if missing:
        raise SystemExit(f"raw_data_processing.py missing topographic QA scoring/provenance: {missing}")

    if "raster_topographic_qa_guard.py" not in smoke:
        raise SystemExit("runtime_real_smoke.sh does not include raster topographic QA guard")

    print("raster_topographic_qa_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
