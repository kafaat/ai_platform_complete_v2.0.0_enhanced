"""Snapshot ids are validated before storage (exploration bug: stored without checks).

Before this, decision-service stored every snapshot id exactly as the caller sent it:

* ``POST /v1/evidence/vegetation-snapshots`` accepted any client-named ``snapshot_id``; since
  that id is the table's GLOBAL primary key while RLS hides other tenants' rows, an id already
  used by another tenant (or by other evidence of the same tenant) surfaced as an unhandled
  unique violation (500) instead of a named refusal;
* ``weather_snapshot_id`` / ``resource_snapshot_id`` (dispatch authorization) and
  ``evidence_snapshot_id`` (outcome verification, learning attribution, learning updates) took
  any string;
* an outcome or a learning update could name a ``veg_`` evidence snapshot that did not exist,
  belonged to another tenant, or showed another field, and it became learning ground truth.

Unit tests drive the HTTP edge with persistence replaced at the function level (no database).
Live tests (``DATABASE_URL``, decision-service migrations) prove the database-backed refusals.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

DB = os.getenv("DATABASE_URL", "").strip()
TENANT_A = "00000000-0000-0000-0000-00000000a5a1"
TENANT_B = "00000000-0000-0000-0000-00000000b5b2"
HEADERS = {"X-Tenant-Id": TENANT_A}

_spec = importlib.util.spec_from_file_location(
    "decision_snapshot_ids_main", SERVICE_DIR / "main.py"
)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)
client = TestClient(mod.app, raise_server_exceptions=False)

MALFORMED = ["", " w1", "w 1", "w1\n", "سهول", "a" * 201, "veg_x", "-leading-dash"]
WELL_FORMED = ["w1", "wsnap/sha1/1:deadbeefcafef00d", "hop/station-7/day-100", "ci-weather"]


def _run(coro):
    return asyncio.run(coro)


def _refuse_persistence(monkeypatch):
    calls: list[str] = []

    async def must_not_run(**kwargs):
        calls.append("called")
        return {"status": "ok"}

    for name in (
        "persist_vegetation_snapshot",
        "authorize_dispatch",
        "verify_execution_outcome",
        "create_learning_attribution",
    ):
        monkeypatch.setattr(mod, name, must_not_run)
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    return calls


# ── format: pure ────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("value", MALFORMED)
def test_malformed_snapshot_references_are_named(value):
    assert persistence.snapshot_reference_format_error(value) == "invalid_snapshot_id", (
        f"{value!r} must be refused as invalid_snapshot_id"
    )


@pytest.mark.unit
@pytest.mark.parametrize("value", WELL_FORMED + ["veg_" + "a" * 20, "ev-1", "e"])
def test_well_formed_snapshot_references_pass(value):
    assert persistence.snapshot_reference_format_error(value) is None, f"{value!r} is well formed"


# ── format: HTTP edge, nothing reaches persistence ──────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("field", ["weather_snapshot_id", "resource_snapshot_id"])
@pytest.mark.parametrize("value", [v for v in MALFORMED if v.strip()])
def test_dispatch_authorization_refuses_a_malformed_snapshot_id(monkeypatch, field, value):
    calls = _refuse_persistence(monkeypatch)
    body = {
        "decision_id": "d",
        "review_id": "r",
        "candidate_lineage_id": "l",
        "policy_version": "p1",
        "weather_snapshot_id": "w1",
        "resource_snapshot_id": "r1",
        "idempotency_key": "i",
        field: value,
    }
    r = client.post(
        "/v1/execution-plans/xplan_1/authorize-dispatch",
        json=body,
        headers={**HEADERS, "X-Authorized-By": "op"},
    )
    assert r.status_code == 422, f"{field}={value!r}: {r.status_code} {r.text}"
    assert r.json()["detail"] == {"code": "invalid_snapshot_id", "field": field}, r.text
    assert calls == [], "a malformed id must be refused before persistence"


@pytest.mark.unit
@pytest.mark.parametrize("value", WELL_FORMED)
def test_dispatch_authorization_passes_a_well_formed_snapshot_id(monkeypatch, value):
    seen: dict = {}

    async def fake_authorize(**kwargs):
        seen.update(kwargs)
        return {"status": "conflict", "reason": "stub"}

    monkeypatch.setattr(mod, "authorize_dispatch", fake_authorize)
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    body = {
        "decision_id": "d",
        "review_id": "r",
        "candidate_lineage_id": "l",
        "policy_version": "p1",
        "weather_snapshot_id": value,
        "resource_snapshot_id": "r1",
        "idempotency_key": "i",
    }
    r = client.post(
        "/v1/execution-plans/xplan_1/authorize-dispatch",
        json=body,
        headers={**HEADERS, "X-Authorized-By": "op"},
    )
    assert r.status_code == 409, f"stubbed persistence answers conflict: {r.status_code} {r.text}"
    assert seen["payload"].weather_snapshot_id == value, "the id must reach persistence unchanged"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["w 1", "veg_x", "a" * 201])
def test_outcome_verification_refuses_a_malformed_evidence_id(monkeypatch, value):
    calls = _refuse_persistence(monkeypatch)
    body = {
        "execution_plan_id": "p",
        "dispatch_authorization_id": "a",
        "decision_id": "d",
        "receipt_id": "r",
        "verification_state": "verified_failure",
        "evidence_snapshot_id": value,
        "idempotency_key": "i",
    }
    r = client.post(
        "/v1/execution-requests/exec_1/verify-outcome",
        json=body,
        headers={**HEADERS, "X-Verified-By": "op"},
    )
    assert r.status_code == 422, f"{value!r}: {r.status_code} {r.text}"
    assert r.json()["detail"]["field"] == "evidence_snapshot_id", r.text
    assert calls == [], "a malformed evidence id must be refused before persistence"


@pytest.mark.unit
def test_learning_attribution_refuses_a_malformed_evidence_id(monkeypatch):
    calls = _refuse_persistence(monkeypatch)
    body = {"model_id": "m", "label": "l", "evidence_snapshot_id": "ev 1", "idempotency_key": "i"}
    r = client.post(
        "/v1/outcomes/out_1/learning-attribution",
        json=body,
        headers={**HEADERS, "X-Attributed-By": "op"},
    )
    assert r.status_code == 422, f"{r.status_code} {r.text}"
    assert calls == [], "a malformed evidence id must be refused before persistence"


def _stub_learning_update_store(monkeypatch) -> list[str]:
    stored: list[str] = []

    async def persist(**kwargs):
        stored.append(kwargs["payload"].evidence_snapshot_id)
        return {
            "replayed": False,
            "write": "inserted",
            "review_status": "unreviewed",
            "agronomically_approved": False,
        }

    monkeypatch.setattr(mod, "persist_learning_update", persist)
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    return stored


@pytest.mark.unit
@pytest.mark.parametrize("value", [" x\n", "ev 1", "", "veg_x", "a" * 201])
def test_learning_update_refuses_a_malformed_evidence_id(monkeypatch, value):
    stored = _stub_learning_update_store(monkeypatch)
    body = {"model_id": "m", "decision_id": "dec_1", "evidence_snapshot_id": value}
    r = client.post("/v1/learning/updates", json=body, headers=HEADERS)
    assert r.status_code == 422, f"{value!r}: {r.status_code} {r.text}"
    assert r.json()["detail"] == {"code": "invalid_snapshot_id", "field": "evidence_snapshot_id"}
    assert stored == [], "a malformed evidence id must be refused before it is stored"


@pytest.mark.unit
@pytest.mark.parametrize("value", [None, "ev-1", "veg_" + "a" * 20])
def test_learning_update_stores_a_well_formed_or_absent_evidence_id(monkeypatch, value):
    stored = _stub_learning_update_store(monkeypatch)
    body = {"model_id": "m", "decision_id": "dec_1", "evidence_snapshot_id": value}
    r = client.post("/v1/learning/updates", json=body, headers=HEADERS)
    assert r.status_code == 200, f"{value!r}: {r.status_code} {r.text}"
    assert stored == [value]


@pytest.mark.unit
def test_learning_update_unresolved_veg_evidence_is_a_named_409(monkeypatch):
    async def refused(**kwargs):
        raise persistence.LearningUpdateEvidenceInvalid("unknown_evidence_snapshot")

    monkeypatch.setattr(mod, "persist_learning_update", refused)
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    body = {"model_id": "m", "decision_id": "dec_1", "evidence_snapshot_id": "veg_" + "c" * 20}
    r = client.post("/v1/learning/updates", json=body, headers=HEADERS)
    assert r.status_code == 409, f"{r.status_code} {r.text}"
    assert r.json()["detail"] == "unknown_evidence_snapshot", r.text


def _veg_body(**over) -> dict:
    body = {
        "field_id": "f1",
        "snapshot_hash": "a" * 64,
        "acquisition_at": "2026-01-01T00:00:00Z",
        "data_available_at": "2026-01-01T01:00:00Z",
        "quality_gate": {},
        "feature_manifest": {},
        "payload": {},
    }
    body.update(over)
    return body


@pytest.mark.unit
@pytest.mark.parametrize("value", ["bad id", "veg_short", "other_" + "a" * 20, "veg_" + "a" * 65])
def test_vegetation_snapshot_writer_refuses_a_malformed_named_id(monkeypatch, value):
    calls = _refuse_persistence(monkeypatch)
    r = client.post(
        "/v1/evidence/vegetation-snapshots", json=_veg_body(snapshot_id=value), headers=HEADERS
    )
    assert r.status_code == 422, f"{value!r}: {r.status_code} {r.text}"
    assert calls == [], "a malformed snapshot id must be refused before persistence"


@pytest.mark.unit
def test_vegetation_snapshot_id_conflict_is_a_named_409(monkeypatch):
    async def conflict(**kwargs):
        raise persistence.SnapshotIdConflict("snapshot_id_conflict")

    monkeypatch.setattr(mod, "persist_vegetation_snapshot", conflict)
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    r = client.post(
        "/v1/evidence/vegetation-snapshots",
        json=_veg_body(snapshot_id="veg_" + "b" * 20),
        headers=HEADERS,
    )
    assert r.status_code == 409, f"{r.status_code} {r.text}"
    assert r.json()["detail"] == "snapshot_id_conflict", r.text


@pytest.mark.unit
def test_persistence_refuses_a_malformed_id_before_connecting(monkeypatch):
    # No connection stub: the refusal must be the named ValueError raised before any
    # connection is acquired. With no DATABASE_URL a connection attempt fails differently.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    payload = SimpleNamespace(
        acquisition_at=datetime(2026, 1, 1, tzinfo=UTC),
        data_available_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="invalid_snapshot_id"):
        _run(
            persistence.persist_vegetation_snapshot(
                tenant_id=TENANT_A, payload=payload, snapshot_id="x"
            )
        )


# ── live PostgreSQL ─────────────────────────────────────────────────────────────────────

live = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")
T0 = datetime(2026, 5, 1, 6, 0, tzinfo=UTC)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _snap_payload(field_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        field_id=field_id,
        season_id=None,
        contract_version="vegetation-snapshot.v2",
        snapshot_hash=uuid4().hex + uuid4().hex,
        acquisition_at=T0,
        data_available_at=T0 + timedelta(hours=2),
        quality_gate={"executable": True, "passed": True},
        feature_manifest={},
        payload={"indices": {"ndvi": 0.5}},
    )


def _persist_snapshot(tenant: str, field_id: str, snapshot_id: str) -> dict:
    return _run(
        persistence.persist_vegetation_snapshot(
            tenant_id=tenant, payload=_snap_payload(field_id), snapshot_id=snapshot_id
        )
    )


@pytest.mark.integration
@live
def test_live_cross_tenant_snapshot_id_reuse_is_a_named_conflict():
    sid = "veg_" + uuid4().hex[:20]
    assert _persist_snapshot(TENANT_A, "f-a", sid)["created"] is True, "first write creates"
    with pytest.raises(persistence.SnapshotIdConflict):
        _persist_snapshot(TENANT_B, "f-b", sid)


@pytest.mark.integration
@live
def test_live_same_tenant_reuse_with_other_evidence_is_a_named_conflict():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_A, "f-a", sid)
    with pytest.raises(persistence.SnapshotIdConflict):
        _persist_snapshot(TENANT_A, "f-a", sid)  # same id, different content hash


async def _seed_terminal_request(tenant: str, field_id: str) -> SimpleNamespace:
    """decision (with field) → review → plan → authorization → accepted task request."""
    c = await _connect()
    did, rid, lin = "dec_" + uuid4().hex, "rev_" + uuid4().hex, "lin_" + uuid4().hex
    pid, aid = "xplan_" + uuid4().hex, "dauth_" + uuid4().hex
    xid, receipt = "exec_" + uuid4().hex, "rec_" + uuid4().hex
    try:
        await c.execute(
            "INSERT INTO decision_record(decision_id,tenant_id,field_id,decision_type,stage,decision_value,"
            "review_state,candidate_lineage_id) VALUES($1,$2::uuid,$3,'candidate','candidate',$4::jsonb,'approved',$5)",
            did,
            tenant,
            field_id,
            json.dumps({"candidate_lineage_id": lin}),
            lin,
        )
        await c.execute(
            "INSERT INTO decision_reviews(review_id,decision_id,tenant_id,action,previous_state,new_state,reason,"
            "reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
            "VALUES($1,$2,$3::uuid,'approve','pending_approval','approved','ok','r',$4,$5,$6,'p1')",
            rid,
            did,
            tenant,
            lin,
            "r-" + uuid4().hex,
            uuid4().hex,
        )
        await c.execute(
            "INSERT INTO decision_execution_plans(execution_plan_id,tenant_id,decision_id,review_id,"
            "candidate_lineage_id,operation_type,status,idempotency_key,request_hash,created_by) "
            "VALUES($1,$2::uuid,$3,$4,$5,'irrigation','planned',$6,$7,'p')",
            pid,
            tenant,
            did,
            rid,
            lin,
            "p-" + uuid4().hex,
            uuid4().hex,
        )
        await c.execute(
            "INSERT INTO decision_dispatch_authorizations(dispatch_authorization_id,tenant_id,execution_plan_id,"
            "decision_id,review_id,candidate_lineage_id,expected_plan_state,status,policy_version,"
            "weather_snapshot_id,resource_snapshot_id,authorization_reason,idempotency_key,request_hash,authorized_by) "
            "VALUES($1,$2::uuid,$3,$4,$5,$6,'planned','authorized','p1','w1','r1','ok',$7,$8,'m')",
            aid,
            tenant,
            pid,
            did,
            rid,
            lin,
            "a-" + uuid4().hex,
            uuid4().hex,
        )
        await c.execute(
            "INSERT INTO decision_execution_requests(execution_request_id,tenant_id,dispatch_authorization_id,"
            "execution_plan_id,decision_id,target_type,target_id,operation_type,command_payload,status,"
            "idempotency_key,request_hash,requested_by,receipt_id,receipt_status,receipt_payload,received_at) "
            "VALUES($1,$2::uuid,$3,$4,$5,'task','t','op','{}'::jsonb,'accepted',$6,$7,'u',$8,'accepted','{}'::jsonb,now())",
            xid,
            tenant,
            aid,
            pid,
            did,
            "i-" + uuid4().hex,
            uuid4().hex,
            receipt,
        )
        await c.execute(
            "INSERT INTO decision_execution_delivery_attempts(delivery_attempt_id,tenant_id,execution_request_id,"
            "adapter_id,adapter_kind,delivery_token_hash,receipt_id,receipt_status,receipt_payload,received_at) "
            "VALUES($1,$2::uuid,$3,'a','task','h',$4,'accepted','{}'::jsonb,now())",
            "del_" + uuid4().hex,
            tenant,
            xid,
            receipt,
        )
    finally:
        await c.close()
    return SimpleNamespace(
        execution_request_id=xid,
        execution_plan_id=pid,
        dispatch_authorization_id=aid,
        decision_id=did,
        receipt_id=receipt,
    )


def _outcome_payload(chain: SimpleNamespace, evidence_snapshot_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        execution_plan_id=chain.execution_plan_id,
        dispatch_authorization_id=chain.dispatch_authorization_id,
        decision_id=chain.decision_id,
        receipt_id=chain.receipt_id,
        verification_state="verified_success",
        evidence_snapshot_id=evidence_snapshot_id,
        actual={"completed": True},
        metrics={},
        idempotency_key="idem-" + uuid4().hex,
    )


def _verify(
    tenant: str,
    chain: SimpleNamespace,
    evidence_snapshot_id: str,
    payload: SimpleNamespace | None = None,
) -> dict:
    payload = payload or _outcome_payload(chain, evidence_snapshot_id)
    return _run(
        persistence.verify_execution_outcome(
            tenant_id=tenant,
            execution_request_id=chain.execution_request_id,
            verified_by="operator",
            payload=payload,
        )
    )


def _outcome_count(execution_request_id: str) -> int:
    async def count():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM outcome_record WHERE execution_request_id=$1",
                execution_request_id,
            )
        finally:
            await c.close()

    return _run(count())


@pytest.mark.integration
@live
def test_live_unknown_veg_evidence_is_refused_and_nothing_is_stored():
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    out = _verify(TENANT_A, chain, "veg_" + uuid4().hex[:20])
    assert out == {"status": "conflict", "reason": "unknown_evidence_snapshot"}, out
    assert _outcome_count(chain.execution_request_id) == 0, "a refused outcome must not be stored"


@pytest.mark.integration
@live
def test_live_another_tenants_veg_evidence_is_refused_as_unknown():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_B, "f-a", sid)  # same field name, other tenant
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    out = _verify(TENANT_A, chain, sid)
    assert out == {"status": "conflict", "reason": "unknown_evidence_snapshot"}, out
    assert _outcome_count(chain.execution_request_id) == 0, "a refused outcome must not be stored"


@pytest.mark.integration
@live
def test_live_veg_evidence_of_another_field_is_refused():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_A, "f-other", sid)
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    out = _verify(TENANT_A, chain, sid)
    assert out == {"status": "conflict", "reason": "evidence_snapshot_field_mismatch"}, out


@pytest.mark.integration
@live
def test_live_veg_evidence_of_the_decisions_field_is_accepted():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_A, "f-a", sid)
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    out = _verify(TENANT_A, chain, sid)
    assert out["status"] == "ok" and out["evidence_snapshot_id"] == sid, out
    assert _outcome_count(chain.execution_request_id) == 1, "the accepted outcome is stored once"


async def _store_legacy_outcome(tenant: str, chain: SimpleNamespace, payload: SimpleNamespace):
    """An outcome stored before evidence resolution existed, naming an unresolvable veg_ id."""
    c = await _connect()
    try:
        async with c.transaction():
            await c.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            await c.execute(
                "INSERT INTO outcome_record(outcome_id,tenant_id,decision_id,planned,actual,metrics,"
                "success,created_by,idempotency_key,execution_request_id,dispatch_authorization_id,"
                "execution_plan_id,receipt_id,verification_state,evidence_snapshot_id,verified_by,"
                "verified_at,request_hash) VALUES($1,$2::uuid,$3,'{}'::jsonb,$4::jsonb,'{}'::jsonb,"
                "true,'operator',$5,$6,$7,$8,$9,$10,$11,'operator',now(),$12)",
                "out_" + uuid4().hex[:20],
                tenant,
                payload.decision_id,
                json.dumps(payload.actual),
                payload.idempotency_key,
                chain.execution_request_id,
                payload.dispatch_authorization_id,
                payload.execution_plan_id,
                payload.receipt_id,
                payload.verification_state,
                payload.evidence_snapshot_id,
                persistence._execution_outcome_hash(
                    execution_request_id=chain.execution_request_id, payload=payload
                ),
            )
    finally:
        await c.close()


@pytest.mark.integration
@live
def test_live_identical_replay_of_a_stored_outcome_is_not_re_judged():
    """A byte-identical retry returns the stored outcome even if its veg_ id no longer resolves."""
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    payload = _outcome_payload(chain, "veg_" + uuid4().hex[:20])
    _run(_store_legacy_outcome(TENANT_A, chain, payload))
    out = _verify(TENANT_A, chain, payload.evidence_snapshot_id, payload=payload)
    assert out["status"] == "ok" and out["replay"] is True, (
        f"an identical retry must replay the stored outcome, not refuse it: {out}"
    )
    assert out["evidence_snapshot_id"] == payload.evidence_snapshot_id, out
    assert _outcome_count(chain.execution_request_id) == 1, "a replay must store nothing new"


# ── learning updates: veg_ evidence resolves against this tenant's snapshots ────────────


def _learning_payload(**over) -> SimpleNamespace:
    fields = dict(
        model_id="m-veg",
        feature_set_id=None,
        learning_rate=0.01,
        sample_count=0,
        label_summary={},
        drift_score=0.0,
        action=None,
        source_type=None,
        source_id=None,
        field_id=None,
        season_id=None,
        recommendation_id=None,
        decision_id="dec_" + uuid4().hex[:12],
        evidence_snapshot_id=None,
        review_status="unreviewed",
        agronomically_approved=False,
        agronomic_review=None,
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def _learn(tenant: str, payload: SimpleNamespace, update_id: str | None = None) -> dict:
    return _run(
        persistence.persist_learning_update(
            tenant_id=tenant,
            payload=payload,
            update_id=update_id or "lu_" + uuid4().hex[:16],
            traceability_status="derived_partial",
        )
    )


def _learning_rows(evidence_snapshot_id: str) -> int:
    async def count():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM online_learning_updates WHERE evidence_snapshot_id=$1",
                evidence_snapshot_id,
            )
        finally:
            await c.close()

    return _run(count())


@pytest.mark.integration
@live
def test_live_learning_update_refuses_unknown_veg_evidence_and_stores_nothing():
    sid = "veg_" + uuid4().hex[:20]
    with pytest.raises(persistence.LearningUpdateEvidenceInvalid) as err:
        _learn(TENANT_A, _learning_payload(evidence_snapshot_id=sid))
    assert err.value.reason == "unknown_evidence_snapshot"
    assert _learning_rows(sid) == 0, "a refused learning update must not be stored"


@pytest.mark.integration
@live
def test_live_learning_update_refuses_another_tenants_veg_evidence_as_unknown():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_B, "f-a", sid)
    with pytest.raises(persistence.LearningUpdateEvidenceInvalid) as err:
        _learn(TENANT_A, _learning_payload(evidence_snapshot_id=sid))
    assert err.value.reason == "unknown_evidence_snapshot"
    assert _learning_rows(sid) == 0, "another tenant's evidence must not be stored"


@pytest.mark.integration
@live
def test_live_learning_update_refuses_veg_evidence_of_another_decision_field():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_A, "f-other", sid)
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    payload = _learning_payload(evidence_snapshot_id=sid, decision_id=chain.decision_id)
    with pytest.raises(persistence.LearningUpdateEvidenceInvalid) as err:
        _learn(TENANT_A, payload)
    assert err.value.reason == "evidence_snapshot_field_mismatch"
    assert _learning_rows(sid) == 0


@pytest.mark.integration
@live
def test_live_learning_update_stores_this_tenants_veg_evidence():
    sid = "veg_" + uuid4().hex[:20]
    _persist_snapshot(TENANT_A, "f-a", sid)
    chain = _run(_seed_terminal_request(TENANT_A, "f-a"))
    payload = _learning_payload(evidence_snapshot_id=sid, decision_id=chain.decision_id)
    out = _learn(TENANT_A, payload)
    assert out["write"] == "inserted", out
    assert _learning_rows(sid) == 1


@pytest.mark.integration
@live
def test_live_learning_update_resend_of_a_stored_veg_id_is_not_re_judged():
    """A row stored before resolution existed replays; a NEW update with that id is refused."""
    sid, update_id = "veg_" + uuid4().hex[:20], "lu_" + uuid4().hex[:16]
    payload = _learning_payload(evidence_snapshot_id=sid)

    async def store_legacy():
        c = await _connect()
        try:
            await c.execute(
                "INSERT INTO online_learning_updates(update_id,tenant_id,model_id,decision_id,"
                "evidence_snapshot_id) VALUES($1,$2::uuid,$3,$4,$5)",
                update_id,
                TENANT_A,
                payload.model_id,
                payload.decision_id,
                sid,
            )
        finally:
            await c.close()

    _run(store_legacy())
    out = _learn(TENANT_A, payload, update_id=update_id)
    assert out["replayed"] is True and out["write"] == "unchanged", out
    with pytest.raises(persistence.LearningUpdateEvidenceInvalid):
        _learn(TENANT_A, payload)  # a fresh update_id: nothing stored to replay
    with pytest.raises(persistence.LearningUpdateEvidenceInvalid):
        _learn(TENANT_B, payload, update_id=update_id)  # another tenant's row is not a replay
    assert _learning_rows(sid) == 1
