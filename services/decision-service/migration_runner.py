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
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_TABLE = "decision_service_schema_migrations"
SCHEMA_LOCK_ID = 91420260709
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


async def applied_versions(conn: Any) -> dict[str, str]:
    await ensure_migration_table(conn)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision-service SoR migration runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify all migrations are applied")
    group.add_argument("--apply", action="store_true", help="Apply pending migrations")
    args = parser.parse_args()

    result = asyncio.run(apply_migrations() if args.apply else check_migrations())
    print(result)
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
