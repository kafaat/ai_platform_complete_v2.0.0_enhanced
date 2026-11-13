from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from api import decision_service_client, decision_sor_mode, main, raster_service_client
from api.routers import seasons
from fastapi import HTTPException

TENANT = "00000000-0000-0000-0000-000000000abc"
START = date(2024, 11, 1)
END = date(2025, 3, 20)


@asynccontextmanager
async def transaction():
    yield


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant", ["confirmed", "empty", "unavailable", "other_season", "other_tenant", "mirror"]
)
async def test_archived_season_uses_owner_after_cutover(monkeypatch, variant):
    row = {
        "crops": ["wheat"],
        "cultivar": "الحبيب",
        "sowing_date": START,
        "season_end": END,
        "status": "closed",
    }

    async def fetchrow(sql, *args):
        if "FROM seasons" in sql:
            assert args == ("s1", "pivot", TENANT)
            return row
        assert "FROM water_ledger" in sql and args == (TENANT, "pivot", END, START)
        return {"d7": None, "d14": None}

    conn = SimpleNamespace(transaction=transaction, fetchrow=fetchrow)

    @asynccontextmanager
    async def session(_):
        yield conn

    monkeypatch.setattr(seasons, "tenant_connection", session)
    monkeypatch.setattr(
        decision_sor_mode,
        "get_platform_decision_sor_mode",
        lambda: SimpleNamespace(platform_writes_required=False),
    )
    monkeypatch.setattr(seasons, "_season_state_scene", AsyncMock(return_value={}))
    payload = {
        "tenant_id": TENANT,
        "field_id": "pivot",
        "season_id": "s1",
        "authoritative": True,
        "outcome_records": [],
        "recommendation_outcomes": [],
    }
    if variant == "confirmed":
        payload["outcome_records"] = [
            {"outcome_id": "o", "tenant_id": TENANT, "field_id": "pivot", "success": False}
        ]
    if variant == "other_season":
        payload["season_id"] = "s2"
    if variant == "other_tenant":
        payload["outcome_records"] = [
            {"tenant_id": "another", "field_id": "pivot", "success": True}
        ]
    if variant == "mirror":
        payload["authoritative"] = False
    caller = AsyncMock(
        side_effect=HTTPException(503) if variant == "unavailable" else None, return_value=payload
    )
    monkeypatch.setattr(decision_service_client, "decision_get_json", caller)
    result = await seasons.field_season_state_endpoint(
        "pivot", "s1", SimpleNamespace(tenant_id=TENANT)
    )
    caller.assert_awaited_once_with(
        "/v1/outcomes/reconciled",
        tenant_id=TENANT,
        params={"field_id": "pivot", "season_id": "s1", "season_inputs": "true"},
    )
    assert result["days_after_sowing"] == (END - START).days
    assert result["open_operations"] is None
    assert result["water_deficit_7d_mm"] is None
    summary = result["outcome_reconciliation"]
    assert summary["available"] == (variant in ("confirmed", "empty"))
    assert summary["total"] == {"confirmed": 1, "empty": 0}.get(variant)
    assert summary["success_rate"] == (0.0 if variant == "confirmed" else None)


@pytest.mark.asyncio
async def test_local_schema_missing_water_rolls_back_savepoint_and_retains_outcomes(monkeypatch):
    row = {
        "crops": ["wheat"],
        "cultivar": None,
        "sowing_date": START,
        "season_end": END,
        "status": "closed",
    }
    recovered = False
    active = False

    @asynccontextmanager
    async def savepoint():
        nonlocal recovered, active
        active = True
        try:
            yield
        except LookupError:
            recovered = True
            raise
        finally:
            active = False

    async def fetchrow(query, *args):
        if "FROM seasons" in query:
            return row
        assert active and "water_ledger" in query
        raise LookupError("optional water table offline")

    async def fetch(query, *args):
        assert active and recovered
        if "FROM dispatch_decisions" in query:
            assert args == (TENANT, "pivot", ["r"])
            return []
        assert args == (TENANT, "pivot", "s1")
        if "FROM outcome_record" in query:
            return [{"decision_id": "d", "success": False}]
        return [
            {
                "recommendation_id": "r",
                "tenant_id": TENANT,
                "field_id": "pivot",
                "farm_id": "farm",
                "season_id": "s1",
                "predicted_yield_t_ha": 2.0,
                "actual_yield_t_ha": 3.0,
                "accepted": True,
                "matured_within_lag": False,
            }
        ]

    @asynccontextmanager
    async def session(_):
        yield SimpleNamespace(fetchrow=fetchrow, fetch=fetch, transaction=savepoint)

    monkeypatch.setattr(seasons, "tenant_connection", session)
    monkeypatch.setattr(seasons, "_season_state_scene", AsyncMock(return_value={}))
    monkeypatch.setattr(
        decision_sor_mode,
        "get_platform_decision_sor_mode",
        lambda: SimpleNamespace(platform_writes_required=True),
    )
    result = await seasons.field_season_state_endpoint(
        "pivot", "s1", SimpleNamespace(tenant_id=TENANT)
    )
    assert result["water_deficit_7d_mm"] is None
    summary = result["outcome_reconciliation"]
    assert (summary["source"], summary["failed"], summary["pending"]) == ("platform", 1, 1)


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
