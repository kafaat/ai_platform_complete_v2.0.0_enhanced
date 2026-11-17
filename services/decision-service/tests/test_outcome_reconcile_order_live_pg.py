"""Which outcome reconciles must not depend on heap order (exploration bug, outcome_reconcile).

``reconcile_outcomes`` keeps the first row it sees per ``decision_id``. Before this fix
``read_outcomes_for_reconcile`` read both outcome tables without ``ORDER BY``, so the winning
outcome for a decision with several rows was whatever order PostgreSQL returned the heap in.
The intended semantics are latest-first, by time then id.

The live tests insert the OLDER row first, so a heap-order read returns it first. Heap order is
not the only plan, though: outcome_record has ``idx_outcome_record_tenant_decision (tenant_id,
decision_id, created_at DESC)``, and a scan of that index returns the NEWEST row first even
without ``ORDER BY``. Which plan the unordered read gets is the planner's choice (today it picks
``idx_outcome_record_content_digest`` on a cost tie, whose order follows the heap). So the
outcome_record test first runs the production read minus its ``ORDER BY`` under default planner
settings and fails with "negative control lost" unless a stale row comes first; only then does
its pass prove the ``ORDER BY``. The recommendation_outcomes test checks every forced plan.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

DB = os.getenv("DATABASE_URL", "").strip()
T0 = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _read_block() -> str:
    src = (SERVICE_DIR / "persistence.py").read_text(encoding="utf-8")
    start = src.index("async def read_outcomes_for_reconcile(")
    return src[start : src.index("class LearningUpdateConflict", start)]


@pytest.mark.unit
def test_both_reconcile_reads_are_ordered_latest_first():
    block = _read_block()
    assert "ORDER BY o.created_at DESC, o.outcome_id DESC" in block, (
        "outcome_record must be read latest-first (time, then id) for the first-row-wins reconcile"
    )
    assert "ORDER BY COALESCE(outcome_recorded_at, issued_at) DESC, outcome_id DESC" in block, (
        "recommendation_outcomes must be read latest-first (time, then id)"
    )


async def _seed_outcomes(tenant: str, decision: str, rows: list[tuple[str, bool, datetime]]):
    c = await _connect()
    try:
        for outcome_id, success, created_at in rows:
            await c.execute(
                "INSERT INTO outcome_record(outcome_id,tenant_id,decision_id,success,created_at) "
                "VALUES($1,$2::uuid,$3,$4,$5)",
                outcome_id,
                tenant,
                decision,
                success,
                created_at,
            )
    finally:
        await c.close()


def _unordered_outcome_record_read() -> str:
    """The production outcome_record read (same SELECT, JOIN and WHERE) without its ORDER BY.

    Taken from persistence.py rather than copied, so the guard follows the production query."""
    block = _read_block()
    start = block.index('"""SELECT o.* FROM outcome_record o')
    sql = block[start + 3 : block.index('"""', start + 3)]
    return sql.split("ORDER BY", 1)[0].rstrip()


async def _unordered_first_success(tenant: str) -> bool:
    """First row of the unordered production read, under default planner settings."""
    c = await _connect()
    try:
        async with c.transaction():
            await c.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            for setting in ("enable_indexscan", "enable_bitmapscan", "enable_seqscan"):
                assert await c.fetchval(f"SHOW {setting}") == "on", f"{setting} is not default"
            row = await c.fetchrow(_unordered_outcome_record_read(), tenant, None, None)
            return bool(row["success"])
    finally:
        await c.close()


def _reconcile(tenant: str) -> dict:
    from outcome_reconcile import reconcile_outcomes
    from persistence import read_outcomes_for_reconcile

    orows, rrows = _run(read_outcomes_for_reconcile(tenant_id=tenant))
    return reconcile_outcomes(orows, rrows)


@pytest.mark.integration
@pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")
def test_latest_outcome_record_wins_even_when_inserted_last():
    tenant, decision = str(uuid4()), "dec_" + uuid4().hex[:12]
    # Older failure inserted first, newer success second: heap order puts the stale row first.
    _run(
        _seed_outcomes(
            tenant,
            decision,
            [
                ("out_" + uuid4().hex[:12], False, T0),
                ("out_" + uuid4().hex[:12], True, T0 + timedelta(days=3)),
            ],
        )
    )
    # Without this guard the test would pass with no ORDER BY whenever the planner reads
    # idx_outcome_record_tenant_decision, which returns the newest row first by itself.
    assert _run(_unordered_first_success(tenant)) is False, (
        "negative control lost: the unordered production read returned the newest row first, "
        "so this test no longer fails without the ORDER BY"
    )
    out = _reconcile(tenant)
    assert out["unique_decisions"] == 1, f"one decision expected: {out}"
    assert out["by_kind"] == {"success": 1, "failure": 0, "unknown": 0}, (
        f"the latest outcome (success, +3 days) must reconcile, not the older failure: {out}"
    )


