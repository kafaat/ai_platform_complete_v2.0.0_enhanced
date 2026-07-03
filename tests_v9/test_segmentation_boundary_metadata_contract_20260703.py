from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_segmentation_proxy_keeps_platform_trust_boundary():
    nginx = _read("nginx/nginx.v9.conf")
    proxy = _read("services/sahool-platform/api/routers/service_proxy.py")
    assert "location /api/segmentation/" in nginx
    assert "proxy_pass http://platform_backend/api/segmentation/" in nginx
    assert "X-Agent-Token" in proxy and "X-Tenant-Id" in proxy
    assert "http://sahool-field-segmentation:8000" in proxy


def test_segmentation_response_carries_boundary_metadata_to_frontend_save():
    seg = _read("services/field-segmentation/main.py")
    sam2 = _read("services/sam2-inference/main.py")
    add = _read("frontend/src/components/AddFieldWithMap.tsx")
    fields = _read("services/sahool-platform/api/routers/fields.py")
    assert '"metadata": metadata' in seg
    assert '"post_processing"' in sam2 and '"inference_ms"' in sam2
    assert "setBoundaryMetadata" in add
    assert "boundary_metadata: boundaryMetadata" in add
    assert "sanitize_boundary_metadata" in fields
    assert "save_field_geometry_revision" in fields and "boundary_metadata" in fields


def test_field_save_guard_blocks_bad_boundary_before_persist():
    guard = _read("services/sahool-platform/api/field_geometry_save_guard.py")
    fields = _read("services/sahool-platform/api/routers/fields.py")
    assert "MAX_FIELD_VERTEX_COUNT" in guard
    assert "boundary_too_many_vertices" in guard
    assert "boundary_area_too_small" in guard
    assert "validate_boundary_for_save(geometry" in fields
    assert "validate_boundary_for_save(guarded.geometry" in fields
