"""Gate-Trust canonical contract — the stored producer-signed receipt is the ONLY trust root.

These certify the reject side of the contract against real Postgres, over the HTTP surface:

  * a caller submits UUID references only — raw inline evidence is forbidden by the model;
  * an unknown / wrong-gate / non-UUID reference is a rejection, never a silent enable;
  * a receipt that resolves but is not admissible (wrong env, expired, not 'pass') degrades,
    it does not enable;
  * a stored signature that fails re-verification is rejected at resolve time;
  * the receipts table is append-only;
  * REVOCATION (the kill switch): a valid receipt admits; after an append-only revocation row is
    inserted the SAME evidence_id is rejected; a duplicate revocation is a conflict; and the
    revocations table is itself append-only (UPDATE/DELETE raise).
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

GATE = "irr_f01_reservation"


def _client(monkeypatch, env_id: str):
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env_id)
    monkeypatch.setenv("ACTIVATION_PROBE_SIGNING_KEY", "probe-key")
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "d" * 40)
    monkeypatch.setenv("ACTIVATION_EVIDENCE_SIGNING_KEY", "evidence-key")
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    import main
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _evidence(
    env_id: str, *, complete: bool = True, result: str = "pass", env_override: str | None = None
) -> list[dict]:
    observed = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    env = env_override or env_id
    items = [
        {
            "producer": "ci",
            "check_name": "ci_live_certification",
            "observed_at": observed,
            "valid_until": future,
            "result": result,
            "provenance": "ci",
            "environment_id": env,
        },
        {
            "producer": "decision-service",
            "check_name": "consumer_heartbeat",
            "observed_at": observed,
            "valid_until": future,
            "result": result,
            "provenance": "inbox",
            "environment_id": env,
        },
    ]
    return items if complete else items[:1]


def _store(client, items: list[dict], gate_name: str = GATE) -> list[str]:
    from activation_gate_core import canonical_evidence_signature

    refs = []
    for item in items:
        body = {**item, "gate_name": gate_name, "build_sha": "d" * 40, "payload": {}}
        body["signature"] = canonical_evidence_signature("evidence-key", **body)
        r = client.post("/v1/activation/evidence-receipts", json=body)
        assert r.status_code == 201, r.text
        refs.append(r.json()["evidence_id"])
    return refs


def _enable(client, env_id: str, refs: list[str]) -> dict:
    h = {"X-Requested-By": "operator"}
    gen = client.post(f"/v1/activation/{GATE}/begin", headers=h).json()["generation"]
    r = client.post(
        f"/v1/activation/{GATE}/complete",
        headers=h,
        json={"expected_generation": gen, "evidence_refs": refs, "ttl_seconds": 3600},
    )
    return r


async def _exec(sql: str, *args):
    import asyncpg

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        return await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _insert_receipt_directly(
    stored_env: str, *, signature: str | None, expired: bool = False
) -> str:
    """Insert a receipt straight into the store, bypassing the ingest endpoint. Used to prove the
    gate re-verifies at resolve (a forged signature) and applies admissibility (a wrong-env or
    expired receipt that ingest would never accept). When ``signature`` is None a VALID one is
    computed; ``expired`` places the whole validity window in the past."""
    import asyncpg
    from activation_gate_core import canonical_evidence_signature

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        now = datetime.now(UTC)
        if expired:
            observed, valid_until = now - timedelta(hours=2), now - timedelta(hours=1)
        else:
            observed, valid_until = now - timedelta(minutes=1), now + timedelta(hours=1)
        sig = signature or canonical_evidence_signature(
            "evidence-key",
            gate_name=GATE,
            producer="ci",
            check_name="ci_live_certification",
            environment_id=stored_env,
            observed_at=observed,
            valid_until=valid_until,
            result="pass",
            provenance="ci",
            build_sha="d" * 40,
            payload={},
        )
        eid = await conn.fetchval(
            """INSERT INTO activation_evidence_receipts
               (gate_name,producer,check_name,environment_id,observed_at,valid_until,result,provenance,build_sha,payload,signature)
               VALUES ($1,'ci','ci_live_certification',$2,$3,$4,'pass','ci',$5,'{}'::jsonb,$6)
               RETURNING evidence_id""",
            GATE,
            stored_env,
            observed,
            valid_until,
            "d" * 40,
            sig,
        )
        return str(eid)
    finally:
        await conn.close()


# ---- raw-evidence-forbidden + malformed reference -------------------------------------------
def test_raw_inline_evidence_is_forbidden(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}
    gen = c.post(f"/v1/activation/{GATE}/begin", headers=h).json()["generation"]
    # The OLD spoofable contract: inline evidence=[...]. extra="forbid" ⇒ 422, never accepted.
    r = c.post(
        f"/v1/activation/{GATE}/complete",
        headers=h,
        json={"expected_generation": gen, "evidence": _evidence(env_id), "ttl_seconds": 3600},
    )
    assert r.status_code == 422, r.text


def test_non_uuid_reference_is_rejected(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}
    gen = c.post(f"/v1/activation/{GATE}/begin", headers=h).json()["generation"]
    r = c.post(
        f"/v1/activation/{GATE}/complete",
        headers=h,
        json={"expected_generation": gen, "evidence_refs": ["not-a-uuid"], "ttl_seconds": 3600},
    )
    assert r.status_code == 422, r.text


# ---- unknown / wrong-gate references ⇒ 400 (never enable) -----------------------------------
def test_unknown_reference_is_rejected(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    r = _enable(c, env_id, [str(uuid4()), str(uuid4())])
    assert r.status_code == 400 and r.json()["detail"] == "evidence_reference_not_found"


def test_wrong_gate_reference_is_rejected(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # Stored under a DIFFERENT gate ⇒ not resolvable from this gate ⇒ 400.
    refs = _store(c, _evidence(env_id), gate_name="satellite_cdse")
    r = _enable(c, env_id, refs)
    assert r.status_code == 400 and r.json()["detail"] == "evidence_reference_not_found"


# ---- admissibility failures ⇒ degraded (resolve OK, but not trustworthy to ENABLE) ----------
def test_wrong_environment_receipt_rejected_at_ingest(monkeypatch):
    from activation_gate_core import canonical_evidence_signature

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # A receipt whose environment_id != the gate environment is refused at ingest (400) — it can
    # never even be stored, a stronger guarantee than admissibility alone.
    item = _evidence(env_id, env_override="some-other-env")[0]
    body = {**item, "gate_name": GATE, "build_sha": "d" * 40, "payload": {}}
    body["signature"] = canonical_evidence_signature("evidence-key", **body)
    r = c.post("/v1/activation/evidence-receipts", json=body)
    assert r.status_code == 400 and "environment" in r.json()["detail"]


def test_wrong_environment_receipt_does_not_enable_even_if_stored(monkeypatch):
    # Defense in depth: even a correctly-signed receipt for another environment that reaches the store
    # by bypassing ingest is resolved (signature valid) but NOT admissible ⇒ degraded, never enabled.
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # A DISTINCT random other-env keeps the semantic UNIQUE key unique across runs.
    eid = asyncio.run(_insert_receipt_directly("other-" + uuid4().hex[:10], signature=None))
    r = _enable(c, env_id, [eid])
    assert r.status_code == 200 and r.json()["status"] == "degraded"


def test_expired_receipt_rejected_at_ingest(monkeypatch):
    from activation_gate_core import canonical_evidence_signature

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # observed_at in the past, valid_until already elapsed (still valid_until > observed_at, so the
    # window CHECK holds) ⇒ ingest refuses an already-expired receipt (400).
    observed = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    elapsed = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    item = {
        "producer": "ci",
        "check_name": "ci_live_certification",
        "observed_at": observed,
        "valid_until": elapsed,
        "result": "pass",
        "provenance": "ci",
        "environment_id": env_id,
    }
    body = {**item, "gate_name": GATE, "build_sha": "d" * 40, "payload": {}}
    body["signature"] = canonical_evidence_signature("evidence-key", **body)
    r = c.post("/v1/activation/evidence-receipts", json=body)
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_expired_receipt_does_not_enable_even_if_stored(monkeypatch):
    # Defense in depth: an expired receipt that reaches the store by bypassing ingest is resolved
    # (signature valid) but NOT admissible (valid_until <= now) ⇒ degraded, never enabled.
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    eid = asyncio.run(_insert_receipt_directly(env_id, signature=None, expired=True))
    r = _enable(c, env_id, [eid])
    assert r.status_code == 200 and r.json()["status"] == "degraded"


def test_not_pass_result_degrades(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    refs = _store(c, _evidence(env_id, result="fail"))
    r = _enable(c, env_id, refs)
    assert r.status_code == 200 and r.json()["status"] == "degraded"


# ---- forged stored signature ⇒ rejected at resolve time ------------------------------------
def test_stored_signature_is_reverified(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # A row with a valid-format but WRONG signature (inserted directly, as a forgery would be).
    eid = asyncio.run(_insert_receipt_directly(env_id, signature="0" * 64))
    r = _enable(c, env_id, [eid])
    assert r.status_code == 400 and r.json()["detail"] == "evidence_signature_invalid"


# ---- receipts table is append-only ---------------------------------------------------------
def test_receipts_are_append_only(monkeypatch):
    import asyncpg

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    eid = _store(c, _evidence(env_id, complete=False))[0]
    for sql in (
        "UPDATE activation_evidence_receipts SET result='fail' WHERE evidence_id=$1",
        "DELETE FROM activation_evidence_receipts WHERE evidence_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            asyncio.run(_exec(sql, __import__("uuid").UUID(eid)))


# ---- revocation kill-switch: 4 behavioral cases --------------------------------------------
def test_revocation_admit_then_reject_then_conflict_then_append_only(monkeypatch):
    from uuid import UUID

    import asyncpg

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}

    refs = _store(c, _evidence(env_id))
    # (a) valid receipt ⇒ admit (enable).
    assert _enable(c, env_id, refs).json()["status"] == "enabled"

    # revoke the FIRST receipt through the actor-authed endpoint.
    revoke_url = f"/v1/activation/evidence-receipts/{refs[0]}/revoke"
    # actor identity is required.
    assert c.post(revoke_url, json={"reason": "incident"}).status_code == 400
    first = c.post(revoke_url, headers=h, json={"reason": "incident"})
    assert first.status_code == 201 and first.json()["status"] == "revoked"

    # (c) duplicate revocation ⇒ conflict (UNIQUE(evidence_id)).
    dup = c.post(revoke_url, headers=h, json={"reason": "again"})
    assert dup.status_code == 409

    # (b) after revocation, the SAME evidence_id is unresolvable ⇒ a new completion is rejected.
    c.post(f"/v1/activation/{GATE}/reset", headers=h)
    rejected = _enable(c, env_id, refs)
    assert (
        rejected.status_code == 400 and rejected.json()["detail"] == "evidence_reference_not_found"
    )

    # (d) the revocations table is itself append-only.
    for sql in (
        "UPDATE activation_evidence_revocations SET reason='x' WHERE evidence_id=$1",
        "DELETE FROM activation_evidence_revocations WHERE evidence_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            asyncio.run(_exec(sql, UUID(refs[0])))


def test_revoke_unknown_receipt_is_404(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    r = c.post(
        f"/v1/activation/evidence-receipts/{uuid4()}/revoke",
        headers={"X-Requested-By": "operator"},
        json={"reason": "x"},
    )
    assert r.status_code == 404
