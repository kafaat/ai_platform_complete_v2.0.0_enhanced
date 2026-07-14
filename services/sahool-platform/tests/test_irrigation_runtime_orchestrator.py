from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from api import irrigation_runtime_orchestrator as mod

D = hashlib.sha256(b"x").hexdigest()


class FakeConn:
    def __init__(self):
        self.executed = []

    async def fetchrow(self, sql, *args):
        if "canonical_irrigation_capability_graphs" in sql:
            now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            return {
                "payload": {
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
                },
                "capability_digest": D,
                "status": "verified",
                "operational_eligible": True,
            }
        if "irrigation_executability_gates" in sql:
            return {
                "snapshot": {},
                "execution_allowed": True,
                "valid_until": datetime.now(UTC) + timedelta(days=1),
                "blocking_reasons": [],
                "executability_digest": D,
                "commissioning_certification_digest": D,
            }
        if "INSERT INTO hourly_irrigation_mpc_schedules" in sql:
            return {"schedule_id": "00000000-0000-0000-0000-000000000001"}
        return None

    async def fetchval(self, sql, *args):
        return 50.0

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_server_owned_orchestrator_builds_and_persists(monkeypatch):
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
        FakeConn(), tenant_id="t1", field_id="f1", horizon_hours=24
    )
    assert out["mode"] == "operational"
    assert out["facts_source"] == "server_owned_canonical_truth"
    assert out["execution_allowed"] is False
    assert out["persistence_status"] == "persisted"
    assert len(out["orchestration_digest"]) == 64


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
