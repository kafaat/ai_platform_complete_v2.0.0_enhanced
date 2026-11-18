"""POST and replay real append-only weather rows under two tenant identities."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def test_weather_history_reaches_replay_with_postgres_rls(monkeypatch):
    # CI invokes this gate separately with the restricted application DSN. Dependencies,
    # schema, permissions, or connection failures in that step must fail this test.
    if os.getenv("WEATHER_REPLAY_CERTIFICATION_REQUIRED") != "1":
        pytest.skip("requires the restricted-role weather replay certification step")
    asyncio.run(_exercise_http(monkeypatch, os.environ["TEST_DATABASE_URL"]))


async def _exercise_http(monkeypatch, dsn):
    import asyncpg
    import httpx
    from api import main, raster_service_client
    from core.canonical_schemas import UserRole, UserSchema

    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        assert await conn.fetchval(
            "SELECT NOT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname = current_user"
        ), "weather replay requires a restricted application role"
        assert await conn.fetchval("SELECT row_security_active('historical_weather_daily')")
        assert await conn.fetchval("SELECT row_security_active('fields')")

        # The normal tenant_connection transaction runs as a nested transaction on this
        # connection. One outer rollback removes both tenants' append-only test records.
        class TestPool:
            @asynccontextmanager
            async def acquire(self):
                yield conn

        monkeypatch.setattr(main, "_DB_POOL", TestPool())
        monkeypatch.setenv("FEATURE_REPLAY_MAP", "1")
        monkeypatch.setattr(
            raster_service_client, "get_field_timeseries", AsyncMock(return_value=[])
        )

        users = [
            UserSchema(
                user_id=uuid4().hex, tenant_id=str(uuid4()), role=UserRole.OWNER, name_ar="مالك"
            )
            for _ in range(2)
        ]
        fields = [f"wr-{uuid4().hex}" for _ in users]
        values = [(31, -2, 0), (26, 12, 3)]
        acting = users[0]
        monkeypatch.setitem(main.app.dependency_overrides, main.get_current_user, lambda: acting)
        outer = conn.transaction()
        await outer.start()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app), base_url="http://platform"
            ) as client:
                for acting, field, (high, low, rain) in zip(users, fields, values, strict=True):
                    async with main.tenant_connection(acting) as scoped:
                        await scoped.execute(
                            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
                            field,
                            str(acting.tenant_id),
                        )
                    response = await client.post(
                        "/api/v1/weather/history/records",
                        json={
                            "source_record_id": "observation-1",
                            "field_id": field,
                            "observed_on": "2025-05-01",
                            "available_at": "2025-05-02T10:00:00Z",
                            "source": "test-station",
                            "payload": {"tmax_c": high, "tmin_c": low, "precipitation_mm": rain},
                        },
                    )
                    assert response.status_code == 201, response.text
                    assert response.json()["persisted"] is True

                for idx, acting in enumerate(users):
                    high, low, rain = values[idx]
                    for target, own in ((fields[idx], True), (fields[1 - idx], False)):
                        response = await client.get(f"/api/v1/fields/{target}/agronomic-replay")
                        assert response.status_code == 200, response.text
                        replay = response.json()
                        assert replay["tenant_id"] == str(acting.tenant_id)
                        weather = [
                            event for event in replay["events"] if event["track"] == "weather"
                        ]
                        assert (
                            replay["source_status"]["weather"]["source"]
                            == "historical_weather_daily"
                        )
                        assert replay["source_status"]["weather"]["status"] == (
                            "available" if own else "empty"
                        )
                        assert replay["source_status"]["weather"]["count"] == (1 if own else 0)
                        if own:
                            assert [event["date"] for event in weather] == ["2025-05-01"]
                            assert weather[0]["value"] == {
                                "t_max": high,
                                "t_min": low,
                                "rain_mm": rain,
                            }
                        else:
                            assert weather == []
        finally:
            await outer.rollback()
    finally:
        await conn.close()
