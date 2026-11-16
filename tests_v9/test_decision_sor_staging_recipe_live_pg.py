"""The §0 role recipe of the staging decision-SoR runbook, run verbatim on a live PostgreSQL.

``docs/runbooks/DECISION_SERVICE_SOR_STAGING_CUTOVER_RUNBOOK.md`` §0 moves the five SoR tables
and two trigger functions to ``decision_schema_owner``. Two review findings (W2-01):

* ``ALTER TABLE ... OWNER TO`` also moves the ``BIGSERIAL`` sequence
  ``recommendation_outcomes_outcome_id_seq``; default privileges cover only future objects, so
  without an explicit sequence grant ``decision_service_app`` cannot insert;
* when the platform app role created (owned) the tables, the owner change drops it from the
  table and sequence ACLs, so the platform stops writing during the interim.

This module reproduces that case: a NOSUPERUSER, NOBYPASSRLS ``sahool_app`` creates stub tables
with the same names and sequence shape, the recipe block is extracted from the runbook and run
unchanged in one transaction (any error aborts it, as ``psql -v ON_ERROR_STOP=1`` would), and an
INSERT into every table through its defaults must then succeed as ``decision_service_app`` and as
``sahool_app``. Everything happens in a throwaway database; the cluster roles the recipe creates
are dropped afterwards.

Needs a superuser DSN (``TEST_DATABASE_ADMIN_URL``, else ``TEST_DATABASE_URL``). The recipe
creates fixed role names; if any of them already exists in the cluster the module does not touch
it. Without a database, or with ``DECISION_SOR_RECIPE_CERTIFICATION_REQUIRED`` unset, the cases
skip and say why; with the switch set to ``1`` every such condition is a failure.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REQUIRED = os.getenv("DECISION_SOR_RECIPE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_STAGING_CUTOVER_RUNBOOK.md"
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv("TEST_DATABASE_URL")

PLATFORM_ROLE = "sahool_app"
RECIPE_ROLES = ("decision_schema_owner", "decision_service_app", "decision_sor_auditor")
SOR_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)

# Same names, same sequence shape (only recommendation_outcomes has a BIGSERIAL in the platform
# migrations, v49), same trigger-function signatures (v235) as the real schema.
PLATFORM_SCHEMA = """
CREATE TABLE decision_record (decision_id text PRIMARY KEY, tenant_id uuid NOT NULL,
                              correlation_id uuid);
CREATE TABLE dispatch_decisions (decision_id text PRIMARY KEY, tenant_id uuid NOT NULL,
                                 correlation_id uuid);
CREATE TABLE outcome_record (outcome_id text PRIMARY KEY, tenant_id uuid NOT NULL);
CREATE TABLE recommendation_outcomes (outcome_id BIGSERIAL PRIMARY KEY, tenant_id uuid NOT NULL);
CREATE TABLE online_learning_updates (update_id text PRIMARY KEY, tenant_id uuid NOT NULL);
CREATE FUNCTION sahool_chain_correlation_root() RETURNS trigger LANGUAGE plpgsql
  SECURITY INVOKER SET search_path = pg_catalog, public AS $$
BEGIN NEW.correlation_id := gen_random_uuid(); RETURN NEW; END; $$;
CREATE FUNCTION sahool_chain_correlation_immutable() RETURNS trigger LANGUAGE plpgsql
  SECURITY INVOKER SET search_path = pg_catalog, public AS $$ BEGIN RETURN NEW; END; $$;
