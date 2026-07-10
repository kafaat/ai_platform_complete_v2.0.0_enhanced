#!/usr/bin/env python3
"""Guard: raster indicators must expose ValidatedRasterProduct + cloud strategies."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATED = ROOT / "services/raster-service/raster_validated_product.py"
STRATEGIES = ROOT / "services/raster-service/raster_cloud_mask_strategies.py"
PIXEL = ROOT / "services/raster-service/raster_pixel_processing.py"
MODELS = ROOT / "services/raster-service/raster_api_models.py"
SMOKE = ROOT / "scripts/ci/runtime_real_smoke.sh"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    validated = _read(VALIDATED)
    strategies = _read(STRATEGIES)
    pixel = _read(PIXEL)
    models = _read(MODELS)
    smoke = _read(SMOKE)

    required_validated = [
        "class ValidatedRasterProduct",
        "quality_score: float",
        "valid_pixel_ratio: float",
        "cloud_mask_applied: bool",
        "shadow_mask_applied: bool",
        "reflectance_normalized: bool",
        "class ProvenanceRecord",
        "sahool.validated_raster_product/1",
        "sahool.raster_quality_flags/1",
        "sahool.raster_pixel_qa/1",
        "assert_indicator_accepts_validated_product",
    ]
    missing = [x for x in required_validated if x not in validated]
    if missing:
        raise SystemExit(f"validated raster product contract missing: {missing}")

    required_strategies = [
        "class CloudMaskStrategy",
        "class Sentinel2SCLStrategy",
        "class LandsatQAPixelStrategy",
        "class NoOpCloudMaskStrategy",
        "strategy_for_source_format",
        "source_has_no_native_cloud_mask",
        "QA_PIXEL",
        "SCL",
    ]
    missing = [x for x in required_strategies if x not in strategies]
    if missing:
        raise SystemExit(f"cloud mask strategy contract missing: {missing}")

    required_pixel = [
        "import raster_validated_product",
        "import raster_cloud_mask_strategies",
        "strategy_for_source_format",
        "strategy.apply",
        "build_validated_raster_product",
        "assert_indicator_accepts_validated_product",
        '"validated_raster_product"',
        "cloud_mask_strategy",
    ]
    missing = [x for x in required_pixel if x not in pixel]
    if missing:
        raise SystemExit(f"indicator path missing validated product wiring: {missing}")

    forbidden_inline = ["b.clp is not None", "b.clm is not None", "np.isin(scl"]
    present = [x for x in forbidden_inline if x in pixel]
    if present:
        raise SystemExit(f"indicator path still contains inline source-native cloud mask logic: {present}")

    if "qa_pixel" not in models:
        raise SystemExit("BandMapping missing qa_pixel for Landsat QA_PIXEL strategy")

    if "raster_validated_product_guard.py" not in smoke:
        raise SystemExit("runtime_real_smoke.sh does not include raster validated product guard")

    print("raster_validated_product_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
