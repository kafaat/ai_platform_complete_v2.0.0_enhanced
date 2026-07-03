from __future__ import annotations

import pytest
from sahool_platform_path import ensure_platform_path

ensure_platform_path()
from api.field_geometry_save_guard import (  # noqa: E402
    sanitize_boundary_metadata,
    validate_boundary_for_save,
)

pytestmark = pytest.mark.unit


def _poly(n: int = 5):
    ring = [[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]
    if n <= 5:
        return {"type": "Polygon", "coordinates": [ring[:n]]}
    many = [[44.0 + i * 0.000001, 15.0] for i in range(n - 1)]
    many.append(many[0])
    return {"type": "Polygon", "coordinates": [many]}


def test_validate_boundary_for_save_returns_metadata():
    meta = validate_boundary_for_save(_poly(), area_ha=1.25)
    assert meta["vertices"] == 5
    assert meta["area_ha"] == 1.25


def test_validate_boundary_for_save_rejects_vertex_explosion():
    with pytest.raises(ValueError) as exc:
        validate_boundary_for_save(_poly(2101), area_ha=5)
    assert "boundary_too_many_vertices" in str(exc.value)


def test_validate_boundary_for_save_rejects_degenerate_area():
    with pytest.raises(ValueError) as exc:
        validate_boundary_for_save(_poly(), area_ha=0)
    assert "boundary_area_too_small" in str(exc.value)


def test_sanitize_boundary_metadata_allowlist_only():
    meta = sanitize_boundary_metadata(
        {
            "source": "sam2",
            "mode": "auto",
            "confidence": 0.87,
            "model_version": "sam2-hiera-large",
            "x_agent_token": "must-not-pass",
            "tenant_id": "must-not-pass",
        }
    )
    assert meta["source"] == "sam2"
    assert meta["confidence"] == 0.87
    assert "x_agent_token" not in meta
    assert "tenant_id" not in meta
