#!/usr/bin/env python3
"""Guard: raster indicators must carry raw pixel QA/provenance."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIXEL = ROOT / "services/raster-service/raster_pixel_processing.py"
RAW = ROOT / "services/raster-service/raw_data_processing.py"
MODELS = ROOT / "services/raster-service/raster_api_models.py"
JOB = ROOT / "services/raster-service/raster_job_orchestration.py"
RUNTIME_SMOKE = ROOT / "scripts/ci/runtime_real_smoke.sh"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    pixel = _read(PIXEL)
    raw = _read(RAW)
    models = _read(MODELS)
    job = _read(JOB)
    smoke = _read(RUNTIME_SMOKE)

    required_pixel = [
        "raw_data_processing.compute_quality_score",
        '"raw_qa_required"',
        '"raw_quality_score"',
        '"pixel_qa"',
        '"quality_flags"',
        "raw_raster_quality_below_threshold",
        "min_raw_quality_score",
        "cloud_shadow_mask_sources",
        "saturation_mask_sources",
        "build_quality_flags",
    ]
    missing = [x for x in required_pixel if x not in pixel]
    if missing:
        raise SystemExit(f"raster pixel processing missing raw QA wiring: {missing}")

    required_raw = [
        "def compute_quality_score",
        '"schema": "sahool.raster_pixel_qa/1"',
        '"quality_flags"',
        '"sahool.raster_quality_flags/1"',
        '"cloud_shadow_mask_applied"',
        '"saturation_mask_applied"',
        '"spatial_alignment"',
        '"temporal_alignment"',
        '"fabricated_indicator": False',
        '"indicator_computed": False',
    ]
    missing = [x for x in required_raw if x not in raw]
    if missing:
        raise SystemExit(f"raw data processing missing QA/provenance contract: {missing}")

    for token in ["raw_qa_required: bool = True", "min_raw_quality_score"]:
        if token not in models:
            raise SystemExit(f"raster API models missing {token}")

    for token in [
        '"raw_processing"',
        '"sahool.raw_processing/1"',
        '"derived_product_computed": True',
    ]:
        if token not in job:
            raise SystemExit(f"raster job provenance missing {token}")

    if "raster_pixel_qa_indicator_guard.py" not in smoke:
        raise SystemExit("runtime_real_smoke.sh does not include raster pixel QA indicator guard")

    print("raster_pixel_qa_indicator_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