CREATE TRIGGER trg_decision_record_correlation_insert BEFORE INSERT ON decision_record
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_root();
CREATE TRIGGER trg_dispatch_decisions_correlation_insert BEFORE INSERT ON dispatch_decisions
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_root();
"""


def _skip_or_fail(message: str) -> None:
    if _REQUIRED:
        pytest.fail(message)
    pytest.skip(message)


def recipe_from_runbook() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("```sql\nCREATE ROLE")
    return text[start + len("```sql\n") : text.index("\n```", start)]


def _insert_statements(tag: str) -> list[str]:
    tenant = str(uuid.uuid4())
    return [
        f"INSERT INTO decision_record (decision_id, tenant_id) VALUES ('d-{tag}', '{tenant}')",
        f"INSERT INTO dispatch_decisions (decision_id, tenant_id) VALUES ('d-{tag}', '{tenant}')",
        f"INSERT INTO outcome_record (outcome_id, tenant_id) VALUES ('o-{tag}', '{tenant}')",
        f"INSERT INTO recommendation_outcomes (tenant_id) VALUES ('{tenant}')",
        f"INSERT INTO online_learning_updates (update_id, tenant_id) VALUES ('u-{tag}', '{tenant}')",
    ]


async def _run_case(recipe: str) -> dict[str, list[str]]:
    """Return, per inserting role, the INSERT errors after running ``recipe`` (empty = all ok)."""
    try:
        admin = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        _skip_or_fail(f"no live database: {type(exc).__name__}: {exc}")
    db_name = f"w201_recipe_{uuid.uuid4().hex[:12]}"
    created_roles: list[str] = []
    try:
        if not await admin.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
            _skip_or_fail("the admin DSN is not a superuser; it must create roles and a database")
        present = await admin.fetch(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY($1::text[])",
            [*RECIPE_ROLES, PLATFORM_ROLE],
        )
        if present:
            _skip_or_fail(
                "roles the recipe creates already exist in this cluster; not touching them: "
                + ", ".join(sorted(r["rolname"] for r in present))
            )
        await admin.execute(f"CREATE DATABASE {db_name}")
        await admin.execute(f"CREATE ROLE {PLATFORM_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT")
        created_roles.append(PLATFORM_ROLE)
        db = await asyncpg.connect(ADMIN_DSN, database=db_name, timeout=5)
        try:
            # The platform role applies the platform manifest, so it owns the tables.
            await db.execute(f"GRANT CREATE, USAGE ON SCHEMA public TO {PLATFORM_ROLE}")
            await db.execute(f"SET ROLE {PLATFORM_ROLE}")
            await db.execute(PLATFORM_SCHEMA)
            await db.execute("RESET ROLE")
            owners = await db.fetch(
                "SELECT relname, pg_get_userbyid(relowner) AS owner FROM pg_class "
                "WHERE relname = ANY($1::text[])",
                [*SOR_TABLES, "recommendation_outcomes_outcome_id_seq"],
            )
            assert {r["owner"] for r in owners} == {PLATFORM_ROLE}, owners
            assert len(owners) == 6, owners

            created_roles.extend(RECIPE_ROLES)  # created by the recipe; dropped in teardown
            await db.execute(recipe)  # one implicit transaction: any error aborts it

            errors: dict[str, list[str]] = {}
            for role in ("decision_service_app", PLATFORM_ROLE):
                errors[role] = []
                for stmt in _insert_statements(role):
                    await db.execute(f"SET ROLE {role}")
                    try:
                        await db.execute(stmt)
                    except asyncpg.PostgresError as exc:
                        errors[role].append(f"{type(exc).__name__}: {exc}")
                    finally:
                        await db.execute("RESET ROLE")
            return errors
        finally:
            await db.close()
    finally:
        try:
            await admin.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
            for role in reversed(created_roles):
                await admin.execute(f"DROP ROLE IF EXISTS {role}")
        finally:
            await admin.close()


def test_runbook_recipe_keeps_both_writers_inserting_after_the_owner_move():
    if not ADMIN_DSN:
        _skip_or_fail("TEST_DATABASE_ADMIN_URL / TEST_DATABASE_URL not set")
    errors = asyncio.run(_run_case(recipe_from_runbook()))
    assert errors == {"decision_service_app": [], PLATFORM_ROLE: []}, errors


def test_previous_recipe_reproduces_both_review_findings():
    """Negative control: without the explicit grants the two inserts fail as the review said."""
    if not ADMIN_DSN:
        _skip_or_fail("TEST_DATABASE_ADMIN_URL / TEST_DATABASE_URL not set")
    recipe = recipe_from_runbook()
    cut = recipe.index("-- Interim, while the platform is still the writer")
    tail = recipe.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO decision_sor_auditor;")
    previous = recipe[:cut] + recipe[tail:]
    errors = asyncio.run(_run_case(previous))
    assert errors["decision_service_app"] == [
        "InsufficientPrivilegeError: permission denied for sequence "
        "recommendation_outcomes_outcome_id_seq"
    ], errors
    assert len(errors[PLATFORM_ROLE]) == len(SOR_TABLES), errors
    assert all("permission denied for table" in e for e in errors[PLATFORM_ROLE]), errors
