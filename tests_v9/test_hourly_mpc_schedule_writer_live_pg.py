"""The hourly MPC schedule writer against the real v179 tables, on a restricted role.

The defect this measures: ``_persist_schedule`` inserted into
``hourly_irrigation_mpc_schedules`` without ``scheduled_volume_m3`` and into
``hourly_irrigation_mpc_actions`` without ``irrigation_volume_m3``. v179 declares both
``NOT NULL`` with no default, so every persist raised ``NotNullViolationError`` and the
table stayed empty; readers of it (the advisor's review-only engine proposals) therefore
always found nothing. The unit test of the orchestrator could not see it: its connection
accepts any SQL.

Measured here, on v179 applied as written into a throwaway schema, through a
NOSUPERUSER / NOBYPASSRLS role inside a transaction with ``app.current_tenant`` set (the
shape ``tenant_connection`` gives the route):

1. the role is restricted and the tables carry ENABLE + FORCE row level security;
2. a schedule produced by the real solver is stored once, with the volumes the solver
   computed (schedule total and per action), recommendation-only and never executable;
3. the same schedule again is idempotent (one row, the actions not duplicated);
4. another tenant sees none of it.

The schema and the role are dropped at the end. Nothing here executes irrigation.

Run: ``TEST_DATABASE_ADMIN_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
pytestmark.append(
    pytest.mark.skipif(
        not _ADMIN_DSN,
        reason="needs TEST_DATABASE_ADMIN_URL (a live DB whose role may create a schema and role)",
    )
)

_ROOT = Path(__file__).resolve().parents[1]
_MIGRATION = _ROOT / "migrations" / "v179_hourly_energy_aware_irrigation_mpc.sql"

_TENANT_A = "aaaaaaaa-0000-4000-8000-00000000179a"
_TENANT_B = "bbbbbbbb-0000-4000-8000-00000000179b"
_H = "a" * 64
_START = datetime(2026, 7, 13, 6, tzinfo=UTC)


def _solved_schedule(*, executable_gate: bool = True) -> dict:
    """A schedule from the real solver (inputs as in the solver's unit tests).

    With an executable commissioning gate it irrigates (actions, a positive volume); without
    one the solver blocks (no actions, no horizon, a zero volume), and the orchestrator
    persists that too.
    """
    from api.hourly_energy_aware_irrigation_mpc import solve_hourly_energy_aware_mpc

    forecast = [
        {
            "hour": (_START + timedelta(hours=i)).isoformat(),
            "etc_mm": 0.2,
            "effective_rain_mm": 0.0,
            "maximum_available_power_kw": 100.0,
            "maximum_starting_kva": 100.0,
            "energy_cost_per_kwh": 0.2,
            "renewable_fraction": 0.5,
            "permitted_load_ids": ["pump-1"],
            "energy_window_digest": str(i % 10) * 64,
        }
        for i in range(24)
    ]
    schedule = solve_hourly_energy_aware_mpc(
        tenant_id=_TENANT_A,
        field_id="field-179",
        season_id="season-179",
        canonical_water_state={
            "operational_eligible": True,
            "taw_mm": 120.0,
            "raw_mm": 60.0,
            "depletion_mm": 70.0,
            "water_state_digest": _H,
            "weather_snapshot_digest": "b" * 64,
            "soil_profile_digest": "c" * 64,
            "season_state_digest": "d" * 64,
        },
        irrigation_capability={
            "status": "verified",
            "maximum_flow_lps": 50.0,
            "maximum_daily_depth_mm": 15.0,
            "maximum_safe_depth_mm_event": 10.0,
            "specific_energy_kwh_m3": 0.3,
            "pump_starting_kva": 25.0,
            "required_energy_load_ids": ["pump-1"],
            "irrigation_capability_digest": "e" * 64,
        },
        commissioning_gate={
            "status": "executable" if executable_gate else "blocked",
            "execution_allowed": executable_gate,
            "executability_digest": "f" * 64,
        },
        hourly_forecast=forecast,
        area_ha=5.0,
    ).to_dict()
    if executable_gate:
        assert schedule["actions"], "the fixture must exercise the action writer too"
        assert schedule["scheduled_volume_m3"] > 0
    else:
        assert schedule["status"] == "blocked" and not schedule["actions"]
        assert schedule["horizon_start"] is None and schedule["scheduled_volume_m3"] == 0.0
    return schedule


def _role_dsn(role: str, password: str) -> dict:
    parts = urlsplit(_ADMIN_DSN)
    return {
        "host": parts.hostname or "127.0.0.1",
        "port": parts.port or 5432,
        "database": (parts.path or "/postgres").lstrip("/") or "postgres",
        "user": role,
        "password": password,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("executable_gate", [True, False], ids=["irrigate", "blocked"])
async def test_solver_schedule_is_stored_with_its_volumes_on_a_restricted_role(executable_gate):
    from api.irrigation_runtime_orchestrator import _persist_schedule

    suffix = uuid.uuid4().hex[:10]
    schema = f"hmpc_{suffix}"
    role = f"hmpc_rls_{suffix}"
    password = uuid.uuid4().hex
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = None
    try:
        await admin.execute(f"CREATE SCHEMA {schema}")
        await admin.execute(f"SET search_path TO {schema}, public")
        await admin.execute(_MIGRATION.read_text(encoding="utf-8"))
        await admin.execute(
            f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'"
        )
        await admin.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
        await admin.execute(
            f"GRANT SELECT, INSERT, UPDATE ON {schema}.hourly_irrigation_mpc_schedules, "
            f"{schema}.hourly_irrigation_mpc_actions TO {role}"
        )
        app = await asyncpg.connect(
            **_role_dsn(role, password), server_settings={"search_path": schema}
        )

        # (1) the instrument first.
        privileges = await admin.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=$1", role
        )
        assert not privileges["rolsuper"] and not privileges["rolbypassrls"]
        for table in ("hourly_irrigation_mpc_schedules", "hourly_irrigation_mpc_actions"):
            flags = await admin.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
                f"{schema}.{table}",
            )
            assert flags["relrowsecurity"] and flags["relforcerowsecurity"], table

        schedule = _solved_schedule(executable_gate=executable_gate)

        async def persist_as(tenant: str) -> None:
            async with app.transaction():
                await app.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
                await _persist_schedule(app, schedule)

        # (2) stored once, with the solver's own volumes.
        await persist_as(_TENANT_A)
        # (3) the same schedule again is idempotent.
        await persist_as(_TENANT_A)

        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", _TENANT_A)
            rows = await app.fetch(
                "SELECT schedule_id, scheduled_irrigation_mm, scheduled_volume_m3, "
                "recommendation_only, execution_allowed, horizon_start, schedule_digest "
                "FROM hourly_irrigation_mpc_schedules"
            )
            assert len(rows) == 1
            row = rows[0]
            assert row["scheduled_volume_m3"] == pytest.approx(schedule["scheduled_volume_m3"])
            assert row["scheduled_irrigation_mm"] == pytest.approx(
                schedule["scheduled_irrigation_mm"]
            )
            assert row["recommendation_only"] is True
            assert row["execution_allowed"] is False
            assert row["schedule_digest"] == schedule["schedule_digest"]
            if schedule["horizon_start"] is None:
                assert row["horizon_start"] is None
            else:
                assert row["horizon_start"] == datetime.fromisoformat(
                    schedule["horizon_start"].replace("Z", "+00:00")
                )
            actions = await app.fetch(
                "SELECT action_hour, irrigation_depth_mm, irrigation_volume_m3 "
                "FROM hourly_irrigation_mpc_actions WHERE schedule_id=$1 ORDER BY action_hour",
                row["schedule_id"],
            )
            assert len(actions) == len(schedule["actions"])
            for stored, solved in zip(actions, schedule["actions"], strict=True):
                assert stored["irrigation_volume_m3"] == pytest.approx(
                    solved["irrigation_volume_m3"]
                )
                assert stored["irrigation_depth_mm"] == pytest.approx(solved["irrigation_depth_mm"])
            assert sum(a["irrigation_volume_m3"] for a in actions) == pytest.approx(
                row["scheduled_volume_m3"], abs=1e-5
            )

        # (4) another tenant sees none of it.
        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", _TENANT_B)
            assert await app.fetchval("SELECT count(*) FROM hourly_irrigation_mpc_schedules") == 0
            assert await app.fetchval("SELECT count(*) FROM hourly_irrigation_mpc_actions") == 0
    finally:
        if app is not None:
            await app.close()
        await admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await admin.execute(f"DROP ROLE IF EXISTS {role}")
        await admin.close()
