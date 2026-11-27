"""H5.1 — live PostgreSQL certification of the server-authoritative field↔water-source binding.

Runs only under ``pytest -m integration`` and drives the REAL resolver
(``api.irrigation_source_binding.resolve_active_bindings``) plus the REAL gate
(``evaluate_water_salinity_gate``) against the REAL v214/v168/v170 tables, as a restricted
NOSUPERUSER/NOBYPASSRLS app role, to certify what the pure/static tests cannot:

  * the active binding for a field resolves the correct source + its EC limit from SoR;
  * the decision-grade sample filter is enforced in SQL — an estimated/measured-only source
    yields no decision-grade sample (and the gate blocks WATER_QUALITY_NOT_DECISION_GRADE),
    while a field_validated / certified sample is selected and clears;
  * suspended bindings and expired validity windows are NOT resolved;
  * FORCE RLS isolates a tenant's bindings — tenant A cannot see tenant B's binding;
  * an unbound field resolves to an empty list (the honest "no limit to enforce" path).

Requires (env), mirroring the IRR-F01 certification pattern:
  TEST_DATABASE_URL        — app-role DSN (NOSUPERUSER, NOBYPASSRLS, NOINHERIT), TCP.
  TEST_DATABASE_ADMIN_URL  — owner/superuser DSN, used ONLY to seed dependency rows across tenants.
  H51_CERTIFICATION_REQUIRED=1 — turn every skip (no DB, no driver, no admin DSN, wrong role,
                                 missing migration) into a HARD failure; no green-but-skipped cert.
The database must already have migrations through v214 applied.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

CERTIFICATION_REQUIRED = os.getenv("H51_CERTIFICATION_REQUIRED") == "1"

# The resolver + policy live in the platform's api package (pure, no FastAPI import chain).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "sahool-platform"))

try:
    import asyncpg
except ImportError:  # pragma: no cover - driver presence is environment-dependent
    asyncpg = None
    if CERTIFICATION_REQUIRED:
        raise

from api.canonical_well_capability import (  # noqa: E402
    WATER_QUALITY_NOT_DECISION_GRADE,
    evaluate_water_salinity_gate,
)
from api.irrigation_source_binding import resolve_active_bindings  # noqa: E402

APP_URL = os.getenv("TEST_DATABASE_URL", "").strip()
ADMIN_URL = os.getenv("TEST_DATABASE_ADMIN_URL", "").strip() or APP_URL


def _skip_or_fail(reason: str) -> None:
    if CERTIFICATION_REQUIRED:
        raise AssertionError(f"H5.1 certification required but unavailable: {reason}")
    pytest.skip(reason)


@pytest.fixture(autouse=True)
def _require_live_database() -> None:
    """Check the environment when a test runs, never at import.

    S1 F3: the checks used to run at module level with ``allow_module_level=True``. pytest
    imports every file under ``testpaths`` before ``-m`` deselects anything, so each
    ``-m unit`` stage reported this integration-only file as *skipped* although none of its
    tests was selected. Here the file is simply deselected under ``-m unit``; under
    ``-m integration`` the same reasons still skip, and ``H51_CERTIFICATION_REQUIRED=1``
    still turns each of them into a hard failure.
    """
    if asyncpg is None:
        _skip_or_fail("asyncpg not installed")
    if not APP_URL:
        _skip_or_fail("TEST_DATABASE_URL not set")


async def _connect(url: str):
    return await asyncpg.connect(url, statement_cache_size=0)


async def _assert_app_role_restricted(app) -> None:
    flags = await app.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    if flags is None or flags["rolsuper"] or flags["rolbypassrls"]:
        _skip_or_fail(
            f"app role is not NOSUPERUSER/NOBYPASSRLS (RLS would not be exercised): {flags}"
        )


async def _seed_source(admin, tenant: str, *, ec_limit: float | None) -> str:
    """Seed a project + water source for a tenant (admin bypasses RLS). Returns source id."""
    project_id = str(uuid4())
    source_id = str(uuid4())
    await admin.execute(
        "INSERT INTO irrigation_projects (id, tenant_id, name) VALUES ($1,$2,$3)",
        project_id,
        tenant,
        "h51-proj",
    )
    await admin.execute(
        "INSERT INTO irrigation_water_sources "
        "(id, tenant_id, project_id, source_type, name, maximum_allowed_ec_ds_m) "
        "VALUES ($1,$2,$3,'well','h51-src',$4)",
        source_id,
        tenant,
        project_id,
        ec_limit,
    )
    return source_id


async def _add_sample(
    admin, tenant, source_id, *, ec, quality, days_ago=10, sampled_at=None
) -> None:
    await admin.execute(
        "INSERT INTO irrigation_water_quality_samples "
        "(tenant_id, water_source_id, sampled_at, ec_ds_m, quality) VALUES ($1,$2,$3,$4,$5)",
        tenant,
        source_id,
        sampled_at if sampled_at is not None else datetime.now(UTC) - timedelta(days=days_ago),
        ec,
        quality,
    )


async def _bind(
    admin,
    tenant,
    field_id,
    source_id,
    *,
    status="active",
    priority=1,
    valid_from_days=1,
    valid_to_days=None,
) -> None:
    await admin.execute(
        "INSERT INTO field_irrigation_source_assignments "
        "(tenant_id, field_id, water_source_id, status, priority, valid_from, valid_to) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7)",
        tenant,
        field_id,
        source_id,
        status,
        priority,
        datetime.now(UTC) - timedelta(days=valid_from_days),
        None if valid_to_days is None else datetime.now(UTC) + timedelta(days=valid_to_days),
    )


async def _resolve_as_tenant(app, tenant, field_id):
    await app.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return await resolve_active_bindings(app, field_id, now=datetime.now(UTC))


@pytest.mark.asyncio
async def test_binding_evidence_for_a_blend_uses_one_statement():
    app = await _connect(APP_URL)
    admin = await _connect(ADMIN_URL)
    try:
        await _assert_app_role_restricted(app)
        tenant, other = str(uuid4()), str(uuid4())
        field = f"h51-{uuid4()}"
        now = datetime.now(UTC)

        async def read(scope):
            await app.execute("SELECT set_config('app.current_tenant', $1, false)", scope)
            commands = []
            with app.query_logger(commands.append):
                rows = await resolve_active_bindings(app, field, now=now)
            await asyncio.sleep(0)  # asyncpg schedules query logger callbacks with call_soon.
            assert len(commands) == 1, [cmd.query for cmd in commands]
            return rows

        assert await read(tenant) == []
        sources = [await _seed_source(admin, tenant, ec_limit=3) for _ in range(6)]
        priorities = [3, 2, 1, 1, 1, 3]
        for source, priority in zip(sources, priorities, strict=True):
            await _bind(admin, tenant, field, source, priority=priority)

        absent = await read(tenant)
        assert [row["water_source_id"] for row in absent] == [
            source for _, source in sorted(zip(priorities, sources, strict=True))
        ]
        assert all(row["water_quality"] is None for row in absent)
        assert all(row["non_decision_grade_sample_present"] is False for row in absent)

        # A newer measured sample cannot displace a certified one, but a newer decision-grade
        # sample with a missing EC (or a future timestamp) must reach the gate as stored.
        for source in sources[:3]:
            await _add_sample(admin, tenant, source, ec=1, quality="certified", days_ago=4)
        await _add_sample(admin, tenant, sources[0], ec=5, quality="measured", days_ago=1)
        await _add_sample(
            admin, tenant, sources[1], ec=None, quality="field_validated", sampled_at=now
        )
        future = now + timedelta(days=1)
        await _add_sample(admin, tenant, sources[2], ec=4, quality="certified", sampled_at=future)
        await _add_sample(admin, tenant, sources[3], ec=1, quality="estimated")
        for ec in (5, 6):
            await _add_sample(admin, tenant, sources[4], ec=ec, quality="certified", sampled_at=now)

        # Another tenant uses the same field label and has its own source and evidence.
        foreign = await _seed_source(admin, other, ec_limit=2)
        await _bind(admin, other, field, foreign)
        await _add_sample(admin, other, foreign, ec=7, quality="certified")

        mixed = {row["water_source_id"]: row for row in await read(tenant)}
        assert set(mixed) == set(sources)
        qualities = [mixed[source]["water_quality"] for source in sources]
        assert qualities[0]["quality"] == "certified" and qualities[0]["ec_ds_m"] == 1
        assert qualities[1] == {
            "ec_ds_m": None,
            "sampled_at": now.isoformat(),
            "quality": "field_validated",
        }
        assert qualities[2] == {
            "ec_ds_m": 4,
            "sampled_at": future.isoformat(),
            "quality": "certified",
        }
        assert qualities[3] is None
        # No precedence is specified between equally recent decision-grade samples.
        assert qualities[4]["sampled_at"] == now.isoformat() and qualities[4]["ec_ds_m"] in (5, 6)
        assert qualities[5] is None
        assert [
            source for source in sources if mixed[source]["non_decision_grade_sample_present"]
        ] == [sources[3]]
        foreign_rows = await read(other)
        assert [row["water_source_id"] for row in foreign_rows] == [foreign]
        assert foreign_rows[0]["water_quality"]["ec_ds_m"] == 7
    finally:
        await app.close()
        await admin.close()


def test_h51_field_source_binding_live_pg() -> None:
    async def _run() -> None:
        app = await _connect(APP_URL)
        admin = await _connect(ADMIN_URL)
        try:
            await _assert_app_role_restricted(app)
            tenant_a = str(uuid4())
            tenant_b = str(uuid4())

            # 1) Decision-grade (field_validated) sample below the limit → resolves + gate clear.
            fid = f"h51-{uuid4().hex[:8]}"
            src = await _seed_source(admin, tenant_a, ec_limit=3.0)
            await _add_sample(admin, tenant_a, src, ec=2.4, quality="field_validated")
            b = await _resolve_as_tenant(app, tenant_a, fid)  # no binding yet
            assert b == [], "unbound field must resolve to empty (no limit to enforce)"
            await _bind(admin, tenant_a, fid, src)
            b = await _resolve_as_tenant(app, tenant_a, fid)
            assert len(b) == 1 and b[0]["water_source_id"] == src, b
            assert b[0]["maximum_allowed_ec_ds_m"] == 3.0
            assert b[0]["water_quality"]["quality"] == "field_validated"
            gate = evaluate_water_salinity_gate(
                maximum_allowed_ec_ds_m=b[0]["maximum_allowed_ec_ds_m"],
                water_quality=b[0]["water_quality"],
                require_decision_grade=True,
                non_decision_grade_sample_present=b[0]["non_decision_grade_sample_present"],
            )
            assert gate["status"] == "clear", gate

            # 2) estimated/measured-only source → NO decision-grade sample selected, flag set,
            #    gate blocks NOT_DECISION_GRADE (the SQL tier filter is real).
            fid2 = f"h51-{uuid4().hex[:8]}"
            src2 = await _seed_source(admin, tenant_a, ec_limit=3.0)
            await _add_sample(admin, tenant_a, src2, ec=1.0, quality="estimated", days_ago=2)
            await _add_sample(admin, tenant_a, src2, ec=1.1, quality="measured", days_ago=1)
            await _bind(admin, tenant_a, fid2, src2)
            b2 = await _resolve_as_tenant(app, tenant_a, fid2)
            assert b2[0]["water_quality"] is None, b2
            assert b2[0]["non_decision_grade_sample_present"] is True
            gate2 = evaluate_water_salinity_gate(
                maximum_allowed_ec_ds_m=b2[0]["maximum_allowed_ec_ds_m"],
                water_quality=b2[0]["water_quality"],
                require_decision_grade=True,
                non_decision_grade_sample_present=b2[0]["non_decision_grade_sample_present"],
            )
            assert gate2["status"] == "blocked"
            assert WATER_QUALITY_NOT_DECISION_GRADE in gate2["blocking_reasons"]

            # 2b) A later certified sample on the SAME source IS selected (maps to laboratory_verified).
            await _add_sample(admin, tenant_a, src2, ec=2.0, quality="certified", days_ago=0)
            b2b = await _resolve_as_tenant(app, tenant_a, fid2)
            assert b2b[0]["water_quality"]["quality"] == "certified", b2b

            # 3) suspended binding + expired-window binding are NOT resolved.
            fid3 = f"h51-{uuid4().hex[:8]}"
            src3 = await _seed_source(admin, tenant_a, ec_limit=2.0)
            await _bind(admin, tenant_a, fid3, src3, status="suspended")
            assert await _resolve_as_tenant(app, tenant_a, fid3) == [], "suspended must not resolve"
            fid4 = f"h51-{uuid4().hex[:8]}"
            src4 = await _seed_source(admin, tenant_a, ec_limit=2.0)
            # valid window entirely in the past (valid_to before now).
            await admin.execute(
                "INSERT INTO field_irrigation_source_assignments "
                "(tenant_id, field_id, water_source_id, valid_from, valid_to) VALUES ($1,$2,$3,$4,$5)",
                tenant_a,
                fid4,
                src4,
                datetime.now(UTC) - timedelta(days=10),
                datetime.now(UTC) - timedelta(days=1),
            )
            assert await _resolve_as_tenant(app, tenant_a, fid4) == [], (
                "expired window must not resolve"
            )

            # 4) RLS isolation: tenant B's binding is invisible to tenant A (same field_id).
            shared_fid = f"h51-{uuid4().hex[:8]}"
            src_b = await _seed_source(admin, tenant_b, ec_limit=1.0)
            await _bind(admin, tenant_b, shared_fid, src_b)
            assert await _resolve_as_tenant(app, tenant_a, shared_fid) == [], "cross-tenant leak!"
            seen_b = await _resolve_as_tenant(app, tenant_b, shared_fid)
            assert len(seen_b) == 1 and seen_b[0]["water_source_id"] == src_b
        finally:
            await app.close()
            await admin.close()

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_shared_aquifer_blocks_both_pivots_and_leaves_other_sources_available():
    from api.irrigation_source_binding import aquifer_allocation_blocker

    admin = await _connect(ADMIN_URL)
    app = await _connect(APP_URL)
    try:
        await _assert_app_role_restricted(app)
        tenant, other = str(uuid4()), str(uuid4())
        fields = [f"pivot-{uuid4()}" for _ in range(2)]
        now = datetime.now(UTC)
        for i in range(6):
            src = await _seed_source(admin, tenant, ec_limit=None)
            await admin.execute(
                """UPDATE irrigation_water_sources SET evidence =
                   jsonb_build_object('aquifer_safe_yield', jsonb_build_object(
                       'aquifer_id','synthetic-aquifer','sustainable_abstraction_lps',30,
                       'issuer','source-self-report','status','approved','water_source_id',id))
                   WHERE id=$1""",
                src,
            )
            await _bind(admin, tenant, fields[i % 2], src)
        canal = await _seed_source(admin, tenant, ec_limit=None)
        await admin.execute(
            "UPDATE irrigation_water_sources SET source_type='canal' WHERE id=$1", canal
        )
        canal_field = f"canal-{uuid4()}"
        await _bind(admin, tenant, canal_field, canal)
        future = f"future-{uuid4()}"
        await _bind(admin, tenant, future, src, valid_from_days=-1)
        await app.execute("SELECT set_config('app.current_tenant',$1,false)", tenant)

        async def reason(field, days=3, scope=tenant):
            return await aquifer_allocation_blocker(
                app, field, tenant_id=scope, start=now, end=now + timedelta(days=days)
            )

        for field in fields:
            assert len(await resolve_active_bindings(app, field, now=now)) == 3
            assert await reason(field) == "AQUIFER_ALLOCATION_UNVERIFIED"
        assert await reason(canal_field) is None
        assert await reason(future, days=0.5) is None
        assert await reason(future, days=3) == "AQUIFER_ALLOCATION_UNVERIFIED"
        assert await reason(fields[0], scope=other) == "water_source_binding_unresolved"
        await app.execute("SELECT set_config('app.current_tenant',$1,false)", other)
        assert await reason(fields[0], scope=other) is None
    finally:
        await app.close()
        await admin.close()


@pytest.mark.asyncio
async def test_operational_http_well_gate_precedes_daily_submit_and_hourly_persistence(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api import irrigation_runtime_orchestrator as runtime
    from api import main as platform
    from api.routers import irrigation_mpc as route
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    tenant = str(uuid4())
    admin = await _connect(ADMIN_URL)
    pool = await asyncpg.create_pool(APP_URL, min_size=1, max_size=2, statement_cache_size=0)
    fields = [f"pivot-{uuid4()}" for _ in range(2)]
    try:
        async with pool.acquire() as conn:
            await _assert_app_role_restricted(conn)
        for field in fields:
            await admin.execute(
                "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
                field,
                tenant,
            )
        for i in range(6):
            source = await _seed_source(admin, tenant, ec_limit=None)
            await _bind(admin, tenant, fields[i % 2], source)

        monkeypatch.setattr(platform, "_DB_POOL", pool)
        monkeypatch.setattr(route, "bridge_enabled", lambda: True)
        emit = AsyncMock(side_effect=AssertionError("blocked decision reached the bridge"))
        persist = AsyncMock(side_effect=AssertionError("blocked well schedule reached persistence"))
        monkeypatch.setattr(route, "emit_mpc_candidate", emit)
        monkeypatch.setattr(runtime, "_persist_schedule", persist)
        app = FastAPI()
        app.include_router(route.router)
        app.dependency_overrides[route.get_current_user] = lambda: SimpleNamespace(
            tenant_id=tenant, user_id=1, role="owner"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for field in fields:
                for endpoint, payload in (
                    ("recommendation", {"submit": True}),
                    ("hourly-recommendation", {"persist": True}),
                ):
                    response = await client.post(
                        f"/api/v1/fields/{field}/irrigation/mpc/{endpoint}", json=payload
                    )
                    assert response.status_code == 200
                    result = response.json()
                    assert result["status"] == "blocked"
                    assert result["reason"] == "AQUIFER_ALLOCATION_UNVERIFIED"
                    assert "decision" not in result and "actions" not in result
        emit.assert_not_awaited()
        persist.assert_not_awaited()
    finally:
        await pool.close()
        await admin.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("binding_state", ["missing", "expired"])
async def test_current_season_well_graph_remains_blocked_without_active_assignment(binding_state):
    """Exercise the persisted-graph fallback SQL and tenant scope on the real v175 schema."""
    from api.irrigation_source_binding import aquifer_allocation_blocker

    admin = await _connect(ADMIN_URL)
    app = await _connect(APP_URL)
    try:
        await _assert_app_role_restricted(app)
        schema = await app.fetchrow(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, a.attnotnull "
            "FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid "
            "WHERE c.oid='canonical_irrigation_capability_graphs'::regclass "
            "AND a.attname='well_id'"
        )
        assert schema is not None and all(schema.values()), (
            "the real graph must retain FORCE RLS and its non-null well column"
        )
        tenant, other = str(uuid4()), str(uuid4())
        field, season = f"persisted-{uuid4()}", f"season-{uuid4()}"
        source = await _seed_source(admin, tenant, ec_limit=None)
        project = await admin.fetchval(
            "SELECT project_id FROM irrigation_water_sources WHERE id=$1", source
        )
        well, pump, machine, controller, energy = (uuid4() for _ in range(5))
        await admin.execute(
            "INSERT INTO irrigation_wells(id,tenant_id,water_source_id,name) "
            "VALUES($1,$2,$3,'h51-persisted')",
            well,
            tenant,
            source,
        )
        await admin.execute(
            "INSERT INTO irrigation_pumps(id,tenant_id,project_id,name,pump_type) "
            "VALUES($1,$2,$3,'h51-persisted','submersible')",
            pump,
            tenant,
            project,
        )
        await admin.execute(
            "INSERT INTO irrigation_machines(id,tenant_id,project_id,name,machine_type) "
            "VALUES($1,$2,$3,'h51-persisted','center_pivot')",
            machine,
            tenant,
            project,
        )
        await admin.execute(
            "INSERT INTO irrigation_controllers(id,tenant_id,project_id,name,provider) "
            "VALUES($1,$2,$3,'h51-persisted','synthetic')",
            controller,
            tenant,
            project,
        )
        await admin.execute(
            "INSERT INTO irrigation_energy_systems(id,tenant_id,project_id,name,system_type) "
            "VALUES($1,$2,$3,'h51-persisted','grid')",
            energy,
            tenant,
            project,
        )
        # The well exists only in the relational column, not in the historic JSON payload.
        await admin.execute(
            """INSERT INTO canonical_irrigation_capability_graphs
               (tenant_id,project_id,field_id,season_id,well_id,pump_id,machine_id,
                controller_id,energy_system_id,capability_id,status,operational_eligible,
                maximum_flow_lps,maximum_daily_depth_mm,maximum_safe_depth_mm_event,
                terminal_pressure_bar,capability_digest,payload)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'verified',true,
                      30,20,10,2,$11,'{}'::jsonb)""",
            tenant,
            project,
            field,
            season,
            well,
            pump,
            machine,
            controller,
            energy,
            str(uuid4()),
            "a" * 64,
        )
        if binding_state == "expired":
            await _bind(admin, tenant, field, source, valid_from_days=2, valid_to_days=-1)
        now = datetime.now(UTC)
        await app.execute("SELECT set_config('app.current_tenant',$1,false)", tenant)
        assert await resolve_active_bindings(app, field, now=now) == []

        async def reason(*, scope=tenant, requested_season=season):
            return await aquifer_allocation_blocker(
                app,
                field,
                tenant_id=scope,
                start=now,
                end=now + timedelta(days=3),
                season_id=requested_season,
            )

        assert await reason() == "AQUIFER_ALLOCATION_UNVERIFIED"
        assert await reason(requested_season=f"other-{season}") is None
        assert await reason(scope=other) == "water_source_binding_unresolved"
        await app.execute("SELECT set_config('app.current_tenant',$1,false)", other)
        # This separate read contains no tenant predicate, so the assertion exercises RLS.
        assert (
            await app.fetchval(
                "SELECT count(*) FROM canonical_irrigation_capability_graphs "
                "WHERE field_id=$1 AND season_id=$2",
                field,
                season,
            )
            == 0
        )
        assert await reason(scope=other) is None
        assert await reason() == "water_source_binding_unresolved"
    finally:
        await app.close()
        await admin.close()
