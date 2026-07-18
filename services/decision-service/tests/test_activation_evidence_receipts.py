"""Gate-Trust-1 (P0) — behavioral proof that the receipt store is the non-spoofable root of trust.

Every one of the operator's ratified reject cases is meaningful ONLY because the caller submits
references and the gate resolves them server-side: unknown / wrong-gate / wrong-environment /
revoked / expired / not-pass receipts are rejected, unknown-producer / unsupported-check are
rejected at ingest, a missing required check degrades, and raw caller evidence is structurally
forbidden (422). Runs on real Postgres.
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

import activation_gate as irr  # noqa: E402
import satellite_cdse_activation_gate as sat  # noqa: E402


def _run(c):
    return asyncio.run(c)


def _env() -> str:
    return "env-" + uuid4().hex[:12]


def _future() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat()


def _past() -> str:
    return (datetime.now(UTC) - timedelta(seconds=5)).isoformat()


async def _issue(gate, env, check, *, producer, result="pass", valid_until=None) -> str:
    r = await gate.record_receipt(
        environment_id=env,
        producer=producer,
        check_name=check,
        result=result,
        observed_at=_future(),
        valid_until=valid_until or _future(),
    )
    assert r["status"] == "recorded", r
    return r["receipt_id"]


async def _both_irr(env) -> list[str]:
    return [
        await _issue(irr, env, "ci_live_certification", producer="ci"),
        await _issue(irr, env, "consumer_heartbeat", producer="decision-service"),
    ]


async def _begin_complete(gate, env, refs):
    began = await gate.begin_evaluation(env, actor="op")
    return await gate.complete_evaluation(
        env,
        expected_generation=began["generation"],
        evidence_refs=refs,
        actor="op",
        ttl_seconds=3600,
    )


def test_valid_receipts_enable_others_never_do():
    async def go():
        env = _env()
        res = await _begin_complete(irr, env, await _both_irr(env))
        assert res["status"] == "enabled" and not res["rejected_receipts"]

    _run(go())


def test_unknown_receipt_is_rejected():
    async def go():
        env = _env()
        res = await _begin_complete(irr, env, [str(uuid4()), "not-even-a-uuid"])
        assert res["status"] == "degraded"
        reasons = {r["reason"] for r in res["rejected_receipts"]}
        assert reasons == {"unknown_receipt", "invalid_receipt_id"}

    _run(go())


def test_wrong_gate_receipt_is_rejected():
    async def go():
        env = _env()
        # A receipt issued to satellite_cdse cannot enable irr_f01_reservation.
        cross = await _issue(sat, env, "cdse_live_probe", producer="raster-service")
        res = await _begin_complete(irr, env, [cross])
        assert res["status"] == "degraded"
        assert res["rejected_receipts"][0]["reason"] == "wrong_gate"

    _run(go())


def test_wrong_environment_receipt_is_rejected():
    async def go():
        env_a, env_b = _env(), _env()
        rid = await _issue(irr, env_a, "ci_live_certification", producer="ci")
        res = await _begin_complete(irr, env_b, [rid])
        assert res["status"] == "degraded"
        assert res["rejected_receipts"][0]["reason"] == "wrong_environment"

    _run(go())


def test_revoked_receipt_is_rejected():
    async def go():
        env = _env()
        refs = await _both_irr(env)
        conn = await _connect()
        try:
            await conn.execute(
                "UPDATE activation_evidence_receipts SET revoked=true, revoked_at=now(), "
                "revoked_reason='incident' WHERE receipt_id=$1::uuid",
                refs[0],
            )
        finally:
            await conn.close()
        res = await _begin_complete(irr, env, refs)
        assert res["status"] == "degraded"
        assert any(r["reason"] == "revoked" for r in res["rejected_receipts"])

    _run(go())


def test_expired_receipt_is_rejected():
    async def go():
        env = _env()
        good = await _issue(irr, env, "ci_live_certification", producer="ci")
        stale = await _issue(
            irr, env, "consumer_heartbeat", producer="decision-service", valid_until=_past()
        )
        res = await _begin_complete(irr, env, [good, stale])
        assert res["status"] == "degraded"
        assert any(r["reason"] == "expired" for r in res["rejected_receipts"])

    _run(go())


def test_fail_result_receipt_is_rejected():
    async def go():
        env = _env()
        good = await _issue(irr, env, "ci_live_certification", producer="ci")
        failing = await _issue(
            irr, env, "consumer_heartbeat", producer="decision-service", result="fail"
        )
        res = await _begin_complete(irr, env, [good, failing])
        assert res["status"] == "degraded"
        assert any(r["reason"] == "not_pass" for r in res["rejected_receipts"])

    _run(go())


def test_ingest_rejects_unknown_producer_and_unsupported_check():
    async def go():
        env = _env()
        bad_producer = await irr.record_receipt(
            environment_id=env,
            producer="attacker",
            check_name="ci_live_certification",
            result="pass",
            observed_at=_future(),
            valid_until=_future(),
        )
        assert bad_producer == {"status": "rejected", "reason": "unknown_producer"}
        bad_check = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="something_made_up",
            result="pass",
            observed_at=_future(),
            valid_until=_future(),
        )
        assert bad_check == {"status": "rejected", "reason": "unsupported_check"}

    _run(go())


def test_missing_required_check_degrades():
    async def go():
        env = _env()
        only_one = [await _issue(irr, env, "ci_live_certification", producer="ci")]
        res = await _begin_complete(irr, env, only_one)
        assert res["status"] == "degraded" and "missing_checks" not in res  # reason on the event

    _run(go())


def test_idempotent_ingest_returns_same_receipt():
    async def go():
        env = _env()
        a = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at="2026-07-18T00:00:00Z",
            valid_until="2026-07-18T06:00:00Z",
        )
        b = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at="2026-07-18T00:00:00Z",
            valid_until="2026-07-18T06:00:00Z",
        )
        assert a["receipt_id"] == b["receipt_id"] and a["content_hash"] == b["content_hash"]

    _run(go())


def test_receipts_are_append_only():
    async def go():
        import asyncpg

        env = _env()
        rid = await _issue(irr, env, "ci_live_certification", producer="ci")
        conn = await _connect()
        try:
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "UPDATE activation_evidence_receipts SET result='fail' WHERE receipt_id=$1::uuid",
                    rid,
                )
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "DELETE FROM activation_evidence_receipts WHERE receipt_id=$1::uuid", rid
                )
        finally:
            await conn.close()

    _run(go())


def test_raw_caller_evidence_is_forbidden_over_http(monkeypatch):
    env = _env()
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env)
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    import main
    from fastapi.testclient import TestClient

    c = TestClient(main.app)
    h = {"X-Requested-By": "operator"}
    gen = c.post("/v1/activation/irr_f01_reservation/begin", headers=h).json()["generation"]
    # A caller trying to smuggle fabricated evidence results is rejected (422), not silently ignored.
    forged = c.post(
        "/v1/activation/irr_f01_reservation/complete",
        headers=h,
        json={
            "expected_generation": gen,
            "evidence_refs": [],
            "evidence": [
                {"producer": "ci", "check_name": "ci_live_certification", "result": "pass"}
            ],
            "ttl_seconds": 3600,
        },
    )
    assert forged.status_code == 422


def test_external_producer_signature_required_in_production(monkeypatch):
    import hashlib
    import hmac

    from activation_gate_core import _parse_ts

    async def go():
        env = _env()
        monkeypatch.setenv("ACTIVATION_REQUIRE_PRODUCTION_HARDENING", "1")
        monkeypatch.setenv("ACTIVATION_EVIDENCE_SIGNING_KEY_CI", "ci-key")
        obs, val = "2026-07-18T00:00:00+00:00", "2026-07-18T06:00:00+00:00"
        # An unsigned CI receipt is rejected in the production profile (CI is external).
        unsigned = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at=obs,
            valid_until=val,
        )
        assert unsigned == {"status": "rejected", "reason": "invalid_signature"}
        # A correctly signed receipt is recorded.
        content_hash = irr._CORE._receipt_content_hash(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at=_parse_ts(obs).isoformat(),
            valid_until=_parse_ts(val).isoformat(),
            provenance=None,
            build_sha=None,
        )
        sig = hmac.new(b"ci-key", content_hash.encode(), hashlib.sha256).hexdigest()
        signed = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at=obs,
            valid_until=val,
            signature=sig,
        )
        assert signed["status"] == "recorded"

    _run(go())


def test_internal_producer_needs_no_signature_in_production(monkeypatch):
    async def go():
        env = _env()
        monkeypatch.setenv("ACTIVATION_REQUIRE_PRODUCTION_HARDENING", "1")
        # decision-service is internal (relies on service identity), so no signature required.
        r = await irr.record_receipt(
            environment_id=env,
            producer="decision-service",
            check_name="consumer_heartbeat",
            result="pass",
            observed_at=_future(),
            valid_until=_future(),
        )
        assert r["status"] == "recorded"

    _run(go())


def test_external_producer_needs_no_signature_in_development(monkeypatch):
    async def go():
        env = _env()
        monkeypatch.delenv("ACTIVATION_REQUIRE_PRODUCTION_HARDENING", raising=False)
        monkeypatch.setenv("SAHOOL_ENV", "development")
        r = await irr.record_receipt(
            environment_id=env,
            producer="ci",
            check_name="ci_live_certification",
            result="pass",
            observed_at=_future(),
            valid_until=_future(),
        )
        assert r["status"] == "recorded"

    _run(go())


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)
