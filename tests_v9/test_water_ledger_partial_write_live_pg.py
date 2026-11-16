"""W0-13 (finding mobile-3) — a person's irrigation report keeps the worker's balance, live PG.

The mobile app logs the water a farmer applied with ``POST …/water-ledger``. Queued offline and
replayed after the water-balance worker wrote the day, the old full upsert wrote NULL over
``et0_mm``, ``depletion_mm``, ``deficit_mm`` and ``confidence``; and because a human write left
``created_by`` on the worker, the worker then wrote ``irrigation_runs``' sum over the farmer's
number. Measured here on the migrated schema, with the real router under a NOSUPERUSER /
NOBYPASSRLS role and the real worker (only the weather service is stubbed):

1. report first, then the worker, then the outbox replay: ET0 and depletion are not null, the
   reported 12 mm is the day's irrigation, and the balance was computed with it;
2. worker first, then the replay, then the worker again: the replay keeps the computed columns,
   and the next worker pass keeps 12 mm and recomputes depletion lower by exactly 12 mm;
3. negative control: the pre-fix SQL replayed on the same day writes NULL over ET0 and depletion;
4. a full manual entry is still the person's day: the worker skips it before and after a report,
   and a full entry posted onto a day a report opened (before the worker computed it) takes the
   day as it would have taken a new one;
5. an as-applied reconciliation written after a report keeps its day: the worker does not take
   it back (review finding on the first cut, where a reporter column outranked created_by);
6. a full entry that clears irrigation_mm on a worker day clears the reporter too, so the stored
   figure is the one the worker's balance uses;
7. another tenant's report on the field is 404 and changes nothing.

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

_CERTIFICATION_REQUIRED = os.getenv("WATER_LEDGER_PARTIAL_CERTIFICATION_REQUIRED") == "1"

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
        "WATER_LEDGER_PARTIAL_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL and "
        "TEST_DATABASE_URL: the job claims a certification with no database to certify on."
    )
pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="needs TEST_DATABASE_ADMIN_URL and TEST_DATABASE_URL (live DB, restricted role)",
    )
)

_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
_TZ = "Asia/Aden"
_ET0_MM = 6.0

# The as-applied ledger write of irrigation_closed_loop_runtime.reconcile (measured_as_applied),
# copied verbatim: it sets created_by and leaves irrigation_reported_by alone. The verified-manual
# as-applied write in routers/irrigation_engineering.py has the same shape.
_AS_APPLIED_UPSERT = """
        INSERT INTO water_ledger (
            tenant_id, field_id, ledger_date, irrigation_mm, depletion_mm,
            decision, created_by
        ) VALUES (
            current_setting('app.current_tenant')::uuid, $1, $2, $3, $4,
            'measured_as_applied', $5
        ) ON CONFLICT (field_id, ledger_date) DO UPDATE SET
            irrigation_mm = COALESCE(water_ledger.irrigation_mm, 0) + EXCLUDED.irrigation_mm,
            depletion_mm = EXCLUDED.depletion_mm,
            decision = EXCLUDED.decision,
            created_by = EXCLUDED.created_by,
            updated_at = now()
        """

# The upsert as it was before W0-13, kept verbatim for the negative control only.
_PRE_FIX_UPSERT = (
    "INSERT INTO water_ledger "
    "(tenant_id, field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm, "
    " irrigation_mm, soil_moisture_pct, depletion_mm, deficit_mm, "
    " stage, decision, confidence, created_by, created_at, updated_at) "
    "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
    " $13, $14, $15, now(), now()) "
    "ON CONFLICT (field_id, ledger_date) DO UPDATE SET "
    " et0_mm = EXCLUDED.et0_mm, kc = EXCLUDED.kc, etc_mm = EXCLUDED.etc_mm, "
    " rain_mm = EXCLUDED.rain_mm, irrigation_mm = EXCLUDED.irrigation_mm, "
    " soil_moisture_pct = EXCLUDED.soil_moisture_pct, "
    " depletion_mm = EXCLUDED.depletion_mm, deficit_mm = EXCLUDED.deficit_mm, "
    " stage = EXCLUDED.stage, decision = EXCLUDED.decision, "
    " confidence = EXCLUDED.confidence, updated_at = now()"
)


def _platform():
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    import api.main as main
    from api import phase_runtime_workers, weather_service_client
    from api.routers import water_ledger

    return main, water_ledger, phase_runtime_workers, weather_service_client


def _user(tenant: str, user_id: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id=user_id, tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير")


def _today() -> _dt.date:
    return _dt.datetime.now(ZoneInfo(_TZ)).date()


class Live:
    """Admin connection for seeding, measuring and the worker; a restricted pool for the router.

    The worker lists fields across tenants before binding each one's GUC, so it runs on the
    admin DSN, as the deployed worker runs on the owner. The router runs on the app role.
    """

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        self.field_id = f"wl-partial-{uuid.uuid4().hex[:10]}"
        self.season_id = f"wl-season-{uuid.uuid4().hex[:10]}"
        self.farmer = f"u-farmer-{uuid.uuid4().hex[:6]}"

    async def __aenter__(self):
        main, self.router, self.workers, weather = _platform()
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
            return {"et0_mm": _ET0_MM, "method": "hargreaves_samani"}

        self.mp.setattr(weather, "get_weather_forecast", forecast)
        self.mp.setattr(weather, "get_et0_product", et0_product)
        await self.admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, lat, lon, crop)"
            " VALUES ($1, $1, $2::uuid, 15.35, 44.2, 'wheat')",
            self.field_id,
            self.tenant,
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
                for table in ("water_ledger", "seasons", "fields"):
                    await self.admin.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                        [self.tenant, self.other_tenant],
                    )
        finally:
            await self.app_pool.close()
            await self.admin_pool.close()
            await self.admin.close()

    async def report(self, irrigation_mm: float, *, tenant: str | None = None):
        """The mobile client's body: the irrigation report alone."""
        req = self.router.WaterLedgerUpsertRequest(
            ledger_date=_today().isoformat(), irrigation_mm=irrigation_mm
        )
        return await self.router.upsert_water_ledger(
            req=req, field_id=self.field_id, user=_user(tenant or self.tenant, self.farmer)
        )

    async def post(self, **body):
        """A full (non-report) entry, as an API caller or an older client sends it."""
        req = self.router.WaterLedgerUpsertRequest(ledger_date=_today().isoformat(), **body)
        return await self.router.upsert_water_ledger(
            req=req, field_id=self.field_id, user=_user(self.tenant, self.farmer)
        )

    async def as_applied(self, applied_mm: float, depletion_after_mm: float, digest: str):
        async with self.app_pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", self.tenant)
            await conn.execute(
                _AS_APPLIED_UPSERT,
                self.field_id,
                _today(),
                applied_mm,
                depletion_after_mm,
                f"as_applied:{digest}",
            )

    async def worker(self) -> None:
        await self.workers.run_water_ledger_once(self.admin_pool)

    async def today_row(self):
        return await self.admin.fetchrow(
            "SELECT * FROM water_ledger WHERE field_id=$1 AND ledger_date=$2",
            self.field_id,
            _today(),
        )


