from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from api import irrigation_runtime_orchestrator as mod
from httpx import ASGITransport, AsyncClient

D = hashlib.sha256(b"x").hexdigest()


class FakeConn:
    def __init__(self, *, jsonb_text=False):
        self.executed = []
        self.jsonb_text = jsonb_text

    def jsonb(self, value):
        return json.dumps(value) if self.jsonb_text else value

    async def fetchrow(self, sql, *args):
        if "canonical_irrigation_capability_graphs" in sql:
            now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            return {
                "payload": self.jsonb(
                    {
                        "status": "verified",
                        "operational_eligible": True,
                        "maximum_flow_lps": 40.0,
                        "maximum_daily_depth_mm": 20.0,
                        "maximum_safe_depth_mm_event": 10.0,
                        "specific_energy_kwh_m3": 0.3,
                        "pump_starting_kva": 30.0,
                        "required_energy_load_ids": ["pump"],
                        "hourly_operating_windows": [
                            {
                                "hour": (now + timedelta(hours=i)).isoformat(),
                                "maximum_available_power_kw": 80.0,
                                "maximum_starting_kva": 100.0,
                                "energy_cost_per_kwh": 0.1,
                                "renewable_fraction": 0.8,
                                "permitted_load_ids": ["pump"],
                            }
                            for i in range(24)
                        ],
                    }
                ),
                "well_id": None,
                "capability_digest": D,
                "status": "verified",
                "operational_eligible": True,
            }
        if "irrigation_executability_gates" in sql:
            return {
                "snapshot": self.jsonb({}),
                "execution_allowed": True,
                "valid_until": datetime.now(UTC) + timedelta(days=1),
                "blocking_reasons": self.jsonb([]),
                "executability_digest": D,
                "commissioning_certification_digest": D,
            }
        if "INSERT INTO hourly_irrigation_mpc_schedules" in sql:
            return {"schedule_id": "00000000-0000-0000-0000-000000000001"}
        return None

    async def fetchval(self, sql, *args):
        if "field_irrigation_source_assignments" in sql:
            return False
        return 50.0

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"


