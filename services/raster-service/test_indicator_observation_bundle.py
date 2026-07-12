from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from routers import fields  # noqa: E402


@pytest.mark.asyncio
async def test_bundle_reports_consistent_single_scene(monkeypatch):
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)

    async def allow_field(field_id: str, **kwargs):
        return None

    async def resolve(field_id: str, index: str, date: str):
        return {"field_id": field_id, "scene_id": "scene-1", "acquisition_date": "2026-07-10"}

    def grid(layer, index, date, size):
        return {
            "real_data": True,
            "date": "2026-07-10",
            "stats": {"mean": 0.5},
            "indicator_product": {
                "provenance": {
                    "scene_id": "scene-1",
                    "acquisition_datetime": "2026-07-10",
                }
            },
        }

    monkeypatch.setattr(fields, "_require_field_tenant", allow_field)
    monkeypatch.setattr(fields, "_resolve_field_layer", resolve)
    monkeypatch.setattr(fields, "_grid_from_cog", grid)

    result = await fields.field_indicator_observation_bundle(
        "field-1", indices="ndvi,ndmi,ndvi", date="latest", grid=16, x_agent_token="token"
    )

    assert result["requested"] == ["ndvi", "ndmi"]
    assert result["bundle_consistency"] is True
    assert result["mixed_scene"] is False
    assert result["scene_ids"] == ["scene-1"]


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
            "indicator_product": {"provenance": {"scene_id": layer["scene_id"]}},
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
