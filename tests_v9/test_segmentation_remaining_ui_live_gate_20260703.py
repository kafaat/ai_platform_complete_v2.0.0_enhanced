from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_add_field_has_client_boundary_improvement_tools():
    ui = _read("frontend/src/components/AddFieldWithMap.tsx")
    assert "type BoundaryImproveLevel" in ui
    assert "improveBoundaryRing" in ui
    assert "handleImproveBoundary" in ui
    assert "client_refined" in ui
    assert "client_simplify_tolerance_m" in ui
    assert "خفيف 1م" in ui and "موصى 3م" in ui and "قوي 5م" in ui
    assert "مصدر الحد" in ui and "الرؤوس" in ui


def test_live_segmentation_platform_gate_exists_and_uses_platform_route():
    gate = _read("scripts/e2e/segmentation_platform_live_gate.py")
    assert "SAHOOL_JWT" in gate
    assert "/api/segmentation/segment" in gate
    assert "SEGMENTATION_REQUIRE_MODEL" in gate
    assert "SAM2_BASE_URL" in gate
    assert "model_loaded" in gate
    assert "Authorization" in gate


def test_manual_fallback_metadata_remains_when_no_sam2_boundary():
    ui = _read("frontend/src/components/AddFieldWithMap.tsx")
    assert "boundary_metadata: boundaryMetadata ?? { source: 'manual', mode: 'manual' }" in ui
    assert "setBoundaryMetadata(null)" in ui
