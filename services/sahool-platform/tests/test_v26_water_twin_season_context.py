"""Active season owns the crop used to interpret a water-twin scenario."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import api.main as main
import api.routers.water_twin as router
import pytest
from api.routers.water_twin import FieldWaterTwinRequest
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

USER = UserSchema(
    user_id="u-water-twin",
    tenant_id="00000000-0000-0000-0000-000000000003",
    role=UserRole.OWNER,
    name_ar="Water Twin tester",
)


@pytest.mark.asyncio
async def test_water_twin_active_season_wins_over_legacy_field_crop(monkeypatch):
    class FakeConn:
        async def fetchrow(self, sql, *args):
            if "FROM fields" in sql:
                return {"crop": "peanut", "planting_date": date(2026, 1, 1)}
            if "FROM seasons" in sql:
                return {
                    "season_id": "season-wheat",
                    "crops": ["wheat"],
                    "sowing_date": date(2026, 10, 20),
                }
            raise AssertionError(sql)

        async def fetch(self, sql, *args):
            assert "FROM water_ledger" in sql
            return []

    @asynccontextmanager
    async def fake_connection(user):
        yield FakeConn()

    async def allow_field(conn, field_id):
        return None

    async def no_sensor(conn, field_id):
        return None

    monkeypatch.setattr(main, "_DB_POOL", object())
    monkeypatch.setattr(main, "_latest_soil_moisture", no_sensor)
    monkeypatch.setattr(router, "tenant_connection", fake_connection)
    monkeypatch.setattr(router, "_assert_field_in_tenant", allow_field)

    req = FieldWaterTwinRequest(
        taw_mm=100,
        raw_mm=50,
        initial_depletion_mm=30,
        daily_etc_mm=4,
        horizon_days=2,
    )
    out = await router.field_water_twin(req=req, field_id="f1", user=USER)
    assert out["season_context"]["season_id"] == "season-wheat"
    assert out["season_context"]["crop"] == "wheat"
    assert out["season_context"]["source"] == "seasons.active"
    assert out["preview_only"] is True
    assert out["season_context"]["decision_authority"] == "none"
