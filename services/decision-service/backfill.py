"""Decision-service SoR backfill utility.

This tool is deliberately conservative. It does not enable cutover. It copies existing
platform-owned closed-loop records into the decision-service tables after the migration is
applied, then prints counts that can be compared before enabling SoR mode.

The current repository stores the interim SoR tables in the same Postgres schema names that
will be owned by decision-service after promotion. In that topology this tool is primarily a
verification/dry-run gate. When a separate decision DB is introduced, use PLATFORM_DATABASE_URL
and DECISION_DATABASE_URL to copy across connections.

WX-10.7 review layer (`--verify-review`): migration 002 backfills existing candidates to
`review_state='pending_approval'` and lifts `candidate_lineage_id` out of `decision_value`
jsonb. That backfill is deterministic and idempotent, but a candidate whose evidence lacks a
`candidate_lineage_id` is left with a NULL lineage — which makes it fail-closed *un-reviewable*
(the atomic transition keys on `candidate_lineage_id = $` and NULL never matches), NOT
mis-approved. `--verify-review` is a read-only pre-cutover parity/quarantine check: it surfaces
those ambiguous candidates so an operator resolves them deliberately instead of the migration
silently leaving them un-reviewable. It never guesses and never writes.
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

VALID_REVIEW_STATES = {"pending_approval", "approved", "rejected"}


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


def classify_candidates(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    """Pure WX-10.7 review-backfill classifier over decision_record candidate rows.

    Each row is expected to expose: decision_id, stage, review_state, candidate_lineage_id,
    and evidence_status (the `decision_value->>'status'` evidence field). Non-candidate rows are
    ignored. A candidate is QUARANTINED (never guessed, never mutated) when the migration's
    deterministic backfill could not produce an authoritatively reviewable row:

    - `review_state` was not backfilled (NULL) — the migration should set every candidate;
    - `review_state` holds a value outside the allowed set (schema/data drift);
    - `candidate_lineage_id` is NULL/empty — fail-closed un-reviewable (the atomic transition
      keys on it, and NULL never matches a supplied lineage);
    - the evidence `status` disagrees with a candidate (`!= pending_approval`) — ambiguous.

    Returns (quarantine, parity_counts, ok). `ok` is False if any candidate is quarantined or any
    review_state is NULL/invalid — i.e. the operator must resolve before the ownership flip.
    """
    quarantine: list[dict[str, Any]] = []
    parity = {
        "candidates": 0,
        "pending_approval": 0,
        "approved": 0,
        "rejected": 0,
        "review_state_null": 0,
        "invalid_review_state": 0,
        "missing_lineage": 0,
        "evidence_status_mismatch": 0,
    }
    for row in rows:
        if row.get("stage") != "candidate":
            continue
        parity["candidates"] += 1
        review_state = row.get("review_state")
        lineage = (
            (row.get("candidate_lineage_id") or "").strip()
            if row.get("candidate_lineage_id") is not None
            else ""
        )
        evidence_status = row.get("evidence_status")
        reasons: list[str] = []

        if review_state is None:
            parity["review_state_null"] += 1
            reasons.append(
                "review_state not backfilled (NULL) — migration 002 did not classify this candidate"
            )
        elif review_state not in VALID_REVIEW_STATES:
            parity["invalid_review_state"] += 1
            reasons.append(
                f"invalid review_state={review_state!r} (not in {sorted(VALID_REVIEW_STATES)})"
            )
        elif review_state in parity:
            parity[review_state] += 1

        if not lineage:
            parity["missing_lineage"] += 1
            reasons.append(
                "candidate_lineage_id is NULL/empty — fail-closed un-reviewable "
                "(atomic transition keys on candidate_lineage_id; resolve before cutover, do not guess)"
            )
        if evidence_status is not None and evidence_status != "pending_approval":
            parity["evidence_status_mismatch"] += 1
            reasons.append(
                f"evidence status={evidence_status!r} disagrees with candidate stage (ambiguous)"
            )

        if reasons:
            quarantine.append(
                {
                    "decision_id": row.get("decision_id"),
                    "review_state": review_state,
                    "candidate_lineage_id": row.get("candidate_lineage_id"),
                    "reasons": reasons,
                }
            )

    ok = not quarantine and parity["review_state_null"] == 0 and parity["invalid_review_state"] == 0
    return quarantine, parity, ok


async def _review_schema_present(conn: Any) -> dict[str, bool]:
    """Confirm migration 002's review layer exists (columns, audit table, append-only trigger)."""
    review_state_col = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name='decision_record' AND column_name='review_state')"
    )
    lineage_col = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name='decision_record' AND column_name='candidate_lineage_id')"
    )
    reviews_table = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='decision_reviews')"
    )
    append_only_trigger = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_decision_reviews_append_only')"
    )
    return {
        "decision_record.review_state": bool(review_state_col),
        "decision_record.candidate_lineage_id": bool(lineage_col),
        "decision_reviews": bool(reviews_table),
        "decision_reviews_append_only_trigger": bool(append_only_trigger),
    }


async def verify_review() -> dict[str, Any]:
    """Read-only WX-10.7 review parity + quarantine report (no writes, no guessing)."""
    conn = await _connect(database_url())
    try:
        schema = await _review_schema_present(conn)
        schema_ok = all(schema.values())
        rows: list[dict[str, Any]] = []
        if (
            schema["decision_record.review_state"]
            and schema["decision_record.candidate_lineage_id"]
        ):
            fetched = await conn.fetch(
                "SELECT decision_id, stage, review_state, candidate_lineage_id, "
                "(decision_value->>'status') AS evidence_status "
                "FROM decision_record WHERE stage = 'candidate'"
            )
            rows = [dict(r) for r in fetched]
        quarantine, parity, candidates_ok = classify_candidates(rows)
        return {
            "ok": schema_ok and candidates_ok,
            "schema": schema,
            "schema_ok": schema_ok,
            "parity": parity,
            "quarantine_count": len(quarantine),
            "quarantine": quarantine,
        }
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision-service SoR backfill/count verification")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--verify-counts",
        action="store_true",
        help="verify decision-side counts cover platform counts",
    )
    group.add_argument(
        "--verify-review",
        action="store_true",
        help="WX-10.7 read-only review parity/quarantine report (surfaces un-reviewable candidates)",
    )
    args = parser.parse_args()
    result = asyncio.run(verify_review() if args.verify_review else verify_counts())
    print(result)
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
