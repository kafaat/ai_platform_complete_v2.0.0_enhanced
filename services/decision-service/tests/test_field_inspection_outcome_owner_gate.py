"""Adversarial field-inspection outcome acceptance contracts.

The tests cover the owner HTTP boundary and canonical persistence refusal. They do
not claim PostgreSQL, BFF/browser, production, or hospital acceptance. A proof is a
point-in-time owner readback; no cross-service linearizability is asserted.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import field_inspection_evidence as owner_gate  # noqa: E402
import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001291"
OTHER_TENANT = "00000000-0000-0000-0000-000000001292"
REQUEST = "exec_inspection_1"
DECISION = "dec_inspection_1"
PLAN = "xplan_inspection_1"
AUTHORIZATION = "dauth_inspection_1"
RECEIPT = "receipt_inspection_1"
FIELD = "inspection-field-a"
PIN = "inspection-pin-a"
TASK = "b155214b-a7a1-5d36-b1dd-dd8aaf548a66"
CORRELATION = "ad6d7561-e481-49f2-bf04-d33c18bd5091"
INSPECTOR = "101"
REVIEWER = "102"
OWNER_URL = "http://field-management:8000"
PROOF_TOKEN = "unit-only-inspection-proof-token"
PROOF_PATH = "/internal/field-tasks/execution-proofs/" + REQUEST


def _case():
    notes = "Inspected the pump coupling and recorded the observation."
    evidence_digest = hashlib.sha256(("||" + notes).encode()).hexdigest()
    actual = {
        "provider": "field-management-service",
        "operation_type": "field_inspection",
        "tenant_id": TENANT,
        "field_id": FIELD,
        "pin_id": PIN,
        "provider_task_id": TASK,
        "execution_request_id": REQUEST,
        "decision_id": DECISION,
        "execution_plan_id": PLAN,
        "dispatch_authorization_id": AUTHORIZATION,
        "receipt_id": RECEIPT,
        "correlation_id": CORRELATION,
        "task_status": "completed",
        "completed_at": "2026-11-27T14:00:00+00:00",
        "handoff_revision": 3,
        "evidence_version": 1,
        "evidence_digest": evidence_digest,
        "photo_evidence_id": None,
        "photo_content_sha256": None,
        "finding_notes": notes,
        "inspector_id": INSPECTOR,
        "reviewer_id": REVIEWER,
    }
    metrics = {"inspection_approved": True}
    raw = json.dumps(
        {"actual": actual, "metrics": metrics},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    snapshot = "inspection_" + digest
    idempotency = "inspect-outcome-" + digest
    receipt_payload = {
        "provider": "field-management-service",
        "operation_type": "field_inspection",
        "provider_task_id": TASK,
        "task_ref": "urn:sahool:task:" + TASK,
        "tenant_id": TENANT,
        "field_id": FIELD,
        "pin_id": PIN,
        "execution_request_id": REQUEST,
        "decision_id": DECISION,
        "execution_plan_id": PLAN,
        "dispatch_authorization_id": AUTHORIZATION,
        "correlation_id": CORRELATION,
        "persisted": True,
    }
    source = {
        "execution_request_id": REQUEST,
        "execution_plan_id": PLAN,
        "dispatch_authorization_id": AUTHORIZATION,
        "decision_id": DECISION,
        "target_type": "task",
        "operation_type": "field_inspection",
        "target_id": PIN,
        "field_id": FIELD,
        "correlation_id": CORRELATION,
        "command_payload": {
            "field_id": FIELD,
            "inspection": {
                "pin_id": PIN,
                "assigned_to": int(INSPECTOR),
                "due_at": "2026-11-27T18:00:00+00:00",
                "priority": 3,
            },
        },
        "status": "accepted",
        "receipt_id": RECEIPT,
        "receipt_status": "accepted",
        "attempt_receipt_id": RECEIPT,
        "attempt_receipt_status": "accepted",
        "receipt_payload": receipt_payload,
    }
    payload = SimpleNamespace(
        execution_plan_id=PLAN,
        dispatch_authorization_id=AUTHORIZATION,
        decision_id=DECISION,
        receipt_id=RECEIPT,
        verification_state="verified_success",
        evidence_snapshot_id=snapshot,
        actual=deepcopy(actual),
        metrics=deepcopy(metrics),
        idempotency_key=idempotency,
    )
    proof = {
        "schema": "sahool.field-inspection-execution-proof/v1",
        "authoritative": True,
        "persisted": True,
        "current": True,
        "observed_at": datetime.now(UTC).isoformat(),
        "completed": True,
        "completed_at": actual["completed_at"],
        "verification_state": "verified_success",
        "tenant_id": TENANT,
        "field_id": FIELD,
        "pin_id": PIN,
        "task_id": TASK,
        "task_ref": "urn:sahool:task:" + TASK,
        "execution_request_id": REQUEST,
        "decision_id": DECISION,
        "execution_plan_id": PLAN,
        "dispatch_authorization_id": AUTHORIZATION,
        "receipt_id": RECEIPT,
        "correlation_id": CORRELATION,
        "confirmation_id": "fic_" + digest[:32],
        "handoff_revision": 3,
        "evidence_version": 1,
        "evidence_digest": evidence_digest,
        "photo_evidence_id": None,
        "photo_content_sha256": None,
        "inspector_id": INSPECTOR,
        "reviewer_id": REVIEWER,
        "verified_by": REVIEWER,
        "evidence_snapshot_id": snapshot,
        "idempotency_key": idempotency,
        "actual": actual,
        "metrics": metrics,
    }
    return source, payload, proof


def _reseal(proof, payload):
    """Keep the owner's canonical IDs coherent when testing a semantic counterexample."""
    raw = json.dumps(
        {"actual": proof["actual"], "metrics": proof["metrics"]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    proof["confirmation_id"] = "fic_" + digest[:32]
    proof["evidence_snapshot_id"] = "inspection_" + digest
    proof["idempotency_key"] = "inspect-outcome-" + digest
    payload.evidence_snapshot_id = proof["evidence_snapshot_id"]
    payload.idempotency_key = proof["idempotency_key"]
    payload.actual = deepcopy(proof["actual"])
    payload.metrics = deepcopy(proof["metrics"])


def _supply_owner(monkeypatch, proof):
    observed = []

    async def read_owner(tenant_id, execution_request_id):
        observed.append((tenant_id, execution_request_id))
        if isinstance(proof, Exception):
            raise proof
        return deepcopy(proof)

    monkeypatch.setattr(owner_gate, "read_owner_proof", read_owner)
    return observed


def _verify_owner(source, payload):
    return asyncio.run(
        owner_gate.verify_owner_evidence(
            tenant_id=TENANT,
            execution_request_id=REQUEST,
            verified_by=REVIEWER,
            source=source,
            payload=payload,
        )
    )


def _assert_refused(reason):
    assert isinstance(reason, str) and reason.strip(), reason


def test_only_matching_persisted_owner_evidence_authorizes_inspection_success(monkeypatch):
    source, payload, proof = _case()
    calls = _supply_owner(monkeypatch, proof)
    assert _verify_owner(source, payload) is None
    assert calls == [(TENANT, REQUEST)]


@pytest.mark.parametrize(
    "key",
    [
        "tenant_id",
        "execution_request_id",
        "decision_id",
        "execution_plan_id",
        "dispatch_authorization_id",
        "receipt_id",
        "correlation_id",
        "task_id",
        "field_id",
        "pin_id",
    ],
)
def test_owner_proof_from_another_chain_cannot_verify_this_execution(monkeypatch, key):
    source, payload, proof = _case()
    proof[key] = OTHER_TENANT if key == "tenant_id" else "unrelated-" + key
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("key", ["authoritative", "persisted", "current", "completed"])
@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_owner_flags_require_actual_true_not_truthy_values(monkeypatch, key, value):
    source, payload, proof = _case()
    proof[key] = value
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("key", ["schema", "confirmation_id", "observed_at"])
def test_owner_proof_cannot_omit_its_protocol_and_readback_identity(monkeypatch, key):
    source, payload, proof = _case()
    del proof[key]
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize(
    ("key", "wrong"),
    [
        ("evidence_snapshot_id", "inspection_" + "f" * 64),
        ("idempotency_key", "different-outcome-attempt"),
        ("evidence_version", 2),
        ("handoff_revision", 4),
        ("evidence_digest", "f" * 64),
        ("photo_evidence_id", "ef072451-f66c-4d16-810c-de14adca7ec8"),
        ("photo_content_sha256", "e" * 64),
    ],
)
def test_old_or_substituted_evidence_cannot_match_current_payload(monkeypatch, key, wrong):
    source, payload, proof = _case()
    proof[key] = wrong
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("key", ["reviewer_id", "verified_by"])
def test_the_owner_review_must_be_by_the_verifying_reviewer(monkeypatch, key):
    source, payload, proof = _case()
    proof[key] = "unrelated-reviewer"
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


def test_an_inspector_cannot_turn_their_own_finding_into_independent_review(monkeypatch):
    source, payload, proof = _case()
    proof["inspector_id"] = REVIEWER
    proof["actual"]["inspector_id"] = REVIEWER
    source["command_payload"]["inspection"]["assigned_to"] = int(REVIEWER)
    _reseal(proof, payload)
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("target", ["actual", "metrics"])
def test_browser_assertions_cannot_replace_the_owner_observation(monkeypatch, target):
    source, payload, proof = _case()
    if target == "actual":
        payload.actual["finding_notes"] = "Claimed work that the inspector did not record."
    else:
        payload.metrics["inspection_approved"] = False
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize(
    ("location", "key", "wrong"),
    [
        ("source", "field_id", "another-field"),
        ("source", "target_id", "another-pin"),
        ("source", "correlation_id", "another-correlation"),
        ("receipt", "provider", "another-service"),
        ("receipt", "operation_type", "irrigation"),
        ("receipt", "provider_task_id", "another-task"),
        ("receipt", "task_ref", "urn:sahool:task:another-task"),
        ("receipt", "field_id", "another-field"),
        ("receipt", "pin_id", "another-pin"),
        ("receipt", "execution_request_id", "another-execution"),
        ("receipt", "decision_id", "another-decision"),
        ("receipt", "execution_plan_id", "another-plan"),
        ("receipt", "dispatch_authorization_id", "another-authorization"),
        ("receipt", "correlation_id", "another-correlation"),
    ],
)
def test_proof_cannot_override_misbound_persisted_source(monkeypatch, location, key, wrong):
    source, payload, proof = _case()
    target = source if location == "source" else source["receipt_payload"]
    target[key] = wrong
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("schema", ["sahool.field-inspection-execution-proof/v0", "", None])
def test_unrecognized_owner_protocol_is_refused(monkeypatch, schema):
    source, payload, proof = _case()
    proof["schema"] = schema
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize(
    ("key", "wrong"),
    [
        ("provider", "another-service"),
        ("operation_type", "irrigation"),
        ("tenant_id", OTHER_TENANT),
        ("field_id", "another-field"),
        ("pin_id", "another-pin"),
        ("provider_task_id", "b155214b-a7a1-5d36-b1dd-dd8aaf548a67"),
        ("execution_request_id", "another-request"),
        ("decision_id", "another-decision"),
        ("execution_plan_id", "another-plan"),
        ("dispatch_authorization_id", "another-authorization"),
        ("receipt_id", "another-receipt"),
        ("correlation_id", "ad6d7561-e481-49f2-bf04-d33c18bd5092"),
        ("task_status", "pending"),
        ("handoff_revision", 4),
        ("evidence_version", 2),
        ("evidence_digest", "f" * 64),
        ("photo_evidence_id", "ef072451-f66c-4d16-810c-de14adca7ec8"),
        ("photo_content_sha256", "e" * 64),
        ("inspector_id", "103"),
        ("reviewer_id", "104"),
    ],
)
def test_actual_must_describe_the_owner_top_level_proof_even_with_valid_seal(
    monkeypatch, key, wrong
):
    source, payload, proof = _case()
    proof["actual"][key] = wrong
    _reseal(proof, payload)
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize(
    "metrics",
    [
        {},
        {"inspection_approved": False},
        {"inspection_approved": 1},
        {"inspection_approved": True, "unmeasured_yield_gain": 42},
    ],
)
def test_metrics_are_the_exact_owner_inspection_contract(monkeypatch, metrics):
    source, payload, proof = _case()
    proof["metrics"] = metrics
    _reseal(proof, payload)
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("key", ["confirmation_id", "evidence_snapshot_id", "idempotency_key"])
def test_declared_seal_cannot_name_another_content_digest(monkeypatch, key):
    source, payload, proof = _case()
    prefixes = {
        "confirmation_id": "fic_",
        "evidence_snapshot_id": "inspection_",
        "idempotency_key": "inspect-outcome-",
    }
    value = prefixes[key] + "f" * (32 if key == "confirmation_id" else 64)
    proof[key] = value
    if key != "confirmation_id":
        setattr(payload, key, value)
    _supply_owner(monkeypatch, proof)
    _assert_refused(_verify_owner(source, payload))


@pytest.mark.parametrize("notes", [None, ""])
def test_current_approved_photo_can_have_no_finding_notes(monkeypatch, notes):
    source, payload, proof = _case()
    photo_id = "ef072451-f66c-4d16-810c-de14adca7ec8"
    photo_sha = "e" * 64
    digest = hashlib.sha256((photo_id + "|" + photo_sha + "|").encode()).hexdigest()
    proof.update(
        photo_evidence_id=photo_id,
        photo_content_sha256=photo_sha,
        evidence_digest=digest,
    )
    proof["actual"].update(
        finding_notes=notes,
        photo_evidence_id=photo_id,
        photo_content_sha256=photo_sha,
        evidence_digest=digest,
    )
    _reseal(proof, payload)
    _supply_owner(monkeypatch, proof)
    assert _verify_owner(source, payload) is None


def test_receipt_json_text_keeps_the_same_owner_binding(monkeypatch):
    source, payload, proof = _case()
    source["receipt_payload"] = json.dumps(source["receipt_payload"])
    _supply_owner(monkeypatch, proof)
    assert _verify_owner(source, payload) is None


def test_a_second_verification_reads_owner_again_and_sees_a_changed_photo(monkeypatch):
    source, payload, proof = _case()
    calls = []

    async def changing_owner(tenant_id, execution_request_id):
        calls.append((tenant_id, execution_request_id))
        current = deepcopy(proof)
        if len(calls) > 1:
            current["current"] = False
            current["photo_evidence_id"] = "ef072451-f66c-4d16-810c-de14adca7ec8"
            current["photo_content_sha256"] = "e" * 64
        return current

    monkeypatch.setattr(owner_gate, "read_owner_proof", changing_owner)
    assert _verify_owner(source, payload) is None
    _assert_refused(_verify_owner(source, payload))
    assert calls == [(TENANT, REQUEST), (TENANT, REQUEST)]


def _http_owner(monkeypatch, handler):
    monkeypatch.setenv("FIELD_MANAGEMENT_SERVICE_URL", OWNER_URL)
    monkeypatch.setenv("FIELD_INSPECTION_PROOF_TOKEN", PROOF_TOKEN)
    real_client = httpx.AsyncClient
    options = []
    requests = []

    def responder(request):
        requests.append(request)
        return handler(request)

    def client(*args, **kwargs):
        options.append(dict(kwargs))
        return real_client(*args, transport=httpx.MockTransport(responder), **kwargs)

    monkeypatch.setattr(owner_gate.httpx, "AsyncClient", client)
    return options, requests


def _read_owner():
    return asyncio.run(owner_gate.read_owner_proof(TENANT, REQUEST))


def test_owner_http_read_uses_dedicated_token_tenant_and_bounded_nonproxy_client(monkeypatch):
    _, _, proof = _case()
    options, requests = _http_owner(monkeypatch, lambda request: httpx.Response(200, json=proof))
    assert _read_owner() == proof
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url) == OWNER_URL + PROOF_PATH
    assert request.headers["X-Field-Inspection-Proof-Token"] == PROOF_TOKEN
    assert request.headers["X-Tenant-Id"] == TENANT
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers
    assert options[0].get("trust_env") is False
    assert not options[0].get("follow_redirects", False)
    timeout = options[0]["timeout"]
    bounds = (
        [timeout.connect, timeout.read, timeout.write, timeout.pool]
        if isinstance(timeout, httpx.Timeout)
        else [timeout]
    )
    assert all(isinstance(value, (int, float)) and 0 < value <= 3 for value in bounds)


@pytest.mark.parametrize(
    "missing", ["FIELD_MANAGEMENT_SERVICE_URL", "FIELD_INSPECTION_PROOF_TOKEN"]
)
def test_missing_owner_configuration_refuses_before_any_http(monkeypatch, missing):
    options, requests = _http_owner(
        monkeypatch, lambda request: httpx.Response(200, json={"completed": True})
    )
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(owner_gate.OwnerEvidenceError) as raised:
        _read_owner()
    _assert_refused(raised.value.reason)
    assert not options and not requests


@pytest.mark.parametrize("status", [401, 403, 404, 409, 500, 503])
def test_owner_http_refusal_never_becomes_success(monkeypatch, status):
    _, requests = _http_owner(
        monkeypatch, lambda request: httpx.Response(status, json={"detail": "unavailable"})
    )
    with pytest.raises(owner_gate.OwnerEvidenceError) as raised:
        _read_owner()
    _assert_refused(raised.value.reason)
    assert len(requests) == 1


def test_owner_redirect_does_not_forward_the_proof_token(monkeypatch):
    _, requests = _http_owner(
        monkeypatch,
        lambda request: httpx.Response(
            302, headers={"Location": "http://unrelated-service.invalid/proof"}
        ),
    )
    with pytest.raises(owner_gate.OwnerEvidenceError):
        _read_owner()
    assert len(requests) == 1


@pytest.mark.parametrize("bad_json", [None, [], "completed", True])
def test_owner_non_object_json_is_not_a_proof(monkeypatch, bad_json):
    _http_owner(monkeypatch, lambda request: httpx.Response(200, json=bad_json))
    with pytest.raises(owner_gate.OwnerEvidenceError):
        _read_owner()


def test_owner_invalid_json_is_refused(monkeypatch):
    _http_owner(monkeypatch, lambda request: httpx.Response(200, content=b"{truncated"))
    with pytest.raises(owner_gate.OwnerEvidenceError):
        _read_owner()


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_owner_transport_failure_is_not_retried_as_an_accepted_result(monkeypatch, error_type):
    def failing(request):
        raise error_type("owner unavailable", request=request)

    _, requests = _http_owner(monkeypatch, failing)
    with pytest.raises(owner_gate.OwnerEvidenceError) as raised:
        _read_owner()
    _assert_refused(raised.value.reason)
    assert len(requests) == 1


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Connection:
    """Record mutations without prescribing the source query/transaction ordering."""

    def __init__(self, source, payload, prior=None):
        self.source = deepcopy(source)
        self.payload = payload
        self.prior = prior
        self.outcomes = []
        self.events = []

    def transaction(self, *args, **kwargs):
        return _Transaction()

    async def execute(self, sql, *args):
        if re.search(r"\bINSERT\s+INTO\s+decision_outbox_events\b", sql, re.I):
            self.events.append(args)
        elif re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", sql, re.I):
            raise AssertionError("Unexpected mutation in outcome verification: " + sql)

    def outcome(self):
        return {
            "outcome_id": "out_inspection_1",
            "execution_request_id": REQUEST,
            "execution_plan_id": PLAN,
            "dispatch_authorization_id": AUTHORIZATION,
            "decision_id": DECISION,
            "receipt_id": RECEIPT,
            "verification_state": self.payload.verification_state,
            "evidence_snapshot_id": self.payload.evidence_snapshot_id,
            "success": self.payload.verification_state == "verified_success",
            "verified_by": REVIEWER,
            "verified_at": "2026-11-27T14:00:01+00:00",
        }

    async def fetchrow(self, sql, *args):
        if re.search(r"\bINSERT\s+INTO\s+outcome_record\b", sql, re.I):
            self.outcomes.append(args)
            return self.outcome()
        if "decision_execution_requests" in sql:
            return deepcopy(self.source)
        if "outcome_record" in sql:
            return deepcopy(self.prior)
        raise AssertionError("Unexpected query in outcome verification: " + sql)

    async def close(self):
        return None


def _persist(monkeypatch, conn):
    async def connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", connect)
    return asyncio.run(
        persistence.verify_execution_outcome(
            tenant_id=TENANT,
            execution_request_id=REQUEST,
            verified_by=REVIEWER,
            payload=conn.payload,
        )
    )


@pytest.mark.parametrize("failure", ["unavailable", "stale", "wrong_task", "browser_actual"])
def test_public_verifier_cannot_write_before_owner_proof(monkeypatch, failure):
    source, payload, proof = _case()
    if failure == "unavailable":
        value = owner_gate.OwnerEvidenceError("owner_unavailable")
    else:
        value = proof
        if failure == "stale":
            value["current"] = False
        elif failure == "wrong_task":
            value["task_id"] = "another-task"
        else:
            payload.actual["finding_notes"] = "Unreviewed replacement"
    _supply_owner(monkeypatch, value)
    conn = _Connection(source, payload)
    result = _persist(monkeypatch, conn)
    assert result.get("status") == "conflict"
    _assert_refused(result.get("reason"))
    assert conn.outcomes == [] and conn.events == []


def test_owner_proof_allows_one_canonical_outcome_and_event(monkeypatch):
    source, payload, proof = _case()
    calls = _supply_owner(monkeypatch, proof)
    conn = _Connection(source, payload)
    result = _persist(monkeypatch, conn)
    assert result["status"] == "ok" and result["success"] is True
    assert calls == [(TENANT, REQUEST)]
    assert len(conn.outcomes) == 1 and len(conn.events) == 1


def test_old_stored_success_cannot_skip_fresh_owner_gate_on_replay(monkeypatch):
    source, payload, _ = _case()
    conn = _Connection(source, payload)
    conn.prior = {
        **conn.outcome(),
        "request_hash": persistence._execution_outcome_hash(
            execution_request_id=REQUEST, payload=payload
        ),
    }
    _supply_owner(monkeypatch, owner_gate.OwnerEvidenceError("owner_no_longer_current"))
    result = _persist(monkeypatch, conn)
    assert result.get("status") == "conflict"
    assert conn.outcomes == [] and conn.events == []


def test_matching_replay_reads_owner_but_does_not_duplicate_outcome(monkeypatch):
    source, payload, proof = _case()
    conn = _Connection(source, payload)
    conn.prior = {
        **conn.outcome(),
        "request_hash": persistence._execution_outcome_hash(
            execution_request_id=REQUEST, payload=payload
        ),
    }
    calls = _supply_owner(monkeypatch, proof)
    result = _persist(monkeypatch, conn)
    assert result["status"] == "ok" and result["replay"] is True
    assert calls == [(TENANT, REQUEST)]
    assert conn.outcomes == [] and conn.events == []


@pytest.mark.parametrize("scope", ["different_operation", "verified_failure"])
def test_existing_noninspection_or_failure_contract_does_not_claim_owner_verification(
    monkeypatch, scope
):
    source, payload, _ = _case()
    if scope == "different_operation":
        source["operation_type"] = "other_human_task"
    else:
        payload.verification_state = "verified_failure"

    async def unexpected_owner(*args, **kwargs):
        raise AssertionError("Owner inspection gate was used outside its declared scope")

    monkeypatch.setattr(owner_gate, "read_owner_proof", unexpected_owner)
    conn = _Connection(source, payload)
    result = _persist(monkeypatch, conn)
    assert result["status"] == "ok"
    assert result["success"] is (scope == "different_operation")
    assert len(conn.outcomes) == 1
