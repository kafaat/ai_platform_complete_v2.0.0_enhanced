"""The daily water-ledger worker against a migrated Postgres (W0-10, weather-7; live PG).

The worker (``phase_runtime_workers.run_water_ledger_once``) runs on the real schema through a
pool whose role mirrors the production jobs role (``sahool_jobs``: NOSUPERUSER, BYPASSRLS).
Only the HTTP owners are replaced at the store-function level: weather-service (forecast,
archive, ET0) and the decision bridge. What is measured on the rows:

* ET0 is requested at the field's elevation (``fields.elevation_m``), not at sea level, and a
  field without an elevation gets no entry (a declared skip, never a sea-level value).
* Each entry records ``et0_method``, ``et0_quality``, ``weather_snapshot_id`` and
  ``rain_source='forecast'`` (v278).
* Yesterday's forecast rain is re-recorded from the archive before today's entry is built on
  it: ``rain_source`` becomes ``observed`` and yesterday's depletion is rebuilt from the day
  before, so today's balance starts from water that fell, not water that was forecast.
* A degraded Penman-Monteith (elevation rejected, sea-level default) is not reference ET0: the
  entry carries ``et0_reference_unavailable`` and the lowered confidence.
* v278 is idempotent, its CHECK constraints refuse an unknown rain source, and its .down.sql
  removes the columns and can be followed by v278 again.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", "")
TZ = "Asia/Aden"
UP = ROOT / "migrations" / "v278_water_ledger_et0_rain_provenance.sql"
DOWN = ROOT / "migrations" / "v278_water_ledger_et0_rain_provenance.down.sql"


async def _probe() -> str:
    if not ADMIN_DSN:
        return "TEST_DATABASE_ADMIN_URL not set"
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if not await conn.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
            return "admin URL is not a superuser (cannot create the jobs-like role)"
        cols = await conn.fetchval(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'water_ledger'"
            " AND column_name IN ('et0_method', 'et0_quality', 'weather_snapshot_id',"
            " 'rain_source')"
        )
        if cols != 4:
            return "schema not migrated (v278 columns missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _today() -> dt.date:
    return dt.datetime.now(ZoneInfo(TZ)).date()


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from api import phase_runtime_workers, water_decision_bridge, weather_service_client

    return phase_runtime_workers, weather_service_client, water_decision_bridge


def _pm_product(quality: str = "validated") -> dict:
    return {
        "product": "et0",
        "unit": "mm/day",
        "et0_mm": 5.0,
        "method": "fao56_penman_monteith",
        "quality_status": quality,
        "formula_version": "et0/fao56-pm/1.0.0",
        "valid_time": None,
        "weather_snapshot_id": f"wsnap/test/{quality}",
        "input_completeness": 1.0 if quality == "validated" else 0.75,
        "missing_inputs": [] if quality == "validated" else ["elevation_m"],
        "invalid_inputs": [],
        "limitations": [] if quality == "validated" else ["elevation defaulted to 0 m (sea level)"],
    }


class _World:
    """One tenant, a jobs-like BYPASSRLS role and the HTTP owners stubbed per test."""

    def __init__(self, monkeypatch, *, et0_quality: str = "validated", archive_rain=0.0):
        self.mp = monkeypatch
        self.tenant = str(uuid.uuid4())
        self.role = f"wl_jobs_{uuid.uuid4().hex[:10]}"
        self.et0_calls: list[dict] = []
        self.archive_calls: list[dict] = []
        self.et0_quality = et0_quality
        self.archive_rain = archive_rain
        self.fields: list[str] = []

    async def __aenter__(self):
        self.admin = await asyncpg.connect(ADMIN_DSN)
        await self.admin.execute(
            f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER BYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{self.role}";'
        )
        role = self.role

        async def setup(conn):
            await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(ADMIN_DSN, min_size=1, max_size=2, setup=setup)
        workers, wsc, bridge = _platform()
        self.workers = workers
        today = _today()

        async def forecast(lat, lon, *, days=7, model="best_match"):
            return {
                "days": [
                    {
                        "date": (today + dt.timedelta(days=k)).isoformat(),
                        "temp_max_c": 28.0,
                        "temp_min_c": 12.0,
                        "precipitation_mm": 0.0,
                        "rh_mean_pct": 30.0,
                        "wind_mean_10m_ms": 3.0,
                        "solar_radiation_mj_m2": 24.0,
                    }
                    for k in (-1, 0, 1)
                ]
            }

        async def historical(lat, lon, *, start_date, end_date, tenant_id=None):
            self.archive_calls.append({"start": start_date, "end": end_date, "tenant": tenant_id})
            return {"days": [{"date": start_date, "precipitation_mm": self.archive_rain}]}

        async def et0(**kw):
            self.et0_calls.append(kw)
            return _pm_product(self.et0_quality)

        async def bridge_off(**_kw):
            return {"status": "disabled"}

        self.mp.setattr(wsc, "get_weather_forecast", forecast)
        self.mp.setattr(wsc, "get_weather_historical", historical)
        self.mp.setattr(wsc, "get_et0_product", et0)
        self.mp.setattr(bridge, "process_water_deficit", bridge_off)
        self.mp.setenv("WATER_LEDGER_AUTO_ENABLED", "1")
        self.mp.setenv("WATER_LEDGER_TIMEZONE", TZ)
        return self

    async def field(self, *, elevation, lat=15.35) -> str:
        field_id = f"wl-{uuid.uuid4().hex[:12]}"
        await self.admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, crop, lat, lon, elevation_m)"
            " VALUES ($1, $1, $2::uuid, 'maize', $3, 44.2, $4)",
            field_id,
            self.tenant,
            lat,
            elevation,
        )
        await self.admin.execute(
            "INSERT INTO seasons (season_id, tenant_id, field_id, crops, sowing_date, status)"
            " VALUES ($1, $2::uuid, $3, $4::jsonb, $5, 'active')",
            f"s-{field_id}",
            self.tenant,
            field_id,
            json.dumps(["maize"]),
            _today() - dt.timedelta(days=60),
        )
        self.fields.append(field_id)
        return field_id

    async def ledger(self, field_id, day, **cols):
        names = ["tenant_id", "field_id", "ledger_date", *cols]
        marks = ["$1::uuid", "$2", "$3", *(f"${i}" for i in range(4, 4 + len(cols)))]
        await self.admin.execute(
            f"INSERT INTO water_ledger ({', '.join(names)}) VALUES ({', '.join(marks)})",
            self.tenant,
            field_id,
            day,
            *cols.values(),
        )

    async def row(self, field_id, day):
        return await self.admin.fetchrow(
            "SELECT * FROM water_ledger WHERE field_id = $1 AND ledger_date = $2", field_id, day
        )

    async def __aexit__(self, *exc):
        await self.pool.close()
        for field_id in self.fields:
            await self.admin.execute("DELETE FROM water_ledger WHERE field_id = $1", field_id)
            await self.admin.execute("DELETE FROM seasons WHERE field_id = $1", field_id)
            await self.admin.execute("DELETE FROM fields WHERE field_id = $1", field_id)
        await self.admin.execute(
            f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{self.role}";'
            f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM "{self.role}";'
            f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM "{self.role}";'
            f'REVOKE ALL ON SCHEMA public FROM "{self.role}";'
            f'DROP ROLE "{self.role}"'
        )
        await self.admin.close()


def _kc_today() -> float:
    from api.water_ledger_inputs import daily_kc

    return daily_kc("maize", _today() - dt.timedelta(days=60), _today()).kc


def test_elevation_reaches_et0_provenance_is_stored_and_yesterdays_rain_is_observed(
    monkeypatch, capsys
):
    async def run():
        async with _World(monkeypatch, archive_rain=0.0) as w:
            today = _today()
            highland = await w.field(elevation=2300.0, lat=15.35)
            unknown = await w.field(elevation=None, lat=15.99)
            # The day before yesterday: start of yesterday's balance.
            await w.ledger(
                highland,
                today - dt.timedelta(days=2),
                depletion_mm=20.0,
                created_by="water-balance-auto",
                decision="auto:irrigation_unobserved",
                rain_source="observed",
            )
            # Yesterday: 10 mm forecast that did not fall (archive: 0 mm).
            from api.water_balance import _effective_rain

            forecast_depletion = round(20.0 + 6.0 - _effective_rain(10.0), 2)
            await w.ledger(
                highland,
                today - dt.timedelta(days=1),
                et0_mm=5.0,
                kc=1.2,
                etc_mm=6.0,
                rain_mm=10.0,
                irrigation_mm=0.0,
                depletion_mm=forecast_depletion,
                deficit_mm=0.0,
                confidence=0.4,
                decision="auto:irrigation_unobserved",
                created_by="water-balance-auto",
                rain_source="forecast",
            )
            processed = await w.workers.run_water_ledger_once(w.pool)
            mine = [c for c in w.et0_calls if c["lat_deg"] in (15.35, 15.99)]
            return (
                processed,
                mine,
                list(w.archive_calls),
                await w.row(highland, today),
                await w.row(highland, today - dt.timedelta(days=1)),
                await w.row(unknown, today),
                forecast_depletion,
            )

    processed, et0_calls, archive, today_row, yday, unknown_row, forecast_dep = asyncio.run(run())
    today = _today()
    assert processed >= 1, "the worker wrote no entry for the field with an elevation"
    assert len(et0_calls) == 1, f"ET0 must be requested once (highland only): {et0_calls}"
    assert et0_calls[0]["elevation_m"] == 2300.0, (
        f"ET0 not requested at the field's elevation: {et0_calls[0].get('elevation_m')!r}"
    )
    assert et0_calls[0]["valid_time"] == today.isoformat(), "ET0 not bound to the ledger day"
    assert unknown_row is None, "a field without an elevation got an entry (sea-level ET0)"
    assert "field_elevation_missing" in capsys.readouterr().out, "the skip was not declared"

    assert today_row is not None, "today's entry missing"
    assert (today_row["et0_method"], today_row["et0_quality"]) == (
        "fao56_penman_monteith",
        "validated",
    ), f"ET0 provenance not stored: {today_row['et0_method']}/{today_row['et0_quality']}"
    assert today_row["weather_snapshot_id"] == "wsnap/test/validated", "snapshot id not stored"
    assert today_row["rain_source"] == "forecast", "today's rain must be declared a forecast"

    yesterday = today - dt.timedelta(days=1)
    assert archive == [
        {
            "start": yesterday.isoformat(),
            "end": yesterday.isoformat(),
            "tenant": archive[0]["tenant"],
        }
    ], f"the archive was not asked for yesterday only: {archive}"
    assert yday["rain_source"] == "observed", "yesterday's forecast rain was not re-recorded"
    assert yday["rain_mm"] == 0.0, f"observed rain not stored: {yday['rain_mm']}"
    assert yday["depletion_mm"] == 26.0, (
        f"yesterday's depletion not rebuilt from the day before with observed rain: "
        f"{yday['depletion_mm']} (forecast-based was {forecast_dep})"
    )
    assert yday["decision"] == "auto:irrigation_unobserved", "yesterday's flags were lost"
    expected_today = round(26.0 + round(_kc_today() * 5.0, 2), 2)
    assert today_row["depletion_mm"] == pytest.approx(expected_today, abs=0.01), (
        f"today's balance did not start from the observed day: {today_row['depletion_mm']} "
        f"!= {expected_today}"
    )


def test_a_degraded_penman_monteith_is_not_reference_and_lowers_confidence(monkeypatch):
    async def run():
        async with _World(monkeypatch, et0_quality="degraded") as w:
            field_id = await w.field(elevation=9999.0, lat=15.41)  # engine rejects it
            await w.workers.run_water_ledger_once(w.pool)
            return await w.row(field_id, _today())

    row = asyncio.run(run())
    assert row is not None, "the entry was not written"
    assert row["et0_quality"] == "degraded", "the degraded quality was not stored"
    assert "et0_reference_unavailable" in (row["decision"] or ""), (
        f"degraded PM counted as reference ET0: {row['decision']}"
    )
    assert row["confidence"] == 0.4, f"degraded ET0 kept full confidence: {row['confidence']}"


def test_a_manual_or_already_observed_yesterday_is_not_rewritten(monkeypatch):
    async def run():
        async with _World(monkeypatch, archive_rain=0.0) as w:
            today = _today()
            field_id = await w.field(elevation=1200.0, lat=15.43)
            await w.ledger(
                field_id,
                today - dt.timedelta(days=1),
                etc_mm=6.0,
                rain_mm=10.0,
                irrigation_mm=0.0,
                depletion_mm=12.0,
                decision="farmer note",
                created_by="farmer-1",
                rain_source="forecast",
            )
            await w.workers.run_water_ledger_once(w.pool)
            return list(w.archive_calls), await w.row(field_id, today - dt.timedelta(days=1))

    archive, yday = asyncio.run(run())
    assert archive == [], "the archive was fetched for a manual entry"
    assert (yday["rain_mm"], yday["rain_source"], yday["depletion_mm"]) == (
        10.0,
        "forecast",
        12.0,
    ), "a person's entry was rewritten by the worker"


def test_v278_is_idempotent_constrained_and_reversible():
    async def run():
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(UP.read_text(encoding="utf-8"))  # second application: no-op
            tenant = str(uuid.uuid4())
            with pytest.raises(asyncpg.CheckViolationError):
                await admin.execute(
                    "INSERT INTO water_ledger (tenant_id, field_id, ledger_date, rain_source)"
                    " VALUES ($1::uuid, 'v278-probe', CURRENT_DATE, 'guess')",
                    tenant,
                )
            with pytest.raises(asyncpg.CheckViolationError):
                await admin.execute(
                    "INSERT INTO water_ledger (tenant_id, field_id, ledger_date, et0_quality)"
                    " VALUES ($1::uuid, 'v278-probe', CURRENT_DATE, 'reference')",
                    tenant,
                )
            await admin.execute(DOWN.read_text(encoding="utf-8"))
            await admin.execute(DOWN.read_text(encoding="utf-8"))  # idempotent rollback
            after_down = await admin.fetchval(
                "SELECT count(*) FROM information_schema.columns WHERE table_name='water_ledger'"
                " AND column_name IN ('et0_method','et0_quality','weather_snapshot_id',"
                "'rain_source')"
            )
            await admin.execute(UP.read_text(encoding="utf-8"))
            after_up = await admin.fetchval(
                "SELECT count(*) FROM pg_constraint WHERE conrelid='water_ledger'::regclass"
                " AND conname LIKE 'water_ledger_%_check' AND conname IN"
                " ('water_ledger_et0_method_check','water_ledger_et0_quality_check',"
                "'water_ledger_rain_source_check')"
            )
            return after_down, after_up
        finally:
            await admin.close()

    after_down, after_up = asyncio.run(run())
    assert after_down == 0, f"v278.down left {after_down} provenance column(s)"
    assert after_up == 3, f"v278 after a rollback did not restore its constraints: {after_up}"