async def test_report_first_then_worker_then_replay_keeps_et0_depletion_and_the_report(
    monkeypatch,
):
    async with Live(monkeypatch) as live:
        out = await live.report(12.0)
        assert out["persisted"] is True, out
        row = await live.today_row()
        assert row["irrigation_reported_by"] == live.farmer, dict(row)
        assert row["created_by"] == "water-balance-auto", (
            f"a report opens a day the worker owns, the reporter is in its own column: {dict(row)}"
        )
        assert row["et0_mm"] is None, "the report alone must not invent a balance"

        await live.worker()
        row = await live.today_row()
        assert row["et0_mm"] == _ET0_MM, f"the worker must compute a reported day: {dict(row)}"
        assert row["depletion_mm"] is not None, dict(row)
        assert row["irrigation_mm"] == 12.0, "the reported figure is the day's irrigation"
        assert row["created_by"] == "water-balance-auto", "the balance is the worker's"
        assert "irrigation_unobserved" not in row["decision"], (
            f"a reported day is not unobserved: {row['decision']}"
        )
        etc = float(row["etc_mm"])
        assert row["depletion_mm"] == pytest.approx(max(30.0 + etc - 12.0, 0.0), abs=0.01), (
            f"depletion must be yesterday's 30 mm + ETc - the reported 12 mm: {dict(row)}"
        )
        computed = dict(row)

        replay = await live.report(12.0)  # the outbox sends the same intent again
        assert replay["persisted"] is True, replay
        row = await live.today_row()
        for col in ("et0_mm", "depletion_mm", "deficit_mm", "confidence", "decision"):
            assert row[col] == computed[col], f"the replay changed {col}: {dict(row)}"
        assert row["irrigation_mm"] == 12.0, dict(row)


