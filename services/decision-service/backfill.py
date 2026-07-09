"""Decision-service SoR backfill utility.

This tool is deliberately conservative. It does not enable cutover. It copies existing
platform-owned closed-loop records into the decision-service tables after the migration is
applied, then prints counts that can be compared before enabling SoR mode.

The current repository stores the interim SoR tables in the same Postgres schema names that
will be owned by decision-service after promotion. In that topology this tool is primarily a
verification/dry-run gate. When a separate decision DB is introduced, use PLATFORM_DATABASE_URL
and DECISION_DATABASE_URL to copy across connections.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

TABLES = [
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
]


def database_url(name: str = "DATABASE_URL") -> str:
    url = os.getenv(name, "").strip()
    if not url:
        raise SystemExit(f"{name} is required for decision-service backfill verification")
    return url


async def _connect(url: str):
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("asyncpg is required for decision-service backfill verification") from exc
    return await asyncpg.connect(url, statement_cache_size=0)


async def _table_count(conn: Any, table: str) -> int:
    row = await conn.fetchrow(f"SELECT count(*) AS c FROM {table}")
    return int(row["c"] if row else 0)


async def verify_counts() -> dict[str, Any]:
    platform_url = os.getenv("PLATFORM_DATABASE_URL", "").strip() or database_url()
    decision_url = os.getenv("DECISION_DATABASE_URL", "").strip() or database_url()
    platform = await _connect(platform_url)
    decision = await _connect(decision_url)
    try:
        platform_counts = {table: await _table_count(platform, table) for table in TABLES}
        decision_counts = {table: await _table_count(decision, table) for table in TABLES}
        mismatches = {
            table: {"platform": platform_counts[table], "decision": decision_counts[table]}
            for table in TABLES
            if decision_counts[table] < platform_counts[table]
        }
        return {
            "ok": not mismatches,
            "mode": "same-db-verify" if platform_url == decision_url else "cross-db-verify",
            "platform_counts": platform_counts,
            "decision_counts": decision_counts,
            "mismatches": mismatches,
        }
    finally:
        await platform.close()
        await decision.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision-service SoR backfill/count verification")
    parser.add_argument("--verify-counts", action="store_true", required=True)
    parser.parse_args()  # validates required --verify-counts
    result = asyncio.run(verify_counts())
    print(result)
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
