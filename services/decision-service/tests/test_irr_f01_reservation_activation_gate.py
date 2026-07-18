"""IRR-F01 Phase 1 — mandatory proof tests for the irr_f01_reservation activation gate, on real
Postgres.

Covers the eight required proofs: concurrent activation, TTL expiry, revoke, stale-evaluating
recovery, probe_only rejected from a normal role, enforcement cannot be bypassed, evidence-log
immutability, and CAS + activation_generation correctness.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
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

import activation_gate as gate  # noqa: E402


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
            "producer": "ci",
            "check_name": "ci_live_certification",
            "observed_at": datetime.now(UTC).isoformat(),
            "valid_until": future,
            "result": "pass",
            "provenance": "ci-run/654f897",
            "environment_id": env,
        },
        {
            "producer": "decision-service",
            "check_name": "consumer_heartbeat",
            "observed_at": datetime.now(UTC).isoformat(),
            "valid_until": future,
            "result": "pass",
            "provenance": "reservation_dispatch_inbox",
            "environment_id": env,
        },
    ]
    return items if complete else items[:1]


async def _store_evidence(env: str, items: list[dict]) -> list[str]:
    os.environ.setdefault("DEPLOY_BUILD_SHA", "d" * 40)
    os.environ.setdefault("ACTIVATION_EVIDENCE_SIGNING_KEY", "evidence-key")
    conn = await _connect()
    refs: list[str] = []
    try:
        from activation_gate_core import canonical_evidence_signature

        for item in items:
            signature = canonical_evidence_signature(
                "evidence-key",
                gate_name="irr_f01_reservation",
                producer=item["producer"],
                check_name=item["check_name"],
                environment_id=env,
                observed_at=item["observed_at"],
                valid_until=item["valid_until"],
                result=item["result"],
                provenance=item["provenance"],
                build_sha="d" * 40,
                payload={},
            )
            evidence_id = await conn.fetchval(
                """INSERT INTO activation_evidence_receipts
                   (gate_name,producer,check_name,environment_id,observed_at,valid_until,result,provenance,build_sha,payload,signature)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'{}'::jsonb,$10) RETURNING evidence_id""",
                "irr_f01_reservation",
                item["producer"],
                item["check_name"],
                env,
                datetime.fromisoformat(item["observed_at"]),
                datetime.fromisoformat(item["valid_until"]),
                item["result"],
                item["provenance"],
                "d" * 40,
                signature,
            )
            refs.append(str(evidence_id))
        return refs
    finally:
        await conn.close()


async def _enable(env: str, ttl: int = 3600) -> dict:
    began = await gate.begin_evaluation(env, actor="op")
    assert began["status"] == "evaluating"
    return await gate.complete_evaluation(
        env,
        expected_generation=began["generation"],
        evidence_refs=await _store_evidence(env, _evidence(env)),
        actor="op",
        ttl_seconds=ttl,
    )


# 1 — concurrent activation: two simultaneous begin_evaluation ⇒ exactly one wins.
def test_concurrent_activation_exactly_one_wins():
    async def go():
        env = _env()
        r1, r2 = await asyncio.gather(
            gate.begin_evaluation(env, actor="a"), gate.begin_evaluation(env, actor="b")
        )
        statuses = sorted([r1["status"], r2["status"]])
        assert statuses.count("evaluating") == 1
        assert statuses.count("conflict") == 1
        snap = await gate.current(env)
        assert snap["state"] == "evaluating" and snap["generation"] == 1

    _run(go())


# 2 — TTL expiry: enabled → past the horizon ⇒ not effective_enabled, enforce raises.
def test_ttl_expiry_disables_enforcement():
    async def go():
        env = _env()
        done = await _enable(env, ttl=3600)
        assert done["status"] == "enabled"
        assert (await gate.current(env))["effective_enabled"] is True
        # Simulate the TTL horizon passing (guard requires the generation to advance by 1).
        conn = await _connect()
        try:
            await conn.execute(
                "UPDATE irr_f01_reservation_activation "
                "SET state_expires_at = now() - interval '1 second', "
                "    activation_generation = activation_generation + 1 WHERE environment_id=$1",
                env,
            )
        finally:
            await conn.close()
        snap = await gate.current(env)
        assert snap["effective_enabled"] is False and snap["expired"] is True
        with pytest.raises(gate.ActivationNotEnabled) as ex:
            await gate.enforce_enabled(env)
        assert ex.value.reason == "ttl_expired"

    _run(go())


# 3 — revoke is monotonic; blocks evaluation until reset.
def test_revoke_then_reset_cycle():
    async def go():
        env = _env()
        await _enable(env)
        rv = await gate.revoke(env, actor="op", reason="incident")
        assert rv["status"] == "revoked"
        assert (await gate.current(env))["effective_enabled"] is False
        with pytest.raises(gate.ActivationNotEnabled):
            await gate.enforce_enabled(env)
        # cannot evaluate while revoked
        assert (await gate.begin_evaluation(env, actor="op"))["reason"] == "revoked"
        # reset re-opens the cycle
        assert (await gate.reset(env, actor="op"))["status"] == "disabled"
        assert (await gate.begin_evaluation(env, actor="op"))["status"] == "evaluating"

    _run(go())


# 4 — stale-evaluating recovery: recent evaluation is NOT recovered; a stale one IS.
def test_stale_evaluating_recovery():
    async def go():
        env = _env()
        await gate.begin_evaluation(env, actor="op")  # state=evaluating, fresh
        # A generous threshold must NOT reclaim a fresh evaluation.
        assert env not in await gate.recover_stale_evaluations(stale_seconds=3600)
        assert (await gate.current(env))["state"] == "evaluating"
        # Age it (guard: generation advances by 1).
        conn = await _connect()
        try:
            await conn.execute(
                "UPDATE irr_f01_reservation_activation "
                "SET evaluated_at = now() - interval '1 hour', "
                "    activation_generation = activation_generation + 1 WHERE environment_id=$1",
                env,
            )
        finally:
            await conn.close()
        recovered = await gate.recover_stale_evaluations(stale_seconds=60)
        assert env in recovered
        assert (await gate.current(env))["state"] == "disabled"

    _run(go())


# 5 — probe_only requires the probe role AND a valid signature.
def test_probe_rejected_from_normal_role_and_bad_signature():
    async def go():
        env = _env()
        await _enable(env)
        sig = gate.probe_signature(env, secret="k")
        with pytest.raises(gate.ActivationProbeDenied):
            await gate.probe_state(env, caller_role="user", signature=sig, secret="k")
        with pytest.raises(gate.ActivationProbeDenied):
            await gate.probe_state(
                env, caller_role=gate.PROBE_ROLE, signature="deadbeef", secret="k"
            )
        ok = await gate.probe_state(env, caller_role=gate.PROBE_ROLE, signature=sig, secret="k")
        assert ok["effective_enabled"] is True

    _run(go())


# 6 — enforcement cannot be bypassed: only a real enabled+valid state passes; nothing else does.
def test_enforcement_is_the_only_gate():
    async def go():
        env = _env()
        with pytest.raises(gate.ActivationNotEnabled):  # disabled
            await gate.enforce_enabled(env)
        await gate.begin_evaluation(env, actor="op")
        with pytest.raises(gate.ActivationNotEnabled):  # evaluating, not enabled
            await gate.enforce_enabled(env)
        # degraded (incomplete evidence) must NOT enable.
        began_gen = (await gate.current(env))["generation"]
        deg = await gate.complete_evaluation(
            env,
            expected_generation=began_gen,
            evidence_refs=await _store_evidence(env, _evidence(env, complete=False)),
            actor="op",
            ttl_seconds=3600,
        )
        assert deg["status"] == "degraded"
        with pytest.raises(gate.ActivationNotEnabled):
            await gate.enforce_enabled(env)

    _run(go())


# 7 — the evidence/transition log is append-only.
def test_evidence_log_is_append_only():
    async def go():
        env = _env()
        await _enable(env)
        conn = await _connect()
        try:
            import asyncpg

            for sql in (
                "UPDATE irr_f01_reservation_activation_events SET reason='x' WHERE environment_id=$1",
                "DELETE FROM irr_f01_reservation_activation_events WHERE environment_id=$1",
            ):
                with pytest.raises(asyncpg.PostgresError):
                    await conn.execute(sql, env)
        finally:
            await conn.close()

    _run(go())


# 8 — CAS + activation_generation: monotonic by 1; stale expected_generation is refused; the DB
# guard rejects a generation jump and an environment rebind.
def test_cas_and_generation_correctness():
    async def go():
        env = _env()
        began = await gate.begin_evaluation(env, actor="op")  # gen 1
        assert began["generation"] == 1
        # One stored receipt set is reused: the semantic UNIQUE index means the same producer/check/
        # env/provenance/build is a single receipt, referenced by UUID across attempts.
        refs = await _store_evidence(env, _evidence(env))
        # A completion with a stale expected generation is a CAS conflict (no-op).
        stale = await gate.complete_evaluation(
            env, expected_generation=0, evidence_refs=refs, actor="op", ttl_seconds=60
        )
        assert stale["status"] == "conflict" and stale["reason"] == "cas_conflict"
        done = await gate.complete_evaluation(
            env, expected_generation=1, evidence_refs=refs, actor="op", ttl_seconds=60
        )
        assert done["status"] == "enabled" and done["generation"] == 2
        # DB guard: generation may only advance by exactly 1, env is immutable.
        conn = await _connect()
        try:
            import asyncpg

            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "UPDATE irr_f01_reservation_activation "
                    "SET activation_generation = activation_generation + 2 WHERE environment_id=$1",
                    env,
                )
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "UPDATE irr_f01_reservation_activation "
                    "SET environment_id='rebound', activation_generation=activation_generation+1 "
                    "WHERE environment_id=$1",
                    env,
                )
        finally:
            await conn.close()

    _run(go())