@pytest.mark.integration
@pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")
def test_same_timestamp_ties_break_on_the_higher_outcome_id():
    tenant, decision = str(uuid4()), "dec_" + uuid4().hex[:12]
    _run(_seed_outcomes(tenant, decision, [("out_a", False, T0), ("out_b", True, T0)]))
    out = _reconcile(tenant)
    assert out["by_kind"] == {"success": 1, "failure": 0, "unknown": 0}, (
        f"on equal created_at the higher outcome_id (out_b, success) must win: {out}"
    )


@pytest.mark.integration
@pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")
def test_latest_recommendation_outcome_wins_even_when_inserted_last():
    """Every natural read order puts a stale row first; only the ORDER BY picks the latest.

    The table has an index on (tenant_id, recommendation_id), and a tenant-filtered read may
    use it, so a random recommendation_id made the unordered read return either row (the
    earlier version of this test passed 5 times in 6 against the unordered read). Here the
    stale rows sort first by every natural order: heap position (inserted first),
    recommendation_id (``rec_0…`` before ``rec_9…``) and outcome_id (BIGSERIAL, lower first).
    Their timestamps are explicit and distinct, and only the newest row is a success.
    """
    tenant, decision = str(uuid4()), "dec_" + uuid4().hex[:12]
    suffix = uuid4().hex[:8]
    # (recommendation_id, outcome, issued_at, outcome_recorded_at), stale first in every order.
    rows = [
        (f"rec_{i}_{suffix}", "failed", T0 + timedelta(days=i), T0 + timedelta(days=i, hours=1))
        for i in range(5)
    ]
    # The latest outcome by COALESCE(outcome_recorded_at, issued_at): issued before some stale
    # rows, recorded after all of them, so ordering by issued_at alone would not pick it either.
    rows.append((f"rec_9_{suffix}", "success", T0 + timedelta(days=1), T0 + timedelta(days=30)))

    async def seed() -> list[str]:
        c = await _connect()
        try:
            for rec_id, outcome, issued, recorded in rows:
                await c.execute(
                    "INSERT INTO recommendation_outcomes"
                    "(tenant_id,recommendation_id,decision_id,outcome,issued_at,outcome_recorded_at) "
                    "VALUES($1::uuid,$2,$3,$4,$5,$6)",
                    tenant,
                    rec_id,
                    decision,
                    outcome,
                    issued,
                    recorded,
                )
            # The production read (persistence.read_outcomes_for_reconcile) minus its ORDER BY,
            # forced onto each plan the planner may choose. Every plan must return a stale row
            # first; otherwise this test would no longer fail without the ORDER BY.
            firsts = []
            for setting in ("enable_indexscan", "enable_bitmapscan", "enable_seqscan"):
                async with c.transaction():
                    for other in ("enable_indexscan", "enable_bitmapscan", "enable_seqscan"):
                        value = "on" if other == setting else "off"
                        await c.execute(f"SET LOCAL {other} = {value}")
                    row = await c.fetchrow(
                        "SELECT * FROM recommendation_outcomes "
                        "WHERE tenant_id=$1::uuid AND ($2::text IS NULL OR field_id=$2) "
                        "AND ($3::text IS NULL OR season_id=$3)",
                        tenant,
                        None,
                        None,
                    )
                    firsts.append(row["outcome"])
            return firsts
        finally:
            await c.close()

    firsts = _run(seed())
    assert firsts == ["failed", "failed", "failed"], (
        f"negative control lost: an unordered read must return a stale row first: {firsts}"
    )
    out = _reconcile(tenant)
    assert out["unique_decisions"] == 1, f"one decision expected: {out}"
    assert out["by_kind"] == {"success": 1, "failure": 0, "unknown": 0}, (
        f"the latest recommendation outcome (success, recorded +30 days) must reconcile: {out}"
    )
