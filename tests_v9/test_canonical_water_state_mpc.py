import asyncio
from contextlib import asynccontextmanager
from datetime import date
from importlib.util import find_spec

import pytest


class Row(dict):
    __getattr__ = dict.__getitem__


class FakeConn:
    def __init__(self, *, ledger=True, soil=True):
        self.ledger = ledger
        self.soil = soil

    async def fetchrow(self, sql, *args):
        if "SELECT lat, lon, crop FROM fields" in sql:
            return Row(lat=15.5, lon=44.2, crop="maize")
        if "SELECT crops, sowing_date FROM seasons" in sql:
            return Row(crops=["maize"], sowing_date=date.today())
        if "SELECT season_id, sowing_date, crops FROM seasons" in sql:
            return Row(season_id="sea-1", sowing_date=date.today(), crops=["maize"])
        if "FROM water_ledger" in sql:
            return (
                Row(
                    ledger_date=date.today(),
                    depletion_mm=20.0,
                    confidence=0.9,
                    et0_mm=5.0,
                    kc=0.4,
                    etc_mm=2.0,
                    rain_mm=0.0,
                )
                if self.ledger
                else None
            )
        if "FROM soil_lab_tests" in sql:
            return Row(result={"texture": "loam"}, sampled_on=date.today()) if self.soil else None
        raise AssertionError(sql)


@pytest.fixture
def canonical_patches(monkeypatch):
    import api.canonical_water_state as c

    async def forecast(*args, **kwargs):
        n = kwargs["days"]
        return {
            "source": "weather-engine",
            "days": [
                {
                    "date": f"2026-07-{i + 1:02d}",
                    "temp_min_c": 18,
                    "temp_max_c": 32,
                    "precipitation_mm": 0,
                    "solar_radiation_mj_m2": 24,
                    "wind_max_ms": 3,
                }
                for i in range(n)
            ],
        }

    async def et0(**kwargs):
        return {"daily_et0_mm": [6.0] * len(kwargs["daily_t_min"])}

    monkeypatch.setattr(c, "get_weather_forecast", forecast)
    monkeypatch.setattr(c, "get_et0_series", et0)

    async def root_zone(*args, **kwargs):
        from api.canonical_root_zone_profile import CanonicalRootZoneProfile

        return CanonicalRootZoneProfile(
            schema_version="canonical_root_zone_profile.v1",
            product_version="root-zone-hydraulics/1.0.0",
            tenant_id="tenant-1",
            field_id="fld-1",
            season_id="sea-1",
            crop="maize",
            root_policy_id="rp-1",
            root_policy_version="maize-roots.v1",
            soil_hydraulic_profile_id="shp-1",
            source_soil_profile_hash="soil-hash",
            generated_at="2026-07-13T00:00:00+00:00",
            effective_at="2026-07-13T00:00:00+00:00",
            root_depth_m=0.6,
            effective_root_zone_m=0.48,
            taw_mm=100.0,
            raw_fraction=0.5,
            raw_mm=50.0,
            field_capacity_weighted=0.30,
            wilting_point_weighted=0.12,
            available_water_capacity_weighted=0.18,
            infiltration_mm_h=12.0,
            ksat_mm_h=20.0,
            soil_ec_ds_m=1.2,
            layer_contributions=[],
            evidence={},
            quality_status="verified",
            operational_eligible=True,
            limitations=[],
            profile_digest="c" * 64,
        )

    monkeypatch.setattr(c, "resolve_canonical_root_zone_profile", root_zone)


def test_canonical_state_uses_server_truth_and_digests(canonical_patches):
    from api.canonical_water_state import resolve_canonical_water_state

    out = asyncio.run(
        resolve_canonical_water_state(
            FakeConn(), tenant_id="tenant-1", field_id="fld-1", horizon_days=3
        )
    )
    assert out.operational_eligible is True
    assert out.depletion_mm == 20.0
    assert out.soil_texture == "governed_hydraulic_profile"
    assert len(out.forecast) == 3
    assert len(out.water_state_digest) == 64
    assert len(out.weather_snapshot_digest) == 64


def test_canonical_state_blocks_without_ledger(canonical_patches):
    from api.canonical_water_state import resolve_canonical_water_state

    out = asyncio.run(
        resolve_canonical_water_state(
            FakeConn(ledger=False), tenant_id="tenant-1", field_id="fld-1"
        )
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "no_ground_truth_depletion"


def test_canonical_state_blocks_without_root_zone(monkeypatch, canonical_patches):
    import api.canonical_water_state as c
    from api.canonical_water_state import resolve_canonical_water_state

    async def blocked(*args, **kwargs):
        return {"status": "blocked", "reason": "governed_soil_hydraulic_profile_missing"}

    monkeypatch.setattr(c, "resolve_canonical_root_zone_profile", blocked)
    out = asyncio.run(
        resolve_canonical_water_state(
            FakeConn(), tenant_id="tenant-1", field_id="fld-1", horizon_days=2
        )
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "governed_soil_hydraulic_profile_missing"


@pytest.mark.skip(
    reason="V21 integration: the canonical_water_state→MPC route wiring "
    "(resolve_canonical_water_state + MpcRecommendationRequest + source_digests trace) belongs to "
    "the zip's divergent P1.1c router, which was NOT adopted — the landed branch keeps its own "
    "server-authoritative P1.1c-b router (facts_provenance). The canonical_water_state kernel and "
    "its module-level truth/fail-closed/digest tests above are integrated and pass; only this "
    "route-level wiring is deferred, matching the forensic P0-2/P0-C finding that these kernels are "
    "not yet mounted into a production read path."
)
def test_operational_route_carries_source_digests(monkeypatch):
    import api.routers.irrigation_mpc as route
    from api.canonical_water_state import CanonicalWaterState

    state = CanonicalWaterState(
        schema_version="canonical_water_state.v1",
        tenant_id="tenant-42",
        field_id="fld-a",
        season_id="sea-1",
        crop="maize",
        growth_stage="initial",
        depletion_mm=20,
        depletion_confidence=0.9,
        ledger_date="2026-07-13",
        ledger_age_hours=2,
        taw_mm=100,
        raw_fraction=0.5,
        raw_mm=50,
        root_depth_m=0.6,
        soil_texture="loam",
        forecast=[{"et0_mm": 6, "kc": 0.4, "rain_mm": 0, "runoff_mm": 0}],
        evidence={},
        quality_status="verified",
        operational_eligible=True,
        limitations=[],
        water_state_digest="a" * 64,
        weather_snapshot_digest="b" * 64,
        soil_profile_digest="c" * 64,
        season_state_digest="d" * 64,
    )

    async def resolver(*args, **kwargs):
        return state

    monkeypatch.setattr(route, "resolve_canonical_water_state", resolver)

    @asynccontextmanager
    async def tc(*args, **kwargs):
        yield object()

    monkeypatch.setattr(route, "tenant_connection", tc)

    class U:
        tenant_id = "tenant-42"

    req = route.MpcRecommendationRequest(horizon_days=1)
    out = asyncio.run(route.irrigation_mpc_recommendation("fld-a", req, user=U()))
    trace = out["decision"]["constraint_trace"]
    assert trace["source_digests"]["water_state_digest"] == "a" * 64
    assert out["mode"] == "operational"


# canonical_water_state transitively imports platform runtime modules (field_context /
# weather_service_client) that require fastapi. The root "Unit Tests" CI job runs pure-logic
# tests_v9 without fastapi installed, so skip this module there (same precedent as the MPC
# route tests). It still runs anywhere fastapi is present.
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(find_spec("fastapi") is None, reason="requires fastapi (platform runtime)"),
]
