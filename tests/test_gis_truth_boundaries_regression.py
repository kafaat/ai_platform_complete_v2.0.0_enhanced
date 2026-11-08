"""Regression guards for GIS truth boundaries across services.

These tests deliberately load the production modules from their service roots,
rather than duplicating their decision logic.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(path: str):
    spec = importlib.util.spec_from_file_location(
        "gis_truth_" + Path(path).stem, ROOT / path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_common_valid_pixels_is_not_assessable():
    change = _module("services/raster-service/change_detection.py")
    result = change.detect_change([[None, None]], [[None, None]], index="ndvi")
    assert result["status"] == "not_assessable"
    assert result["valid_pixels"] == 0
    assert result["mean_delta"] is None
    assert "no_common_valid_pixels" in result["reason_codes"]


def test_field_route_preserves_kernel_assessment_status():
    # The field handler is an async HTTP integration boundary; this guard checks
    # the exact production assignment rather than importing the whole app stack.
    source = (ROOT / "services/raster-service/routers/fields.py").read_text()
    start = source.index("    result = cd.detect_change(")
    end = source.index("    return result", start)
    section = source[start:end]
    assert '"status": "assessed"' not in section
    assert '"available": result.get("status") == "assessed"' in section
    assert '"real_data": True,' in section


def test_required_unknown_check_is_not_accepted():
    checks = _module("services/gis-workflow-service/self_checks.py")
    result = checks.run_self_checks({"analysis": {"index": "ndvi"}, "target": {}}, {}, {})
    assert result["passed"] is False
    assert result["quality"] == "failed"


def test_dem_no_valid_pixels_has_explicit_refusal():
    source = (ROOT / "services/raster-service/terrain_analysis.py").read_text()
    start = source.index("    finite = np.isfinite(dem)")
    end = source.index("    dzdx = np.gradient", start)
    assert "if not ev.size:" in source[start:end]
    assert '"computed": False' in source[start:end]