@pytest.mark.asyncio
@pytest.mark.parametrize("jsonb_text", [False, True], ids=["codec", "asyncpg-default"])
async def test_server_owned_orchestrator_builds_and_persists(monkeypatch, jsonb_text):
    now = datetime.now(UTC).date().isoformat()

    async def fake_water(*args, **kwargs):
        return {
            "tenant_id": "t1",
            "field_id": "f1",
            "season_id": "s1",
            "depletion_mm": 80.0,
            "taw_mm": 120.0,
            "raw_mm": 60.0,
            "operational_eligible": True,
            "water_state_digest": D,
            "weather_snapshot_digest": D,
            "soil_profile_digest": D,
            "season_state_digest": D,
            "evidence": {"location": {"lat": 15.0, "lon": 44.0}},
            "forecast": [{"date": now, "et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0}],
        }

    async def fake_hourly(**kwargs):
        start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        hours = []
        for i in range(24):
            hour = (start + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
            hours.append(
                {
                    "hour": hour,
                    "et0_mm": 0.25,
                    "kc": 1.0,
                    "etc_mm": 0.25,
                    "effective_rain_mm": 0.0,
                    "net_crop_demand_mm": 0.25,
                    "content_digest": D,
                }
            )
        return {
            "status": "verified",
            "quality_status": "provider_native",
            "content_digest": D,
            "hours": hours,
        }

    monkeypatch.setattr(mod, "resolve_canonical_water_state", fake_water)
    monkeypatch.setattr(mod, "get_hourly_etc_product", fake_hourly)
    out = await mod.orchestrate_irrigation_recommendation(
        FakeConn(jsonb_text=jsonb_text), tenant_id="t1", field_id="f1", horizon_hours=24
    )
    assert out["mode"] == "operational"
    assert out["facts_source"] == "server_owned_canonical_truth"
    assert out["execution_allowed"] is False
    assert out["persistence_status"] == "persisted"
    assert len(out["orchestration_digest"]) == 64


@pytest.mark.parametrize(
    "column,bad",
    [
        ("payload", "[]"),
        ("payload", "null"),
        ("payload", "{"),
        ("snapshot", "[]"),
        ("snapshot", "null"),
        ("snapshot", "{"),
        ("blocking_reasons", '"EXPIRED"'),
        ("blocking_reasons", "{}"),
        ("blocking_reasons", "[1]"),
        ("blocking_reasons", "{"),
    ],
)
def test_invalid_persisted_jsonb_blocks_at_http_boundary(monkeypatch, column, bad):
    from api.routers import irrigation_mpc as route
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    class InvalidConn(FakeConn):
        async def fetchrow(self, sql, *args):
            row = await super().fetchrow(sql, *args)
            if row is not None and column in row:
                row[column] = bad
            return row

    conn = InvalidConn(jsonb_text=True)

    @asynccontextmanager
    async def tenant_connection(user):
        yield conn

    monkeypatch.setattr(route, "tenant_connection", tenant_connection)
    monkeypatch.setattr(route, "_field_belongs_to_tenant", AsyncMock(return_value=True))
    monkeypatch.setattr(
        mod, "resolve_canonical_water_state", AsyncMock(return_value={"season_id": "s1"})
    )
    hourly = AsyncMock(side_effect=AssertionError("invalid evidence must stop before weather"))
    monkeypatch.setattr(mod, "get_hourly_etc_product", hourly)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user] = lambda: type(
        "User", (), {"tenant_id": "t1"}
    )()
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/fields/f1/irrigation/mpc/hourly-recommendation", json={"persist": False}
    )
    assert response.status_code == 200
    out = response.json()
    assert out["status"] == "blocked"
    # حجبٌ واحد يُسمّي **العمود** لا المصدر وحدَه: من يقرأ الحمولة يعرف أيّ عمودٍ يُصلح.
    assert out["reason"] == "canonical_runtime_row_malformed"
    assert out["missing"] == [
        {
            "payload": "canonical_irrigation_capability_graphs.payload",
            "snapshot": "irrigation_executability_gates.snapshot",
            "blocking_reasons": "irrigation_executability_gates.blocking_reasons",
        }[column]
    ]
    assert out["execution_allowed"] is False
    hourly.assert_not_awaited()
    assert conn.executed == []


@pytest.mark.asyncio
async def test_gate_decodes_blocking_reasons_without_splitting_characters():
    class BlockedConn(FakeConn):
        async def fetchrow(self, sql, *args):
            row = await super().fetchrow(sql, *args)
            row.update(execution_allowed=False, blocking_reasons='["NOT_CERTIFIED"]')
            return row

    gate = await mod._latest_executability_gate(
        BlockedConn(jsonb_text=True), field_id="f1", season_id="s1", capability_digest=D
    )
    assert gate["blocking_reasons"] == ["NOT_CERTIFIED"]
    assert gate["execution_allowed"] is False


@pytest.mark.asyncio
async def test_orchestrator_fails_closed_without_capability(monkeypatch):
    async def fake_water(*args, **kwargs):
        return {
            "tenant_id": "t1",
            "field_id": "f1",
            "season_id": "s1",
            "depletion_mm": 10.0,
            "taw_mm": 100.0,
            "raw_mm": 50.0,
            "operational_eligible": True,
            "water_state_digest": D,
            "weather_snapshot_digest": D,
            "soil_profile_digest": D,
            "season_state_digest": D,
            "forecast": [],
        }

    class NoCap(FakeConn):
        async def fetchrow(self, sql, *args):
            if "canonical_irrigation_capability_graphs" in sql:
                return None
            return await super().fetchrow(sql, *args)

    monkeypatch.setattr(mod, "resolve_canonical_water_state", fake_water)
    out = await mod.orchestrate_irrigation_recommendation(
        NoCap(), tenant_id="t1", field_id="f1", persist=False
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "canonical_irrigation_capability_graph_missing"


@pytest.mark.asyncio
async def test_well_fk_on_old_graph_blocks_even_when_payload_omits_the_well(monkeypatch):
    class WellGraph(FakeConn):
        async def fetchrow(self, sql, *args):
            row = await super().fetchrow(sql, *args)
            if "canonical_irrigation_capability_graphs" in sql:
                row["well_id"] = "old-well"
            return row

    conn = WellGraph()
    monkeypatch.setattr(
        mod, "resolve_canonical_water_state", AsyncMock(return_value={"season_id": "s1"})
    )
    result = await mod.orchestrate_irrigation_recommendation(
        conn, tenant_id="t1", field_id="f1", persist=True
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "AQUIFER_ALLOCATION_UNVERIFIED"
    assert result["execution_allowed"] is False
    assert conn.executed == []


# ASGI policy regression for the daily consumer of a persisted well graph.
# Router, canonical-water resolver, daily solver, and governed bridge are real.
# Database transport, authentication, weather/root-profile providers, and decision
# transport are synthetic; these cases do not certify PostgreSQL/RLS or JWT.
_AQUIFER_TEST_TENANT = "11111111-1111-4111-8111-111111111111"
_AQUIFER_TEST_FIELD = "synthetic-pivot"
_AQUIFER_TEST_SEASON = "synthetic-current-season"


class _AquiferSnapshotConnection:
    """Transport double with a persisted well graph and absent/expired bindings."""

    def __init__(self, binding_state: str, graph_season: str | None):
        self.binding_state = binding_state
        self.graph_season = graph_season
        self.queries: list[str] = []
        self.writes: list[str] = []
        now = datetime.now(UTC)
        self.bindings = (
            []
            if binding_state == "absent"
            else [
                {
                    "tenant_id": _AQUIFER_TEST_TENANT,
                    "field_id": _AQUIFER_TEST_FIELD,
                    "source_type": "well",
                    "status": "active",
                    "valid_from": now - timedelta(days=7),
                    "valid_to": now - timedelta(days=1),
                }
            ]
        )

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        if "field_irrigation_source_assignments" in sql:
            field, now = args
            return [
                row
                for row in self.bindings
                if row["field_id"] == field
                and row["status"] == "active"
                and row["valid_from"] <= now < row["valid_to"]
            ]
        raise AssertionError(f"Unexpected fetch: {sql}")

    async def fetchval(self, sql, *args):
        self.queries.append(sql)
        if "field_irrigation_source_assignments" in sql:
            field, start, end, tenant = args
            assert tenant == _AQUIFER_TEST_TENANT
            return any(
                row["tenant_id"] == tenant
                and row["field_id"] == field
                and row["status"] == "active"
                and row["source_type"] == "well"
                and row["valid_from"] < end
                and row["valid_to"] > start
                for row in self.bindings
            )
        if "canonical_irrigation_capability_graphs" in sql:
            # The proposed query scopes the current persisted graph to tenant,
            # field, and season. A real PG fixture is a separate acceptance gate.
            return self.graph_season is not None and tuple(args) == (
                _AQUIFER_TEST_TENANT,
                _AQUIFER_TEST_FIELD,
                self.graph_season,
            )
        if "elevation_m" in sql:
            return 400.0
        if "area_ha" in sql:
            return 50.0
        if "cultivar" in sql:
            return "synthetic-wheat-variety"
        raise AssertionError(f"Unexpected fetchval: {sql}")

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        if "SELECT 1 FROM fields" in sql:
            return {"exists": 1}
        if "FROM seasons" in sql:
            return {
                "season_id": _AQUIFER_TEST_SEASON,
                "sowing_date": datetime.now(UTC).date() - timedelta(days=60),
                "crops": ["wheat"],
                "cultivar": "synthetic-wheat-variety",
            }
        if "FROM water_ledger" in sql:
            return {
                "ledger_date": datetime.now(UTC).date(),
                "depletion_mm": 80.0,
                "confidence": 0.95,
                "et0_mm": 5.0,
                "kc": 1.0,
                "etc_mm": 5.0,
                "rain_mm": 0.0,
            }
        if "canonical_irrigation_capability_graphs" in sql:
            if self.graph_season != _AQUIFER_TEST_SEASON:
                return None
            return {
                "well_id": "22222222-2222-4222-8222-222222222222",
                "payload": {"status": "verified", "operational_eligible": True},
                "capability_digest": "a" * 64,
                "status": "verified",
                "operational_eligible": True,
            }
        if "irrigation_executability_gates" in sql:
            return {
                "snapshot": {},
                "valid_until": datetime.now(UTC) + timedelta(days=1),
                "execution_allowed": True,
                "blocking_reasons": [],
                "executability_digest": "b" * 64,
                "commissioning_certification_digest": "c" * 64,
            }
        raise AssertionError(f"Unexpected fetchrow: {sql}")

    async def execute(self, sql, *args):
        self.writes.append(sql)
        raise AssertionError("An unverified well must not persist an hourly schedule")


@pytest.fixture
def aquifer_snapshot_harness(monkeypatch):
    from api import canonical_water_state as water
    from api import decision_service_client as decisions
    from api.routers import irrigation_mpc as route
    from fastapi import FastAPI

    async def make(binding_state, graph_season=_AQUIFER_TEST_SEASON):
        conn = _AquiferSnapshotConnection(binding_state, graph_season)

        @asynccontextmanager
        async def tenant_connection(user):
            assert user.tenant_id == _AQUIFER_TEST_TENANT
            yield conn

        async def forecast(lat, lon, *, days):
            return {
                "timezone": "UTC",
                "source": "synthetic-weather-provider",
                "days": [
                    {
                        "date": (datetime.now(UTC).date() + timedelta(days=i)).isoformat(),
                        "temp_min_c": 15.0,
                        "temp_max_c": 28.0,
                        "precipitation_mm": 0.0,
                    }
                    for i in range(days)
                ],
            }

        async def et0(**kwargs):
            n = len(kwargs["daily_dates"])
            return {"daily_et0_mm": [5.0] * n, "methods": ["fao56_pm"] * n}

        monkeypatch.setattr(route, "tenant_connection", tenant_connection)
        monkeypatch.setattr(
            water,
            "_field_weather_context",
            AsyncMock(return_value=(15.0, 44.0, "wheat", "mid_season", 60)),
        )
        monkeypatch.setattr(
            water,
            "resolve_canonical_root_zone_profile",
            AsyncMock(
                return_value=SimpleNamespace(
                    taw_mm=120.0,
                    raw_fraction=0.5,
                    raw_mm=60.0,
                    root_depth_m=1.0,
                    operational_eligible=True,
                    limitations=[],
                    soil_hydraulic_profile_id="synthetic-soil",
                    profile_digest="d" * 64,
                    root_policy_version="synthetic-policy",
                    quality_status="verified",
                    evidence={},
                )
            ),
        )
        monkeypatch.setattr(water, "get_weather_forecast", forecast)
        monkeypatch.setattr(water, "get_et0_series", et0)
        monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "1")
        lineage = AsyncMock(return_value={"status": "synthetic_lineage_boundary"})
        submission = AsyncMock(return_value={"status": "observed_stub_transport"})
        monkeypatch.setattr(decisions, "governed_candidate_lineage", lineage)
        monkeypatch.setattr(decisions, "submit_governed_candidate", submission)
        app = FastAPI()
        app.include_router(route.router)
        app.dependency_overrides[route.get_current_user] = lambda: SimpleNamespace(
            tenant_id=_AQUIFER_TEST_TENANT
        )
        return conn, app, submission

    return make


@pytest.mark.asyncio
@pytest.mark.parametrize("binding_state", ["absent", "expired"])
@pytest.mark.parametrize("submit", [False, True])
async def test_daily_known_well_blocks_even_without_active_assignment(
    aquifer_snapshot_harness, binding_state, submit
):
    conn, app, submission = await aquifer_snapshot_harness(binding_state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.post(
            f"/api/v1/fields/{_AQUIFER_TEST_FIELD}/irrigation/mpc/recommendation",
            json={"horizon_days": 1, "submit": submit},
        )
    result = response.json()
    assert response.status_code == 200
    assert result.get("status") == "blocked", result
    assert result["reason"] == "AQUIFER_ALLOCATION_UNVERIFIED"
    assert "decision" not in result
    submission.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("binding_state", ["absent", "expired"])
async def test_hourly_existing_guard_is_a_blocking_control(aquifer_snapshot_harness, binding_state):
    conn, app, submission = await aquifer_snapshot_harness(binding_state)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.post(
            f"/api/v1/fields/{_AQUIFER_TEST_FIELD}/irrigation/mpc/hourly-recommendation",
            json={"horizon_hours": 1, "persist": True},
        )
    assert response.status_code == 200
    assert response.json()["reason"] == "AQUIFER_ALLOCATION_UNVERIFIED"
    assert response.json()["execution_allowed"] is False
    assert conn.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("graph_season", [None, "a-different-season"])
async def test_daily_without_a_current_well_graph_retains_legacy_behavior(
    aquifer_snapshot_harness, graph_season
):
    conn, app, submission = await aquifer_snapshot_harness("absent", graph_season=graph_season)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.post(
            f"/api/v1/fields/{_AQUIFER_TEST_FIELD}/irrigation/mpc/recommendation",
            json={"horizon_days": 1, "submit": False},
        )
    assert response.status_code == 200
    assert response.json()["mode"] == "operational"
    assert "decision" in response.json()
    submission.assert_not_awaited()
