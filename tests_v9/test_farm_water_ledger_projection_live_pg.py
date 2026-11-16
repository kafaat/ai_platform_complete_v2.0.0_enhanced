"""W1-13 (finding water-5, manual part) — measured farm water reaches the daily water ledger, live PG.

Water a farmer measured in the farm operations ledger never reached ``water_ledger``: the FAO-56
balance read the day as "no irrigation recorded" and recommended watering a watered field.
Measured here on the migrated schema, with the real farm-ledger router under a NOSUPERUSER /
NOBYPASSRLS role and the real water-balance worker (only the weather service is stubbed):

1. acceptance: a 500 m3 metered water record on a completed operation on a 1 ha field writes
   50 mm of irrigation on that day, with ``irrigation_source='farm_ledger'``, the reporter, and
   the day left to the worker;
2. the worker then keeps that figure and computes the balance around it (W0-13 report path);
3. a second record on the same day makes the day's sum, never the same water twice;
4. nothing is projected, and the response says why, for planned work, a record without a volume,
   a field without an area, or a day a person's full entry owns;
5. a person's report written over a projection clears the source;
6. another tenant's operation on the field is 404 and changes nothing.

Run: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytestmark = [pytest.mark.integration]

_CERTIFICATION_REQUIRED = os.getenv("FARM_WATER_LEDGER_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "FARM_WATER_LEDGER_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL and "
        "TEST_DATABASE_URL: the job claims a certification with no database to certify on."
    )
pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL (live DB, restricted role)",
    )
)

_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
# The farm ledger dates actual work by the database's CURRENT_DATE and the worker its day by the
# ledger timezone; UTC on both keeps the two on the same calendar day whenever the test runs.
_TZ = "UTC"
_ET0_MM = 6.0


def _platform():
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    import api.main as main
    from api import phase_runtime_workers, weather_service_client
    from api.routers import farm_operations_ledger, water_ledger

    return main, farm_operations_ledger, water_ledger, phase_runtime_workers, weather_service_client


def _user(tenant: str, user_id: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id=user_id, tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير")


def _today() -> _dt.date:
    return _dt.datetime.now(ZoneInfo(_TZ)).date()


class Live:
    """Admin connection for seeding, measuring and the worker; a restricted pool for the routers."""

    def __init__(self, monkeypatch, *, area_ha: float | None = 1.0):
        self.mp = monkeypatch
        self.area_ha = area_ha
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        self.field_id = f"fw-ledger-{uuid.uuid4().hex[:10]}"
        self.season_id = f"fw-season-{uuid.uuid4().hex[:10]}"
        self.farmer = f"u-farmer-{uuid.uuid4().hex[:6]}"

    async def __aenter__(self):
        main, self.ops, self.ledger_router, self.workers, weather = _platform()
        self.admin = await asyncpg.connect(_ADMIN_DSN)
        self.admin_pool = await asyncpg.create_pool(_ADMIN_DSN, min_size=1, max_size=2)
        self.app_pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=2)
        role = await self.app_pool.fetchval("SELECT current_user")
        flags = await self.admin.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=$1", role
        )
        assert flags is not None and not flags["rolsuper"] and not flags["rolbypassrls"], (
            f"{role} bypasses RLS, so the router would not be measured under tenant isolation"
        )
        self.mp.setattr(main, "_DB_POOL", self.app_pool)
        self.mp.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")
        self.mp.setenv("WATER_LEDGER_AUTO_ENABLED", "1")
        self.mp.setenv("WATER_LEDGER_TIMEZONE", _TZ)
        self.mp.delenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", raising=False)

        async def forecast(lat, lon, days=2):
            return {
                "days": [
                    {
                        "date": _today().isoformat(),
                        "temp_max_c": 33.0,
                        "temp_min_c": 19.0,
                        "precipitation_mm": 0.0,
                    }
                ]
            }

        async def et0_product(**_kw):
            return {
                "et0_mm": _ET0_MM,
                "method": "fao56_penman_monteith",
                "quality_status": "validated",
            }

        self.mp.setattr(weather, "get_weather_forecast", forecast)
        self.mp.setattr(weather, "get_et0_product", et0_product)
        await self.admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, lat, lon, crop, elevation_m, area_ha)"
            " VALUES ($1, $1, $2::uuid, 15.35, 44.2, 'wheat', 2250, $3)",
            self.field_id,
            self.tenant,
            self.area_ha,
        )
        await self.admin.execute(
            "INSERT INTO seasons (season_id, tenant_id, field_id, crops, sowing_date, status)"
            " VALUES ($1, $2::uuid, $3, '[\"wheat\"]'::jsonb, $4, 'active')",
            self.season_id,
            self.tenant,
            self.field_id,
            _today() - _dt.timedelta(days=40),
        )
        # Yesterday's computed balance, so today's entry is not a bootstrap from field capacity.
        await self.admin.execute(
            "INSERT INTO water_ledger (tenant_id, field_id, ledger_date, depletion_mm, decision,"
            " confidence, created_by) VALUES ($1::uuid, $2, $3, 30.0, 'auto:daily_balance', 0.7,"
            " 'water-balance-auto')",
            self.tenant,
            self.field_id,
            _today() - _dt.timedelta(days=1),
        )
        return self

    async def __aexit__(self, *exc):
        try:
            async with self.admin.transaction():
                await self.admin.execute("SET LOCAL session_replication_role = replica")
                for table in (
                    "farm_water_records",
                    "farm_operation_ledger",
                    "water_ledger",
                    "seasons",
                    "fields",
                ):
                    await self.admin.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                        [self.tenant, self.other_tenant],
                    )
        finally:
            await self.app_pool.close()
            await self.admin_pool.close()
            await self.admin.close()

    async def operation(
        self,
        *,
        volume_m3: float | None = 500.0,
        hours: float | None = 3.0,
        status: str = "completed",
        tenant: str | None = None,
    ) -> dict:
        """The farm operations form: an irrigation operation with its water record."""
        req = self.ops.OperationLedgerIn(
            operation_date=_today(),
            operation_type="irrigation",
            field_id=self.field_id,
            status=status,
            water=self.ops.WaterRecordIn(
                well_id="well-1",
                hours_operated=hours,
                water_volume_m3=volume_m3,
                measurement_method="meter" if volume_m3 is not None else None,
            ),
        )
        return await self.ops.create_operation_ledger_record(
            req=req, user=_user(tenant or self.tenant, self.farmer), idem=None
        )

    async def worker(self) -> None:
        await self.workers.run_water_ledger_once(self.admin_pool)

    async def today_row(self):
        return await self.admin.fetchrow(
            "SELECT * FROM water_ledger WHERE field_id=$1 AND ledger_date=$2",
            self.field_id,
            _today(),
        )


async def test_500_m3_on_one_hectare_is_50_mm_of_irrigation_with_its_source(monkeypatch):
    async with Live(monkeypatch) as live:
        assert await live.today_row() is None, "the fixture must start without a ledger day"
        out = await live.operation(volume_m3=500.0)
        assert out["persisted"] is True, out
        projection = out.get("water_ledger")
        assert projection is not None and projection["status"] == "projected", (
            f"the response must say the water reached the ledger: {out}"
        )
        assert projection["irrigation_mm"] == pytest.approx(50.0), projection
        assert projection["source"] == "farm_ledger", projection

        row = await live.today_row()
        assert row is not None, "the measured farm water never reached the daily water ledger"
        assert row["irrigation_mm"] == pytest.approx(50.0), (
            f"500 m3 on 1 ha must be 50 mm in the ledger: {dict(row)}"
        )
        assert row["irrigation_source"] == "farm_ledger", f"source not recorded: {dict(row)}"
        assert row["irrigation_reported_by"] == live.farmer, (
            f"the reporter is what makes the worker keep the figure (W0-13): {dict(row)}"
        )
        assert row["created_by"] == "water-balance-auto", (
            f"the day stays the worker's, so the balance is still computed: {dict(row)}"
        )
        assert row["et0_mm"] is None and row["depletion_mm"] is None, (
            f"the projection must not invent a balance: {dict(row)}"
        )


async def test_the_worker_keeps_the_projected_water_and_computes_the_balance_around_it(
    monkeypatch,
):
    async with Live(monkeypatch, area_ha=2.5) as live:
        out = await live.operation(volume_m3=250.0)  # 250 m3 on 2.5 ha = 10 mm
        assert out["water_ledger"]["irrigation_mm"] == pytest.approx(10.0), out
        await live.worker()
        row = await live.today_row()
        assert row["et0_mm"] == _ET0_MM, f"the worker must compute a projected day: {dict(row)}"
        assert row["irrigation_mm"] == pytest.approx(10.0), (
            f"the worker overwrote the farm ledger's water with irrigation_runs: {dict(row)}"
        )
        assert row["irrigation_source"] == "farm_ledger", dict(row)
        assert "irrigation_unobserved" not in row["decision"], (
            f"a day with measured farm water is not unobserved: {row['decision']}"
        )
        etc = float(row["etc_mm"])
        assert row["depletion_mm"] == pytest.approx(max(30.0 + etc - 10.0, 0.0), abs=0.01), (
            f"depletion must be yesterday's 30 mm + ETc - the farm ledger's 10 mm: {dict(row)}"
        )


async def test_a_second_record_on_the_same_day_makes_the_days_sum(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.operation(volume_m3=500.0)
        out = await live.operation(volume_m3=250.0)
        assert out["water_ledger"]["irrigation_mm"] == pytest.approx(75.0), out
        row = await live.today_row()
        assert row["irrigation_mm"] == pytest.approx(75.0), (
            f"two records (500 + 250 m3 on 1 ha) must make 75 mm, counted once each: {dict(row)}"
        )


async def test_planned_work_is_not_applied_water(monkeypatch):
    async with Live(monkeypatch) as live:
        out = await live.operation(volume_m3=500.0, status="planned")
        assert out["water_ledger"] == {
            "ledger_date": _today().isoformat(),
            "source": "farm_ledger",
            "status": "skipped",
            "reason": "no_completed_water_record",
        }, out
        assert await live.today_row() is None, "planned water must not reach the ledger"


async def test_a_record_without_a_volume_is_not_read_as_zero(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.operation(volume_m3=500.0)
        out = await live.operation(volume_m3=None, hours=2.0)
        assert out["water_ledger"]["reason"] == "unmeasured_water_record", out
        row = await live.today_row()
        assert row["irrigation_mm"] == pytest.approx(50.0), (
            f"an unmeasured record must neither add a made-up amount nor erase the figure: "
            f"{dict(row)}"
        )


async def test_a_field_without_an_area_gets_no_invented_depth(monkeypatch):
    async with Live(monkeypatch, area_ha=None) as live:
        out = await live.operation(volume_m3=500.0)
        assert out["water_ledger"]["status"] == "skipped", out
        assert out["water_ledger"]["reason"] == "field_area_unknown", out
        assert await live.today_row() is None, "no area, no depth: nothing must be written"


async def test_a_persons_full_entry_keeps_its_day(monkeypatch):
    async with Live(monkeypatch) as live:
        req = live.ledger_router.WaterLedgerUpsertRequest(
            ledger_date=_today().isoformat(), et0_mm=5.0, depletion_mm=20.0, irrigation_mm=4.0
        )
        await live.ledger_router.upsert_water_ledger(
            req=req, field_id=live.field_id, user=_user(live.tenant, "u-agronomist")
        )
        before = dict(await live.today_row())
        out = await live.operation(volume_m3=500.0)
        assert out["persisted"] is True, out
        assert out["water_ledger"]["reason"] == "day_owned_by_another_writer", out
        assert dict(await live.today_row()) == before, (
            "the projection wrote over a day a person's full entry owns"
        )


async def test_a_persons_report_over_a_projection_clears_the_source(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.operation(volume_m3=500.0)
        req = live.ledger_router.WaterLedgerUpsertRequest(
            ledger_date=_today().isoformat(), irrigation_mm=12.0
        )
        await live.ledger_router.upsert_water_ledger(
            req=req, field_id=live.field_id, user=_user(live.tenant, live.farmer)
        )
        row = await live.today_row()
        assert (row["irrigation_mm"], row["irrigation_source"]) == (12.0, None), (
            f"the farm_ledger label must not stay on a figure the farm ledger did not write: "
            f"{dict(row)}"
        )


async def test_another_tenants_operation_is_404_and_changes_nothing(monkeypatch):
    from fastapi import HTTPException

    async with Live(monkeypatch) as live:
        await live.operation(volume_m3=500.0)
        before = dict(await live.today_row())
        with pytest.raises(HTTPException) as caught:
            await live.operation(volume_m3=9000.0, tenant=live.other_tenant)
        assert caught.value.status_code == 404, caught.value.detail
        assert dict(await live.today_row()) == before, "a foreign operation changed the ledger"
        foreign = await live.admin.fetchval(
            "SELECT count(*) FROM farm_water_records WHERE tenant_id=$1::uuid", live.other_tenant
        )
        assert foreign == 0, "the foreign operation's water record was stored"
