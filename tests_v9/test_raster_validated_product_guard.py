from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_raster_validated_product_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/raster_validated_product_guard.py"],
        cwd=ROOT,
        check=True,
    )


def test_guard_covers_validated_indicator_product():
    """The guard must also protect the ValidatedIndicatorProduct wiring (WS-A)."""
    guard = (ROOT / "scripts/ci/raster_validated_product_guard.py").read_text(encoding="utf-8")
    for token in (
        "raster_indicator_product.py",
        "class ValidatedIndicatorProduct",
        "sahool.validated_indicator_product/1",
        "layer_lookup.grid_from_cog missing indicator_product wiring",
        # صدق الإنتاج (20260712): حُذفت شبكة المحاكاة نهائيّاً — الحارس يمنع عودتها
        # بدل مطالبة synthetic_grid بحمل indicator_product (لم تعد موجودة أصلاً).
        "production indicator_grid still contains a synthetic serving path",
    ):
        assert token in guard, f"guard no longer enforces: {token}"

    module = ROOT / "services/raster-service/raster_indicator_product.py"
    assert module.exists(), "raster_indicator_product.py must exist for the guard to protect"
