"""Decision-service migration runner for the planned System-of-Record cutover.

This runner is intentionally separate from application startup. Promotion to SoR must be an
explicit release action, not an accidental side effect of importing the service.

Usage:
    python services/decision-service/migration_runner.py --check
    python services/decision-service/migration_runner.py --apply

Required env:
    DATABASE_URL

Optional safety env:
    DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true   # required for --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_TABLE = "decision_service_schema_migrations"
SCHEMA_LOCK_ID = 91420260709
HARDENING_VERSION = "033_tenant_boundary_hardening.sql"
COMPOSITION_VERSION = "034_tenant_boundary_policy_composition.sql"
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    checksum: str
    sql: str


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required for decision-service migration checks")
    return url


def allow_schema_change() -> bool:
    return os.getenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "").strip().lower() in _TRUTHY


def load_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=path.name,
                path=path,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    if not migrations:
        raise SystemExit(f"No decision-service migrations found in {MIGRATIONS_DIR}")
    return migrations


async def _connect():
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:  # pragma: no cover - deploy/runtime dependency
        raise SystemExit("asyncpg is required for decision-service migration checks") from exc
    return await asyncpg.connect(database_url(), statement_cache_size=0)


async def ensure_migration_table(conn: Any) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
          version text PRIMARY KEY,
          checksum text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


async def migration_table_exists(conn: Any) -> bool:
    """Read-only probe for the migration journal.

    Readiness/check paths run under the restricted application role and must never
    require DDL.  A missing journal means every known migration is pending; only
    the explicit --apply path may create the journal.
    """
    return bool(
        await conn.fetchval(
            "SELECT to_regclass($1) IS NOT NULL",
            f"public.{MIGRATION_TABLE}",
        )
    )


async def applied_versions(conn: Any) -> dict[str, str]:
    if not await migration_table_exists(conn):
        return {}
    rows = await conn.fetch(f"SELECT version, checksum FROM {MIGRATION_TABLE}")
    return {row["version"]: row["checksum"] for row in rows}


async def check_migrations() -> dict[str, Any]:
    migrations = load_migrations()
    conn = await _connect()
    try:
        applied = await applied_versions(conn)
        pending = []
        checksum_mismatches = []
        for migration in migrations:
            existing = applied.get(migration.version)
            if existing is None:
                pending.append(migration.version)
            elif existing != migration.checksum:
                checksum_mismatches.append(migration.version)
        return {
            "ok": not pending and not checksum_mismatches,
            "pending": pending,
            "checksum_mismatches": checksum_mismatches,
            "known_migrations": [m.version for m in migrations],
        }
    finally:
        await conn.close()


async def apply_migrations() -> dict[str, Any]:
    if not allow_schema_change():
        raise SystemExit(
            "Refusing to apply schema changes without DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true"
        )
    migrations = load_migrations()
    conn = await _connect()
    applied_now: list[str] = []
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_ID)
            await ensure_migration_table(conn)
            applied = await applied_versions(conn)
            for migration in migrations:
                existing = applied.get(migration.version)
                if existing == migration.checksum:
                    continue
                if existing and existing != migration.checksum:
                    raise RuntimeError(f"Migration checksum mismatch for {migration.version}")
                await conn.execute(migration.sql)
                await conn.execute(
                    f"INSERT INTO {MIGRATION_TABLE} (version, checksum) VALUES ($1, $2)",
                    migration.version,
                    migration.checksum,
                )
                applied_now.append(migration.version)
        status = await check_migrations()
        status["applied_now"] = applied_now
        return status
    finally:
        await conn.close()


def _validate_composition_journal(
    migrations: list[Migration], applied: dict[str, str], *, include_hardening: bool = False
) -> None:
    first_required = HARDENING_VERSION if include_hardening else COMPOSITION_VERSION
    if COMPOSITION_VERSION in applied and HARDENING_VERSION not in applied:
        raise RuntimeError("034 is journaled without its 033 prerequisite")
    known = {m.version: m.checksum for m in migrations}
    if set(applied) - set(known):
        raise RuntimeError("Migration journal contains versions outside the reviewed source")
    for migration in migrations:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise RuntimeError(f"Migration checksum mismatch for {migration.version}")
        if migration.version < first_required and recorded is None:
            raise RuntimeError(f"034 prerequisite is not journaled: {migration.version}")


async def inspect_composition() -> dict[str, Any]:
    """Collect bounded metadata in a server-enforced read-only transaction.

    This observation neither authorizes application nor proves restricted-role
    behavior. Permission errors propagate instead of being reported as absence.
    """
    migrations = load_migrations()
    target = next(m for m in migrations if m.version == COMPOSITION_VERSION)
    conn = await _connect()
    try:
        async with conn.transaction(readonly=True):
            await conn.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
            await conn.execute("SET LOCAL lock_timeout = '5s'")
            await conn.execute("SET LOCAL statement_timeout = '30s'")
            read_only = await conn.fetchval("SHOW transaction_read_only")
            if read_only != "on":
                raise RuntimeError("034 observation requires server-enforced read-only mode")
            identity = await conn.fetchrow(
                "SELECT current_user AS role, session_user AS session, "
                "rolsuper, rolbypassrls, rolcanlogin, "
                "current_setting('server_version_num') AS server_version_num "
                "FROM pg_roles WHERE rolname=current_user"
            )
            memberships = await conn.fetch(
                "SELECT parent.rolname AS role FROM pg_auth_members m "
                "JOIN pg_roles parent ON parent.oid=m.roleid "
                "JOIN pg_roles child ON child.oid=m.member "
                "WHERE child.rolname=current_user ORDER BY parent.rolname"
            )
            applied = await applied_versions(conn)
            tables = await conn.fetch(
                "SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, "
                "c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind IN ('r','p') "
                "AND c.relname=ANY($1::text[]) ORDER BY c.relname",
                ["decision_outbox_events", "decision_reviews"],
            )
            policies = await conn.fetch(
                "SELECT tablename, policyname, permissive, roles, cmd, qual, with_check "
                "FROM pg_policies WHERE schemaname='public' "
                "AND tablename=ANY($1::text[]) ORDER BY tablename, policyname",
                ["decision_outbox_events", "decision_reviews"],
            )
            try:
                _validate_composition_journal(migrations, applied)
                journal_error = None
            except RuntimeError as exc:
                journal_error = str(exc)
            try:
                _validate_composition_journal(migrations, applied, include_hardening=True)
                pair_journal_error = None
            except RuntimeError as exc:
                pair_journal_error = str(exc)
            prerequisites_ok = (
                journal_error is None
                and len(tables) == 2
                and all(row["relrowsecurity"] and row["relforcerowsecurity"] for row in tables)
            )
        return {
            "ok": prerequisites_ok,
            "scope": "034_readonly_observation",
            "transaction_read_only": read_only,
            "identity": dict(identity),
            "memberships": [dict(row) for row in memberships],
            "source_checksum": target.checksum,
            "journal": applied,
            "journal_error": journal_error,
            "pair_journal_error": pair_journal_error,
            "pair_prerequisites_ok": pair_journal_error is None and len(tables) == 2,
            "pair_source_checksums": {
                m.version: m.checksum
                for m in migrations
                if m.version in {HARDENING_VERSION, COMPOSITION_VERSION}
            },
            "tables": [dict(row) for row in tables],
            "policies": [dict(row) for row in policies],
            "pending": [m.version for m in migrations if m.version not in applied],
            "authorization_or_acceptance": False,
        }
    finally:
        await conn.close()


async def apply_composition_only(expected_sha256: str) -> dict[str, Any]:
    """Apply only 034; 033 must already be journaled with its exact checksum."""
    return await _apply_boundary_scope({COMPOSITION_VERSION: expected_sha256})


async def apply_hardening_pair(
    expected_033_sha256: str, expected_034_sha256: str
) -> dict[str, Any]:
    """Apply only the reviewed 033+034 pair atomically; never apply 035 or later."""
    return await _apply_boundary_scope(
        {HARDENING_VERSION: expected_033_sha256, COMPOSITION_VERSION: expected_034_sha256}
    )


async def _apply_boundary_scope(expected_checksums: dict[str, str]) -> dict[str, Any]:
    # An exact allowlist is deliberate: this operator path cannot become a
    # generic migration-range bypass if another caller supplies extra versions.
    if set(expected_checksums) not in (
        {COMPOSITION_VERSION},
        {HARDENING_VERSION, COMPOSITION_VERSION},
    ):
        raise RuntimeError("Only the explicit 034 or 033+034 scope is permitted")
    if not allow_schema_change():
        raise SystemExit(
            "Refusing to apply schema changes without DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true"
        )
    migrations = load_migrations()
    by_version = {m.version: m for m in migrations}
    targets = []
    for version, expected in sorted(expected_checksums.items()):
        target = by_version.get(version)
        if target is None or expected != target.checksum:
            raise RuntimeError(f"{version} source checksum differs from the reviewed SHA-256")
        targets.append(target)
    include_hardening = HARDENING_VERSION in expected_checksums
    conn = await _connect()
    applied_now: list[str] = []
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
            await conn.execute("SET LOCAL lock_timeout = '5s'")
            await conn.execute("SET LOCAL statement_timeout = '30s'")
            await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_ID)
            if not await migration_table_exists(conn):
                raise RuntimeError("034 requires an existing migration journal")
            applied = await applied_versions(conn)
            _validate_composition_journal(migrations, applied, include_hardening=include_hardening)
            for target in targets:
                # In pair mode, real 033 DDL establishes these flags first.
                # On repeats or 034-only calls, missing flags still fail closed.
                if target.version == COMPOSITION_VERSION:
                    flags = await conn.fetch(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relnamespace='public'::regnamespace "
                        "AND relkind IN ('r','p') AND relname=ANY($1::text[])",
                        ["decision_outbox_events", "decision_reviews"],
                    )
                    if len(flags) != 2 or not all(
                        row["relrowsecurity"] and row["relforcerowsecurity"] for row in flags
                    ):
                        raise RuntimeError(
                            "034 requires both existing tables with ENABLE and FORCE RLS"
                        )
                if target.version in applied:
                    continue
                await conn.execute(target.sql)
                await conn.execute(
                    f"INSERT INTO public.{MIGRATION_TABLE} (version, checksum) VALUES ($1, $2)",
                    target.version,
                    target.checksum,
                )
                applied_now.append(target.version)
                applied[target.version] = target.checksum
            pending = [m.version for m in migrations if m.version not in applied]
        return {
            "ok": True,
            "scope": "033+034" if include_hardening else COMPOSITION_VERSION,
            "checksum": by_version[COMPOSITION_VERSION].checksum,
            "source_checksums": {m.version: m.checksum for m in targets},
            "applied_now": applied_now,
            "remaining_pending": pending,
            "staging_acceptance_proven": False,
        }
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision-service SoR migration runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify all migrations are applied")
    group.add_argument("--apply", action="store_true", help="Apply pending migrations")
    group.add_argument(
        "--inspect-034", action="store_true", help="Read-only 034 journal/catalog snapshot"
    )
    group.add_argument(
        "--apply-034-only", action="store_true", help="Apply only the reviewed 034 migration"
    )
    group.add_argument(
        "--apply-033-034-only", action="store_true", help="Apply only the reviewed 033+034 pair"
    )
    parser.add_argument(
        "--expected-sha256", help="Reviewed 034 SHA-256 for either scoped apply mode"
    )
    parser.add_argument("--expected-033-sha256", help="Reviewed 033 SHA-256 for pair mode only")
    args = parser.parse_args()
    if args.apply_033_034_only:
        if not args.expected_033_sha256 or not args.expected_sha256:
            parser.error(
                "--apply-033-034-only requires both --expected-033-sha256 and --expected-sha256"
            )
        operation = apply_hardening_pair(args.expected_033_sha256, args.expected_sha256)
    elif args.apply_034_only:
        if args.expected_033_sha256:
            parser.error("--expected-033-sha256 is valid only with --apply-033-034-only")
        if not args.expected_sha256:
            parser.error("--apply-034-only requires --expected-sha256")
        operation = apply_composition_only(args.expected_sha256)
    else:
        if args.expected_sha256 or args.expected_033_sha256:
            parser.error("Expected checksums are valid only with the matching scoped apply mode")
        if args.inspect_034:
            operation = inspect_composition()
        else:
            operation = apply_migrations() if args.apply else check_migrations()
    result = asyncio.run(operation)
    print(
        json.dumps(result, sort_keys=True)
        if args.inspect_034 or args.apply_034_only or args.apply_033_034_only
        else result
    )
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
