"""Season-state scene selection and the pure season projection.

The endpoint's platform reads (archived-season water window, owner-only outcomes after
cutover, the optional-source savepoint) are proven against a migrated Postgres in
tests_v9/test_season_state_sources_live_pg.py.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from api import raster_service_client
from api.routers import seasons

TENANT = "00000000-0000-0000-0000-000000000abc"
START = date(2024, 11, 1)
END = date(2025, 3, 20)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["same", "different_scene", "different_geometry", "cloudy"])
async def test_season_image_date_and_identity(monkeypatch, variant):
    catalogue = {
        "field_id": "pivot",
        "dates": [
            {"date": "2024-10-10", "has_cog": True},
            {"date": "2025-03-10", "has_cog": True},
            {"date": "2025-03-18", "has_cog": False},
            {"date": "2026-03-12", "has_cog": True},
        ],
    }
    monkeypatch.setattr(
        raster_service_client, "get_available_dates", AsyncMock(return_value=catalogue)
    )

    async def points(field, *, tenant_id, index, dates):
        assert (field, tenant_id, dates) == ("pivot", TENANT, "2025-03-10")
        base = {"datetime": dates, "scene_id": "s1", "geometry_revision": 2, "mean": 0.2}
        if index == "ndmi":
            base.update(
                {
                    "same": {},
                    "different_scene": {"scene_id": "s2"},
                    "different_geometry": {"geometry_revision": 3},
                    "cloudy": {"cloud_pct": 95},
                }[variant]
            )
        return [base]

    monkeypatch.setattr(raster_service_client, "get_field_timeseries", points)
    scene = await seasons._season_state_scene("pivot", TENANT, START, END)
    assert scene["datetime"] == "2025-03-10"
    assert scene["ndmi"] == (0.2 if variant == "same" else None)


def test_archived_scene_compared_to_stage_on_its_own_date():
    from api.field_season_projection import assemble_field_season_state

    state = assemble_field_season_state(
        crop="wheat",
        sowing_date=START,
        today=date(2025, 2, 15),
        imagery_date=START,
        observed_ndvi=0.2,
        valid_pixel_ratio=0.9,
    )
    assert state["current_stage"] == "late"
    assert state["eo_stage_mismatch"]["stage"] == "initial"
