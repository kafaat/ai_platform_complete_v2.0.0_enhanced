from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PIXEL_PROCESSING = ROOT / "services" / "raster-service" / "raster_pixel_processing.py"
CLOUD_STRATEGIES = ROOT / "services" / "raster-service" / "raster_cloud_mask_strategies.py"


def _pixel_source() -> str:
    return PIXEL_PROCESSING.read_text(encoding="utf-8")


def _strategy_source() -> str:
    return CLOUD_STRATEGIES.read_text(encoding="utf-8")


def test_savi_denominator_is_guarded_with_np_where() -> None:
    src = _pixel_source()
    savi_block_start = src.index('elif ind == "savi":')
    savi_block_end = src.index('elif ind == "vari":', savi_block_start)
    block = src[savi_block_start:savi_block_end]
    assert "_denom = nir + red + 0.5" in block
    assert "np.where(_denom == 0, 1e-10, _denom)" in block


def test_savi_zero_denominator_formula_stays_finite() -> None:
    nir = np.array([-0.25], dtype="float32")
    red = np.array([-0.25], dtype="float32")
    denom = nir + red + 0.5
    out = 1.5 * (nir - red) / np.where(denom == 0, 1e-10, denom)
    assert np.isfinite(out[0])
    assert float(out[0]) == pytest.approx(0.0)


def test_clp_all_nan_is_guarded_before_nanmax() -> None:
    src_pixel = _pixel_source()
    src_strategies = _strategy_source()
    combined = src_pixel + "\n" + src_strategies
    assert "finite = np.isfinite(clp_f)" in combined
    assert "if bool(np.any(finite))" in combined
    assert "clp_max = float(np.nanmax(clp_f))" in combined
    assert "np.where(finite, clp_f >= threshold, False)" in combined
    assert "sentinel2_clp_all_nan_unavailable" in combined


def test_clp_all_nan_strategy_math_is_false_without_warning_path() -> None:
    clp_f = np.array([[np.nan, np.nan]], dtype="float32")
    finite = np.isfinite(clp_f)
    if bool(np.any(finite)):
        clp_max = float(np.nanmax(clp_f))
        threshold = 0.40 if clp_max <= 1.0 else 40.0
        clp_mask = np.where(finite, clp_f >= threshold, False)
    else:
        clp_mask = np.zeros_like(clp_f, dtype=bool)
    assert clp_mask.dtype == np.bool_
    assert not bool(np.any(clp_mask))
