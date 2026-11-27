"""Field inspection delivery contracts; network/DB seams are explicit unit doubles.

PostgreSQL atomicity/RLS is measured separately by the v291 live tests. These tests
exercise the adapter's real state machine, owner evidence builder, bounded discovery
and the three failure windows; no unit double is reported as end-to-end evidence.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.append(str(SERVICE_DIR))

from fastapi import HTTPException  # noqa: E402
from fm_execution_task_store import inspection_proof  # noqa: E402
from fm_execution_tasks import (  # noqa: E402
    ExecutionSettings,
    binding_from_source,
    canonical,
    outcome_payload,
    refuse,
)
from fm_gateway import Caller  # noqa: E402
from fm_task_inspection import evidence_digest  # noqa: E402

_COORDINATOR_PATH = SERVICE_DIR.parent / "sahool-platform/api/inspection_execution_adapter.py"
_COORDINATOR_SPEC = importlib.util.spec_from_file_location(
    "inspection_execution_coordinator_contract_tests", _COORDINATOR_PATH
)
_COORDINATOR_MODULE = importlib.util.module_from_spec(_COORDINATOR_SPEC)
sys.modules[_COORDINATOR_SPEC.name] = _COORDINATOR_MODULE
_COORDINATOR_SPEC.loader.exec_module(_COORDINATOR_MODULE)
ExecutionAdapter = _COORDINATOR_MODULE.ExecutionAdapter

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-4111-8111-111111111111"
PEER = "22222222-2222-4222-8222-222222222222"
OWNER = Caller(TENANT, "9", "owner")
WORKER = Caller(TENANT, "7", "worker")
FIELD = "field-inspection-unit"
SETTINGS = ExecutionSettings(True, "field-management-service-inspection-v1", "k" * 48)
REQUEST = "exec_unit"
PHOTO = "33333333-3333-4333-8333-333333333333"


def source():
    spec = {
        "pin_id": "pin_unit",
        "assigned_to": 7,
        "due_at": "2026-11-27T18:00:00+00:00",
        "priority": 3,
    }
    item = {
        "execution_request_id": REQUEST,
        "decision_id": "decision_unit",
        "execution_plan_id": "plan_unit",
        "dispatch_authorization_id": "authorization_unit",
        "target_type": "task",
        "target_id": spec["pin_id"],
        "operation_type": "field_inspection",
        "command_payload": {"field_id": FIELD, "inspection": copy.deepcopy(spec)},
    }
    lineage = {
        "authoritative": True,
        "tenant_id": TENANT,
        "decision_id": "decision_unit",
        "decision": {
            "decision_id": "decision_unit",
            "field_id": FIELD,
            "correlation_id": "44444444-4444-4444-8444-444444444444",
        },
    }
    plan = {
        "authoritative": True,
        "tenant_id": TENANT,
        "execution_plan_id": "plan_unit",
        "decision_id": "decision_unit",
        "field_id": FIELD,
        "operation_type": "field_inspection",
        "plan_state": "planned",
        "bound": True,
        "review_state": "approved",
        "plan_digest": "a" * 64,
        "decision_value_digest": "b" * 64,
        "current_decision_value_digest": "b" * 64,
        "target_zone_ids": [FIELD],
        "constraints": {"field_id": FIELD, "inspection": copy.deepcopy(spec)},
    }
    return item, lineage, plan


def binding():
    return binding_from_source(OWNER, *source(), FIELD, SETTINGS.adapter_id)


def evidence():
    link = asdict(binding())
    notes, photo_hash = "Synthetic inspection finding, reviewed by another person.", "c" * 64
    version = {
        "version": 1,
        "photo_evidence_id": PHOTO,
        "photo_content_sha256": photo_hash,
        "notes": notes,
        "digest": evidence_digest(PHOTO, photo_hash, notes),
        "recorded_by": "7",
    }
    task = {
        "tenant_id": TENANT,
        "field_id": FIELD,
        "task_id": link["task_id"],
        "pin_id": "pin_unit",
        "status": "completed",
        "task_type": "scouting",
        "anomaly_ref": None,
        "completed_at": "2026-11-27T17:00:00+00:00",
        "assigned_to": "7",
        "evidence": [version],
        "photo": {"evidence_id": PHOTO, "content_sha256": photo_hash},
    }
    events = [
        {
            "revision": 1,
            "action": "accept",
            "actor": "7",
            "assignee": "7",
            "evidence_version": None,
        },
        {"revision": 2, "action": "submit", "actor": "7", "assignee": "7", "evidence_version": 1},
        {"revision": 3, "action": "approve", "actor": "9", "assignee": "7", "evidence_version": 1},
    ]
    return link, task, events


def test_stable_task_identity_is_tenant_scoped_and_token_is_secret_bound():
    item, lineage, plan = source()
    first = binding_from_source(OWNER, item, lineage, plan, FIELD, SETTINGS.adapter_id)
    assert first.task_id == binding().task_id
    assert SETTINGS.token(TENANT, REQUEST) == SETTINGS.token(TENANT, REQUEST)
    assert SETTINGS.token(TENANT, REQUEST) != ExecutionSettings(
        True, SETTINGS.adapter_id, "z" * 48
    ).token(TENANT, REQUEST)
    lineage["tenant_id"], plan["tenant_id"] = PEER, PEER
    second = binding_from_source(
        Caller(PEER, "9", "owner"), item, lineage, plan, FIELD, SETTINGS.adapter_id
    )
    assert first.task_id != second.task_id and first.receipt_id != second.receipt_id
    assert "delivery_token" not in canonical(asdict(first) | {"receipt": first.receipt_payload()})


@pytest.mark.parametrize(
    "change",
    [
        lambda item, lineage, plan: item.update(target_type="equipment"),
        lambda item, lineage, plan: item.update(operation_type="irrigation"),
        lambda item, lineage, plan: item.update(target_id="invented-pin"),
        lambda item, lineage, plan: item["command_payload"].update(field_id="another-field"),
        lambda item, lineage, plan: item["command_payload"].update(device_id="valve-1"),
        lambda item, lineage, plan: item["command_payload"].pop("inspection"),
        lambda item, lineage, plan: item["command_payload"]["inspection"].update(assigned_to=True),
        lambda item, lineage, plan: item["command_payload"]["inspection"].update(
            due_at="2026-11-27T18:00:00"
        ),
        lambda item, lineage, plan: lineage.update(tenant_id=PEER),
        lambda item, lineage, plan: lineage["decision"].update(field_id="another-field"),
        lambda item, lineage, plan: lineage["decision"].update(correlation_id=None),
        lambda item, lineage, plan: plan.update(bound=False),
        lambda item, lineage, plan: plan.update(field_id="another-field"),
        lambda item, lineage, plan: plan.update(target_zone_ids=[]),
        lambda item, lineage, plan: plan.update(target_zone_ids=[FIELD, "another-field"]),
        lambda item, lineage, plan: plan.update(current_decision_value_digest="d" * 64),
        lambda item, lineage, plan: plan["constraints"]["inspection"].update(assigned_to=8),
        lambda item, lineage, plan: plan["constraints"].pop("inspection"),
    ],
)
def test_only_the_exact_approved_inspection_scope_can_be_bound(change):
    item, lineage, plan = source()
    change(item, lineage, plan)
    with pytest.raises(HTTPException):
        binding_from_source(OWNER, item, lineage, plan, FIELD, SETTINGS.adapter_id)


@pytest.mark.parametrize(
    "change",
    [
        lambda t, e: t.update(status="in_progress"),
        lambda t, e: t.update(task_type="irrigation"),
        lambda t, e: t.update(anomaly_ref="urn:sahool:anomaly:unrelated"),
        lambda t, e: t.update(completed_at=None),
        lambda t, e: t.update(field_id="peer"),
        lambda t, e: t.update(pin_id="peer"),
        lambda t, e: e.clear(),
        lambda t, e: e.pop(),
        lambda t, e: e[-1].update(action="return"),
        lambda t, e: e[-1].update(actor="7"),
        lambda t, e: t["evidence"][0].update(recorded_by="9"),
        lambda t, e: t["photo"].update(content_sha256="d" * 64),
        lambda t, e: t["photo"].update(evidence_id="55555555-5555-4555-8555-555555555555"),
        lambda t, e: t["evidence"][0].update(digest="e" * 64),
        lambda t, e: t.update(assigned_to="8"),
        lambda t, e: e.append({"revision": 4, "action": "reopen", "actor": "9", "assignee": "7"}),
        lambda t, e: t["evidence"].append({**t["evidence"][0], "version": 2}),
    ],
)
def test_completion_requires_current_latest_independent_approved_finding(change):
    link, task, events = evidence()
    change(task, events)
    with pytest.raises(HTTPException):
        inspection_proof(link, task, events)


def test_evidence_identity_is_stable_but_observation_time_is_not_an_attestation_forever():
    link, task, events = evidence()
    first, second = inspection_proof(link, task, events), inspection_proof(link, task, events)
    assert first["confirmation_id"] == second["confirmation_id"]
    assert first["evidence_snapshot_id"] == second["evidence_snapshot_id"]
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["actual"] == second["actual"] and first["metrics"] == {"inspection_approved": True}
    assert "observed_at" not in first["actual"]
    assert first["reviewer_id"] != first["inspector_id"]
    assert outcome_payload(first)["verification_state"] == "verified_success"


class OwnerStore:
    def __init__(self, log):
        self.log, self.links, self.tasks = log, {}, {}
        self.fail_before_commit = self.lose_commit_response = self.fail_readback = False
        self.validation_failure = False
        self.assignee_name = None
        self.proof = inspection_proof(*evidence())
        self.outcomes = []
        self.stale = False

    def source_context(self, binding, item, lineage, plan):
        self.source_envelope = {"item": item, "lineage": lineage, "plan": plan}

    def claim_context(self, binding, claim):
        self.source_claim = claim

    async def require_field(self, caller, field):
        self.log.append("field")
        if caller.tenant_id != TENANT or field != FIELD:
            raise refuse("field_not_found", 404)

    async def get_link(self, caller, request_id):
        self.log.append("link")
        return self.links.get(request_id)

    async def list_links(self, caller, field_id, limit):
        return list(self.links.values())[:limit]

    async def validate(self, caller, item):
        self.log.append("validate")
        if self.validation_failure:
            raise refuse("pin_or_assignee_unavailable", 422)
        return self.assignee_name

    async def ensure_task(self, caller, item):
        self.log.append("commit")
        if self.fail_before_commit:
            self.fail_before_commit = False
            raise refuse("store_unavailable", 503)
        self.tasks[item.task_id] = item
        self.links[item.execution_request_id] = asdict(item)
        if self.lose_commit_response:
            self.lose_commit_response = False
            raise refuse("store_response_lost", 503)
        return self.links[item.execution_request_id]

    async def readback(self, caller, item):
        self.log.append("readback")
        if self.fail_readback or item.task_id not in self.tasks:
            raise refuse("owner_readback_missing", 503)
        return self.links[item.execution_request_id]

    async def preview_confirmation(self, caller, link):
        if self.stale:
            raise refuse("inspection_changed", 409)
        if self.proof["reviewer_id"] != caller.user_id:
            raise refuse("reviewer_mismatch", 403)
        return self.proof

    async def prepare_confirmation(self, caller, task_id, field_id):
        self.log.append("prepare_committed")
        return await self.preview_confirmation(caller, {})

    async def read_execution_proof(self, tenant_id, request_id):
        if self.stale:
            raise refuse("inspection_changed", 409)
        return self.proof

    async def save_outcome(self, caller, proof, result):
        self.log.append("outcome_receipt")
        self.outcomes.append(result)
        return result


class Decision:
    def __init__(self, log, store):
        self.log, self.store = log, store
        self.item, self.head, self.approved_plan = source()
        self.claim_token, self.receipts, self.verify_calls = None, {}, []
        self.missing_feed = self.fail_feed = self.lose_receipt_response = False
        self.malformed_claim = self.malformed_receipt = self.stale_before_verify = False

    async def discover(self, tenant, adapter, limit):
        self.log.append("feed")
        if self.fail_feed:
            raise refuse("upstream_unavailable", 503)
        items = [] if self.missing_feed or self.receipts else [copy.deepcopy(self.item)]
        return {"items": items, "truncated": False}

    async def lineage(self, tenant, decision_id):
        self.log.append("lineage")
        return copy.deepcopy(self.head)

    async def plan(self, tenant, plan_id):
        self.log.append("plan")
        return copy.deepcopy(self.approved_plan)

    async def claim(self, tenant, request, adapter, token):
        self.log.append("claim")
        if self.claim_token is not None and self.claim_token != token:
            raise refuse("claim_mismatch", 409)
        self.claim_token = token
        if self.malformed_claim:
            return {"accepted": True}
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "execution_request_id": request,
            "adapter_id": adapter,
            "adapter_kind": "task",
            "delivery_state": "delivering",
        }

    async def receipt(self, item, token):
        self.log.append("receipt")
        assert item.task_id in self.store.tasks, "receipt must follow committed owner readback"
        if self.claim_token != token:
            raise refuse("claim_mismatch", 409)
        value = item.receipt_payload()
        if item.execution_request_id in self.receipts:
            assert self.receipts[item.execution_request_id] == value
        self.receipts[item.execution_request_id] = value
        if self.lose_receipt_response:
            self.lose_receipt_response = False
            raise refuse("receipt_response_lost", 503)
        if self.malformed_receipt:
            return {"accepted": True}
        return {
            "authoritative": True,
            "persisted": True,
            "execution_state": "accepted",
            "execution_request_id": item.execution_request_id,
            "receipt_id": item.receipt_id,
        }

    async def delivery_context(self, tenant, request):
        if request not in self.receipts:
            return None
        return {
            "tenant_id": tenant,
            "execution_request_id": request,
            "field_id": FIELD,
            "receipt_id": binding().receipt_id,
        }

    async def verify(self, tenant, request, actor, payload):
        self.log.append("remote_verify")
        if self.stale_before_verify:
            self.store.stale = True
        proof = await self.store.read_execution_proof(tenant, request)
        assert payload == outcome_payload(proof), "DS rereads the owner proof, not caller claims"
        self.verify_calls.append(payload)
        return {
            "status": "ok",
            "authoritative": True,
            "persisted": True,
            "success": True,
            **{
                key: payload[key]
                for key in (
                    "execution_plan_id",
                    "dispatch_authorization_id",
                    "decision_id",
                    "receipt_id",
                    "evidence_snapshot_id",
                    "verification_state",
                )
            },
            "execution_request_id": request,
            "verified_by": actor,
            "outcome_id": "out_unit",
            "verified_at": "2026-11-27T17:01:00+00:00",
        }


def harness(settings=SETTINGS):
    log = []
    owner = OwnerStore(log)
    decision = Decision(log, owner)
    adapter = ExecutionAdapter(owner, decision, settings)
    return adapter, owner, decision, log


def receive(adapter):
    return asyncio.run(adapter.receive(OWNER, REQUEST, expected_field_id=FIELD))


@pytest.mark.parametrize(
    "settings", [ExecutionSettings(), ExecutionSettings(True, token_key="short")]
)
def test_disabled_or_unconfigured_adapter_does_no_io(settings):
    adapter, owner, decision, log = harness(settings)
    with pytest.raises(HTTPException):
        receive(adapter)
    assert log == [] and owner.tasks == {} and decision.receipts == {}


def test_worker_cannot_deliver_or_verify_a_decision():
    adapter, owner, decision, log = harness()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(adapter.receive(WORKER, REQUEST, expected_field_id=FIELD))
    assert exc.value.status_code == 403 and log == []


def test_pin_and_assignee_are_validated_before_claim():
    adapter, owner, decision, log = harness()
    owner.validation_failure = True
    with pytest.raises(HTTPException):
        receive(adapter)
    assert "validate" in log and "claim" not in log and not owner.tasks


def test_receive_returns_accepted_only_after_commit_readback_and_terminal_receipt():
    adapter, owner, decision, log = harness()
    result = receive(adapter)
    assert result["state"] == "accepted" and not result["physical_execution_verified"]
    assert (
        log.index("validate")
        < log.index("claim")
        < log.index("commit")
        < log.index("readback")
        < log.index("receipt")
    )
    assert len(owner.tasks) == len(owner.links) == len(decision.receipts) == 1


@pytest.mark.parametrize("failure", ["fail_before_commit", "lose_commit_response"])
def test_recovery_after_claim_or_store_commit_is_idempotent(failure):
    adapter, owner, decision, log = harness()
    setattr(owner, failure, True)
    with pytest.raises(HTTPException):
        receive(adapter)
    assert decision.claim_token is not None and not decision.receipts
    first_token = decision.claim_token
    result = receive(ExecutionAdapter(owner, decision, SETTINGS))
    assert result["state"] == "accepted" and decision.claim_token == first_token
    assert len(owner.tasks) == len(owner.links) == len(decision.receipts) == 1


def test_receipt_committed_then_response_lost_replays_without_feed_or_new_claim():
    adapter, owner, decision, log = harness()
    decision.lose_receipt_response = True
    with pytest.raises(HTTPException):
        receive(adapter)
    assert len(owner.tasks) == len(decision.receipts) == 1
    log.clear()
    decision.missing_feed = True  # terminal/expired requests no longer appear in bounded feeds
    result = receive(ExecutionAdapter(owner, decision, SETTINGS))
    assert result["state"] == "accepted" and result["replayed"]
    assert "feed" not in log and "claim" not in log and "commit" not in log
    assert len(owner.tasks) == len(decision.receipts) == 1


def test_readback_failure_never_sends_an_accepted_receipt():
    adapter, owner, decision, log = harness()
    owner.fail_readback = True
    with pytest.raises(HTTPException):
        receive(adapter)
    assert "commit" in log and "readback" in log and "receipt" not in log


@pytest.mark.parametrize("malformed", ["malformed_claim", "malformed_receipt"])
def test_an_accepted_boolean_alone_is_never_a_success(malformed):
    adapter, owner, decision, log = harness()
    setattr(decision, malformed, True)
    with pytest.raises(HTTPException) as exc:
        receive(adapter)
    assert exc.value.status_code == 503
    if malformed == "malformed_claim":
        assert not owner.tasks and not decision.receipts


def test_key_rotation_does_not_fake_recovery_or_create_another_task():
    adapter, owner, decision, log = harness()
    decision.lose_receipt_response = True
    with pytest.raises(HTTPException):
        receive(adapter)
    changed = ExecutionAdapter(
        owner, decision, ExecutionSettings(True, SETTINGS.adapter_id, "x" * 48)
    )
    with pytest.raises(HTTPException) as exc:
        receive(changed)
    assert exc.value.status_code == 409 and len(owner.tasks) == 1


def test_field_route_cannot_deliver_a_peer_field_request():
    adapter, owner, decision, log = harness()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(adapter.receive(OWNER, REQUEST, expected_field_id="peer-field"))
    assert exc.value.status_code == 404 and not decision.claim_token


def test_missing_bounded_feed_is_not_reported_as_nonexistent_request():
    adapter, owner, decision, log = harness()
    decision.missing_feed = True
    with pytest.raises(HTTPException) as exc:
        receive(adapter)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "execution_request_not_discoverable"


def test_inbox_upstream_outage_does_not_become_empty_success():
    adapter, owner, decision, log = harness()
    decision.fail_feed = True
    with pytest.raises(HTTPException) as exc:
        asyncio.run(adapter.list_for_field(OWNER, FIELD))
    assert exc.value.status_code == 503


def test_inbox_is_bounded_and_never_performs_claims_or_writes():
    adapter, owner, decision, log = harness()
    result = asyncio.run(adapter.list_for_field(OWNER, FIELD, limit=1))
    assert len(result["items"]) == 1 and result["truncated"] is True
    assert result["items"][0]["can_receive"] is True
    assert "claim" not in log and "commit" not in log and "receipt" not in log


@pytest.mark.parametrize("name", [None, "اسم المستلم المحفوظ"])
def test_inbox_uses_only_the_owner_supplied_assignee_name_for_queued_and_linked_tasks(name):
    adapter, owner, decision, log = harness()
    owner.assignee_name = name
    queued = asyncio.run(adapter.list_for_field(OWNER, FIELD))["items"][0]
    assert queued["assigned_to"] == "7" and queued["assignee_name"] == name
    receive(adapter)
    owner.links[REQUEST]["assignee_name"] = name
    linked = asyncio.run(adapter.list_for_field(OWNER, FIELD))["items"][0]
    assert linked["assigned_to"] == "7" and linked["assignee_name"] == name


def test_owner_confirmation_precedes_remote_verification_and_only_ack_is_saved():
    adapter, owner, decision, log = harness()
    result = asyncio.run(adapter.verify(OWNER, binding().task_id, expected_field_id=FIELD))
    assert result["state"] == "verified_success"
    assert log == ["prepare_committed", "remote_verify", "outcome_receipt"]
    assert len(owner.outcomes) == 1 and len(decision.verify_calls) == 1


def test_changed_photo_before_decision_owner_readback_refuses_outcome():
    adapter, owner, decision, log = harness()
    decision.stale_before_verify = True
    with pytest.raises(HTTPException):
        asyncio.run(adapter.verify(OWNER, binding().task_id, expected_field_id=FIELD))
    assert decision.verify_calls == [] and owner.outcomes == []


def test_another_owner_cannot_confirm_the_last_approvers_finding():
    adapter, owner, decision, log = harness()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            adapter.verify(
                Caller(TENANT, "10", "owner"), binding().task_id, expected_field_id=FIELD
            )
        )
    assert exc.value.status_code == 403 and "remote_verify" not in log
