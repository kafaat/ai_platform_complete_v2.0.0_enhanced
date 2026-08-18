"""Read-only preflight for S5-EXEC-01 recommendation_outcomes compatibility migration.

This tool never applies DDL.  It verifies that an existing recommendation_outcomes relation
can be migrated by 032_recommendation_outcomes_cutover_compat.sql without laundering schema
drift or an already-corrupt idempotency/outcome identity set.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

REQUIRED_EXISTING_COLUMNS = {"tenant_id", "recommendation_id"}



def classify_observation(
    *,
    table_exists: bool,
    columns: set[str] | list[str] | tuple[str, ...] = (),
    duplicate_tenant_idempotency_groups: int = 0,
    null_outcome_ids: int = 0,
    duplicate_outcome_id_groups: int = 0,
) -> dict[str, Any]:
    """Classify a measured PostgreSQL observation without pretending a fake connection enforces DB semantics."""
    if not table_exists:
        return {
            "classification": "PASSED",
            "table_exists": False,
            "reason": "fresh_schema_migration_can_create_relation",
            "blockers": [],
        }
    cols = {str(c) for c in columns}
    blockers: list[str] = []
    missing = sorted(REQUIRED_EXISTING_COLUMNS - cols)
    if missing:
        blockers.append("missing_required_columns:" + ",".join(missing))
    if duplicate_tenant_idempotency_groups:
        blockers.append(f"duplicate_tenant_idempotency_groups:{int(duplicate_tenant_idempotency_groups)}")
    if null_outcome_ids:
        blockers.append(f"null_outcome_ids:{int(null_outcome_ids)}")
    if duplicate_outcome_id_groups:
        blockers.append(f"duplicate_outcome_id_groups:{int(duplicate_outcome_id_groups)}")
    return {
        "classification": "FAILED" if blockers else "PASSED",
        "table_exists": True,
        "columns_present": sorted(cols),
        "duplicate_tenant_idempotency_groups": int(duplicate_tenant_idempotency_groups),
        "null_outcome_ids": int(null_outcome_ids),
        "duplicate_outcome_id_groups": int(duplicate_outcome_id_groups),
        "blockers": blockers,
    }


async def inspect_connection(conn: Any) -> dict[str, Any]:
    await conn.execute("SET TRANSACTION READ ONLY")
    exists = bool(await conn.fetchval("SELECT to_regclass('recommendation_outcomes') IS NOT NULL"))
    if not exists:
        return classify_observation(table_exists=False)
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'recommendation_outcomes'
        """
    )
    columns = {str(row["column_name"]) for row in rows}
    dup_idem = 0
    if {"tenant_id", "idempotency_key"}.issubset(columns):
        dup_idem = int(await conn.fetchval(
            """SELECT count(*) FROM (
              SELECT tenant_id, idempotency_key FROM recommendation_outcomes
              WHERE idempotency_key IS NOT NULL
              GROUP BY tenant_id, idempotency_key HAVING count(*) > 1
            ) d"""
        ) or 0)
    null_ids = dup_ids = 0
    if "outcome_id" in columns:
        null_ids = int(await conn.fetchval(
            "SELECT count(*) FROM recommendation_outcomes WHERE outcome_id IS NULL"
        ) or 0)
        dup_ids = int(await conn.fetchval(
            """SELECT count(*) FROM (
              SELECT outcome_id FROM recommendation_outcomes
              WHERE outcome_id IS NOT NULL GROUP BY outcome_id HAVING count(*) > 1
            ) d"""
        ) or 0)
    return classify_observation(
        table_exists=True,
        columns=columns,
        duplicate_tenant_idempotency_groups=dup_idem,
        null_outcome_ids=null_ids,
        duplicate_outcome_id_groups=dup_ids,
    )


async def run() -> dict[str, Any]:
    # Use the service-owned pool contract; this tool must not create a new raw-connect exception.
    try:
        from persistence import acquire_connection, database_url  # type: ignore
    except ImportError as exc:
        return {"classification": "HARNESS_INVALID", "blockers": [f"persistence_import_failed:{exc}"]}
    if not database_url():
        raise SystemExit("DATABASE_URL is required")
    try:
        conn = await acquire_connection()
    except Exception as exc:
        return {"classification": "HARNESS_INVALID", "blockers": [f"database_connect_failed:{type(exc).__name__}"]}
    try:
        async with conn.transaction():
            return await inspect_connection(conn)
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = asyncio.run(run())
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("classification") == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
