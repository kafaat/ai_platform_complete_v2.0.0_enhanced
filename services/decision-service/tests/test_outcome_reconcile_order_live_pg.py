"""Which outcome reconciles must not depend on heap order (exploration bug, outcome_reconcile).

``reconcile_outcomes`` keeps the first row it sees per ``decision_id``. Before this fix
``read_outcomes_for_reconcile`` read both outcome tables without ``ORDER BY``, so the winning
outcome for a decision with several rows was whatever order PostgreSQL returned the heap in.
The intended semantics are latest-first, by time then id.

The live tests insert the OLDER row first, so plain heap order returns it first: without the
``ORDER BY`` the stale outcome wins and the tests fail (negative control recorded in the commit).
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
    tenant, decision = str(uuid4()), "dec_" + uuid4().hex[:12]

    async def seed():
        c = await _connect()
        try:
            for outcome, issued in (("failed", T0), ("success", T0 + timedelta(days=2))):
                await c.execute(
                    "INSERT INTO recommendation_outcomes"
                    "(tenant_id,recommendation_id,decision_id,outcome,issued_at) "
                    "VALUES($1::uuid,$2,$3,$4,$5)",
                    tenant,
                    "rec_" + uuid4().hex[:12],
                    decision,
                    outcome,
                    issued,
                )
        finally:
            await c.close()

    _run(seed())
    out = _reconcile(tenant)
    assert out["by_kind"] == {"success": 1, "failure": 0, "unknown": 0}, (
        f"the latest recommendation outcome (success, +2 days) must reconcile: {out}"
    )