async def test_worker_first_then_replay_then_worker_recomputes_around_the_report(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.worker()
        before = dict(await live.today_row())
        assert before["et0_mm"] == _ET0_MM, before
        assert before["irrigation_mm"] == 0.0, before
        assert "irrigation_unobserved" in before["decision"], before

        await live.report(12.0)  # queued offline while the worker wrote the day
        row = await live.today_row()
        assert row["et0_mm"] == _ET0_MM, f"the replay wrote over ET0: {dict(row)}"
        assert row["depletion_mm"] == before["depletion_mm"], dict(row)
        assert row["confidence"] == before["confidence"], dict(row)
        assert row["irrigation_mm"] == 12.0, dict(row)
        assert row["irrigation_reported_by"] == live.farmer, dict(row)

        await live.worker()
        after = await live.today_row()
        assert after["irrigation_mm"] == 12.0, (
            f"the worker overwrote the farmer's water with irrigation_runs: {dict(after)}"
        )
        assert after["depletion_mm"] == pytest.approx(before["depletion_mm"] - 12.0, abs=0.01), (
            f"the balance must be recomputed with the reported 12 mm: {before} -> {dict(after)}"
        )
        assert "irrigation_unobserved" not in after["decision"], after["decision"]
        assert after["et0_mm"] is not None and after["depletion_mm"] is not None, dict(after)


async def test_negative_control_the_pre_fix_upsert_nulls_the_computed_balance(monkeypatch):
    """Without the fix, the same replay on the same day loses ET0 and depletion."""
    async with Live(monkeypatch) as live:
        await live.worker()
        assert (await live.today_row())["et0_mm"] == _ET0_MM, "worker did not compute the day"
        async with live.app_pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", live.tenant)
            await conn.execute(
                _PRE_FIX_UPSERT,
                live.tenant,
                live.field_id,
                _today(),
                *([None] * 4),
                12.0,
                *([None] * 6),
                live.farmer,
            )
        row = await live.today_row()
        assert row["et0_mm"] is None and row["depletion_mm"] is None, (
            f"the pre-fix SQL no longer reproduces the fault, so this control proves nothing: "
            f"{dict(row)}"
        )


async def test_a_full_manual_entry_stays_the_persons_day(monkeypatch):
    async with Live(monkeypatch) as live:
        req = live.router.WaterLedgerUpsertRequest(
            ledger_date=_today().isoformat(), et0_mm=5.0, depletion_mm=20.0, irrigation_mm=4.0
        )
        await live.router.upsert_water_ledger(
            req=req, field_id=live.field_id, user=_user(live.tenant, live.farmer)
        )
        await live.worker()
        row = await live.today_row()
        assert (row["et0_mm"], row["depletion_mm"], row["created_by"]) == (
            5.0,
            20.0,
            live.farmer,
        ), f"the worker wrote over a manual entry: {dict(row)}"

        await live.report(9.0)
        await live.worker()
        row = await live.today_row()
        assert row["irrigation_reported_by"] is None, (
            "a report on a manual entry must not hand the day to the worker"
        )
        assert (row["irrigation_mm"], row["et0_mm"], row["depletion_mm"]) == (9.0, 5.0, 20.0), dict(
            row
        )


async def test_a_full_entry_onto_a_day_a_report_opened_takes_the_day(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.report(12.0)
        await live.post(et0_mm=5.0, depletion_mm=20.0, irrigation_mm=4.0)
        row = await live.today_row()
        assert (row["created_by"], row["irrigation_reported_by"]) == (live.farmer, None), (
            f"a full entry on an uncomputed report day must take it like a new day: {dict(row)}"
        )
        await live.worker()
        row = await live.today_row()
        assert (row["et0_mm"], row["depletion_mm"], row["irrigation_mm"], row["created_by"]) == (
            5.0,
            20.0,
            4.0,
            live.farmer,
        ), f"the worker wrote over the manual entry: {dict(row)}"


@pytest.mark.parametrize("worker_first", [True, False], ids=["worker-first", "report-first"])
async def test_an_as_applied_reconciliation_after_a_report_keeps_its_day(monkeypatch, worker_first):
    async with Live(monkeypatch) as live:
        if worker_first:
            await live.worker()
        await live.report(12.0)
        await live.as_applied(20.0, 5.0, "deadbeef")
        reconciled = dict(await live.today_row())
        assert reconciled["created_by"] == "as_applied:deadbeef", reconciled
        assert reconciled["irrigation_mm"] == 32.0, reconciled

        await live.worker()
        row = await live.today_row()
        for col in ("created_by", "decision", "depletion_mm", "irrigation_mm", "et0_mm"):
            assert row[col] == reconciled[col], (
                f"the worker took back an as-applied day ({col}): {reconciled} -> {dict(row)}"
            )


async def test_a_full_entry_that_clears_irrigation_clears_the_reporter(monkeypatch):
    async with Live(monkeypatch) as live:
        await live.worker()
        await live.post(et0_mm=5.0, irrigation_mm=7.0)
        row = await live.today_row()
        assert row["irrigation_reported_by"] == live.farmer, (
            f"a figure sent on a worker day is a report the worker keeps: {dict(row)}"
        )
        await live.worker()
        row = await live.today_row()
        assert (row["irrigation_mm"], row["et0_mm"]) == (7.0, _ET0_MM), dict(row)

        await live.post(et0_mm=5.0, irrigation_mm=None)
        row = await live.today_row()
        assert row["irrigation_reported_by"] is None, (
            f"a cleared figure must not leave a reporter behind: {dict(row)}"
        )
        await live.worker()
        row = await live.today_row()
        assert row["irrigation_mm"] == 0.0, (
            f"the stored figure must be the one the balance used (no runs today): {dict(row)}"
        )
        assert "irrigation_unobserved" in row["decision"], row["decision"]


async def test_another_tenants_report_is_404_and_changes_nothing(monkeypatch):
    from fastapi import HTTPException

    async with Live(monkeypatch) as live:
        await live.worker()
        before = dict(await live.today_row())
        with pytest.raises(HTTPException) as caught:
            await live.report(50.0, tenant=live.other_tenant)
        assert caught.value.status_code == 404, caught.value.detail
        assert dict(await live.today_row()) == before, "a foreign report changed the row"
