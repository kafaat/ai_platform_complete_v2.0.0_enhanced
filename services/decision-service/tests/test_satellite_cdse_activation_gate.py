"""Phase 2 — mandatory proof tests for the satellite_cdse activation gate, on real Postgres.

Same eight proofs as gate 1, but enforcement is a SOURCE SELECTION (cdse when enabled, else the
element84 fallback) rather than a refusal — the deliberate variation that informs Phase 3.
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
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")

import satellite_cdse_activation_gate as gate  # noqa: E402


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _env() -> str:
    return "env-" + uuid4().hex[:12]


def _evidence(env: str, *, complete: bool = True) -> list[dict]:
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    items = [
        {
            "producer": "raster-service",
            "check_name": "cdse_credentials_present",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/cdse_client",
            "environment_id": env,
        },
        {
            "producer": "raster-service",
            "check_name": "cdse_live_probe",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/stac_search",
            "environment_id": env,
        },
    ]
    return items if complete else items[:1]


async def _ingest(env: str, *, complete: bool = True) -> list[str]:
    """Gate-Trust-1: producers issue receipts server-side; the operator references them by id."""
    ids = []
    for item in _evidence(env, complete=complete):
        r = await gate.record_receipt(
            environment_id=env,
            producer=item["producer"],
            check_name=item["check_name"],
            result=item["result"],
            observed_at=item["observed_at"],
            valid_until=item["valid_until"],
            provenance=item.get("provenance"),
        )
        assert r["status"] == "recorded"
        ids.append(r["receipt_id"])
    return ids


async def _enable(env: str, ttl: int = 3600) -> dict:
    began = await gate.begin_evaluation(env, actor="op")
    assert began["status"] == "evaluating"
    return await gate.complete_evaluation(
        env,
        expected_generation=began["generation"],
        evidence_refs=await _ingest(env),
        actor="op",
        ttl_seconds=ttl,
    )


def test_concurrent_activation_exactly_one_wins():
    async def go():
        env = _env()
        r1, r2 = await asyncio.gather(
            gate.begin_evaluation(env, actor="a"), gate.begin_evaluation(env, actor="b")
        )
        statuses = sorted([r1["status"], r2["status"]])
        assert statuses.count("evaluating") == 1 and statuses.count("conflict") == 1

    _run(go())


def test_ttl_expiry_falls_back_to_element84():
    async def go():
        env = _env()
        assert (await _enable(env, ttl=3600))["status"] == "enabled"
        assert (await gate.active_imagery_source(env))["source"] == "cdse"
        conn = await _connect()
        try:
            await conn.execute(
                "UPDATE satellite_cdse_activation SET state_expires_at = now() - interval '1 second', "
                "activation_generation = activation_generation + 1 WHERE environment_id=$1",
                env,
            )
        finally:
            await conn.close()
        src = await gate.active_imagery_source(env)
        assert (
            src["source"] == "element84"
            and src["fallback"] is True
            and src["reason"] == "ttl_expired"
        )

    _run(go())


def test_revoke_then_reset_cycle():
    async def go():
        env = _env()
        await _enable(env)
        assert (await gate.revoke(env, actor="op", reason="incident"))["status"] == "revoked"
        assert (await gate.active_imagery_source(env))["source"] == "element84"
        assert (await gate.begin_evaluation(env, actor="op"))["reason"] == "revoked"
        assert (await gate.reset(env, actor="op"))["status"] == "disabled"
        assert (await gate.begin_evaluation(env, actor="op"))["status"] == "evaluating"

    _run(go())


def test_stale_evaluating_recovery():
    async def go():
        env = _env()
        await gate.begin_evaluation(env, actor="op")
        assert env not in await gate.recover_stale_evaluations(stale_seconds=3600)
        conn = await _connect()
        try:
            await conn.execute(
                "UPDATE satellite_cdse_activation SET evaluated_at = now() - interval '1 hour', "
                "activation_generation = activation_generation + 1 WHERE environment_id=$1",
                env,
            )
        finally:
            await conn.close()
        assert env in await gate.recover_stale_evaluations(stale_seconds=60)
        assert (await gate.current(env))["state"] == "disabled"

    _run(go())


def test_probe_rejected_from_normal_role_and_bad_signature():
    async def go():
        env = _env()
        await _enable(env)
        sig = gate.probe_signature(env, secret="k")
        with pytest.raises(gate.ActivationProbeDenied):
            await gate.probe_state(env, caller_role="user", signature=sig, secret="k")
        with pytest.raises(gate.ActivationProbeDenied):
            await gate.probe_state(env, caller_role=gate.PROBE_ROLE, signature="beef", secret="k")
        ok = await gate.probe_state(env, caller_role=gate.PROBE_ROLE, signature=sig, secret="k")
        assert ok["effective_enabled"] is True

    _run(go())


def test_source_selection_is_the_enforcement():
    async def go():
        env = _env()
        # disabled ⇒ fallback
        assert (await gate.active_imagery_source(env))["source"] == "element84"
        # incomplete evidence ⇒ degraded ⇒ still fallback (CDSE not trusted)
        began = await gate.begin_evaluation(env, actor="op")
        deg = await gate.complete_evaluation(
            env,
            expected_generation=began["generation"],
            evidence_refs=await _ingest(env, complete=False),
            actor="op",
            ttl_seconds=3600,
        )
        assert deg["status"] == "degraded"
        assert (await gate.active_imagery_source(env))["source"] == "element84"

    _run(go())


def test_evidence_log_is_append_only():
    async def go():
        env = _env()
        await _enable(env)
        conn = await _connect()
        try:
            import asyncpg

            for sql in (
                "UPDATE satellite_cdse_activation_events SET reason='x' WHERE environment_id=$1",
                "DELETE FROM satellite_cdse_activation_events WHERE environment_id=$1",
            ):
                with pytest.raises(asyncpg.PostgresError):
                    await conn.execute(sql, env)
        finally:
            await conn.close()

    _run(go())


def test_cas_and_generation_correctness():
    async def go():
        env = _env()
        began = await gate.begin_evaluation(env, actor="op")
        assert began["generation"] == 1
        refs = await _ingest(env)
        stale = await gate.complete_evaluation(
            env, expected_generation=0, evidence_refs=refs, actor="op", ttl_seconds=60
        )
        assert stale["status"] == "conflict" and stale["reason"] == "cas_conflict"
        done = await gate.complete_evaluation(
            env, expected_generation=1, evidence_refs=refs, actor="op", ttl_seconds=60
        )
        assert done["status"] == "enabled" and done["generation"] == 2
        conn = await _connect()
        try:
            import asyncpg

            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "UPDATE satellite_cdse_activation "
                    "SET activation_generation = activation_generation + 2 WHERE environment_id=$1",
                    env,
                )
        finally:
            await conn.close()

    _run(go())
