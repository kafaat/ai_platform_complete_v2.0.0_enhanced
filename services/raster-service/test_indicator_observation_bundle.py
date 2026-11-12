from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from raster_indicator_product import from_grid_response  # noqa: E402
from routers import fields  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_ratio", [1.0, 0.0, None])
async def test_bundle_reports_consistent_single_scene(monkeypatch, valid_ratio):
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)

    async def allow_field(field_id: str, **kwargs):
        return None

    async def resolve(field_id: str, index: str, date: str):
        return {"field_id": field_id, "scene_id": "scene-1", "acquisition_date": "2026-07-10"}

    def grid(layer, index, date, size):
        payload = {
            "field_id": layer["field_id"],
            "index": index,
            "real_data": True,
            "date": "2026-07-10",
            "stats": {"mean": 0.0},
            "valid_pixel_ratio": valid_ratio,
        }
        payload["indicator_product"] = from_grid_response(payload)
        return payload

    monkeypatch.setattr(fields, "_require_field_tenant", allow_field)
    monkeypatch.setattr(fields, "_resolve_field_layer", resolve)
    monkeypatch.setattr(fields, "_grid_from_cog", grid)

    result = await fields.field_indicator_observation_bundle(
        "field-1", indices="ndvi,ndmi,ndvi", date="latest", grid=16, x_agent_token="token"
    )

    assert result["requested"] == ["ndvi", "ndmi"]
    assert result["bundle_consistency"] is True
    assert result["mixed_scene"] is False
    if valid_ratio == 1.0:
        assert result["scene_ids"] == ["scene-1"]
        assert set(result["observations"]) == {"ndvi", "ndmi"}
        assert result["complete"] is True  # measured zero is still an observation
    else:
        assert result["scene_ids"] == []
        assert result["observations"] == {}
        assert set(result["unavailable"]) == {"ndvi", "ndmi"}
        assert result["complete"] is False


@pytest.mark.asyncio
async def test_bundle_marks_mixed_scenes(monkeypatch):
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)

    async def allow_field(field_id: str, **kwargs):
        return None

    async def resolve(field_id: str, index: str, date: str):
        scene = "scene-a" if index == "ndvi" else "scene-b"
        return {"field_id": field_id, "scene_id": scene, "acquisition_date": "2026-07-10"}

    def grid(layer, index, date, size):
        return {
            "real_data": True,
            "date": layer["acquisition_date"],
            "stats": {"mean": 0.5},
            "indicator_product": {
                "quality_gate_passed": True,
                "valid_pixel_ratio": 1.0,
                "provenance": {"scene_id": layer["scene_id"]},
            },
        }

    monkeypatch.setattr(fields, "_require_field_tenant", allow_field)
    monkeypatch.setattr(fields, "_resolve_field_layer", resolve)
    monkeypatch.setattr(fields, "_grid_from_cog", grid)

    result = await fields.field_indicator_observation_bundle(
        "field-1", indices="ndvi,ndmi", date="latest", grid=16, x_agent_token="token"
    )

    assert result["bundle_consistency"] is False
    assert result["mixed_scene"] is True
    assert result["scene_ids"] == ["scene-a", "scene-b"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("spacings", "expected"),
    [([7.5, 7.5], 7.5), ([7.5, 20.0], None), ([7.5, None], None), ([None, None], None)],
)
async def test_field_indices_reports_spacing_only_when_observed_products_agree(
    monkeypatch, spacings, expected
):
    from routers import observability

    async def resolve(field_id, index, date, **kwargs):
        return {"index": index}

    def grid(layer, index, date, size, object_store):
        spacing = dict(zip(["ndvi", "ndmi"], spacings, strict=True))[index]
        return {
            "stats": {"mean": 0.25},
            "grid": [[0.25]],
            "spatial_sampling": {"output_pixel_size_m": [spacing, spacing]} if spacing else None,
        }

    monkeypatch.setattr(observability, "AGENT_TOKEN", "test-token")
    monkeypatch.setattr(observability, "resolve_field_layer", resolve)
    monkeypatch.setattr(observability, "grid_from_cog", grid)
    result = await observability.field_indices(
        "field-1", date="latest", indices="ndvi,ndmi", x_agent_token="test-token"
    )
    assert result["real_data"] is True
    assert result["resolution_m"] == expected
