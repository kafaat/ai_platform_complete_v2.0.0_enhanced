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


def _skip_or_fail(reason: str, *, module_level: bool = False) -> None:
    if CERTIFICATION_REQUIRED:
        raise AssertionError(f"H5.1 certification required but unavailable: {reason}")
    # A module-level skip (during collection, e.g. under `-m unit` with no DB env) must declare
    # allow_module_level; a function-level skip (inside a test) must not.
    pytest.skip(reason, allow_module_level=module_level)


if asyncpg is None:
    _skip_or_fail("asyncpg not installed", module_level=True)
if not APP_URL:
    _skip_or_fail("TEST_DATABASE_URL not set", module_level=True)


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


async def _add_sample(admin, tenant, source_id, *, ec, quality, days_ago=10) -> None:
    await admin.execute(
        "INSERT INTO irrigation_water_quality_samples "
        "(tenant_id, water_source_id, sampled_at, ec_ds_m, quality) VALUES ($1,$2,$3,$4,$5)",
        tenant,
        source_id,
        datetime.now(UTC) - timedelta(days=days_ago),
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
