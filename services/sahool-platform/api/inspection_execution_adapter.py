"""Platform HTTP coordinator for inspection delivery and independent owner proof.

The coordinator owns no field SQL. Its two outgoing clients form an acyclic
call graph: platform -> decision/field, with decision -> field for fresh proof.
No field owner transaction remains open while the coordinator calls decision.
"""

from __future__ import annotations

import copy
import os
from dataclasses import asdict
from typing import Protocol
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException

from shared.field_inspection_execution import (
    FIELD_VIEW,
    OPERATION,
    Caller,
    ExecutionBinding,
    ExecutionSettings,
    _operator,
    binding_from_source,
    identifier,
    outcome_payload,
    refuse,
    require,
)


class DecisionClient(Protocol):
    async def discover(self, tenant_id: str, adapter_id: str, limit: int) -> dict: ...
    async def lineage(self, tenant_id: str, decision_id: str) -> dict: ...
    async def plan(self, tenant_id: str, plan_id: str) -> dict: ...
    async def claim(self, tenant_id: str, request_id: str, adapter_id: str, token: str) -> dict: ...
    async def receipt(self, binding: ExecutionBinding, token: str) -> dict: ...
    async def delivery_context(self, tenant_id: str, request_id: str) -> dict | None: ...
    async def verify(
        self, tenant_id: str, request_id: str, verified_by: str, payload: dict
    ) -> dict: ...


class ExecutionStore(Protocol):
    def source_context(
        self, binding: ExecutionBinding, item: dict, lineage: dict, plan: dict
    ) -> None: ...
    def claim_context(self, binding: ExecutionBinding, claim: dict) -> None: ...
    async def require_field(self, caller: Caller, field_id: str) -> None: ...
    async def get_link(self, caller: Caller, request_id: str) -> dict | None: ...
    async def list_links(self, caller: Caller, field_id: str, limit: int) -> list[dict]: ...
    async def validate(self, caller: Caller, binding: ExecutionBinding) -> str | None: ...
    async def ensure_task(self, caller: Caller, binding: ExecutionBinding) -> dict: ...
    async def readback(self, caller: Caller, binding: ExecutionBinding) -> dict: ...
    async def preview_confirmation(self, caller: Caller, link: dict) -> dict: ...
    async def prepare_confirmation(self, caller: Caller, task_id: str, field_id: str) -> dict: ...
    async def save_outcome(self, caller: Caller, proof: dict, result: dict) -> dict: ...


class HttpDecisionClient:
    """Real service HTTP; errors expose codes, never bearer tokens or upstream bodies."""

    def __init__(self, base_url: str, token: str, timeout: float = 8.0):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise refuse("decision_service_url_unconfigured", 503)
        if not token:
            raise refuse("decision_service_token_unconfigured", 503)
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    @classmethod
    def from_env(cls) -> HttpDecisionClient:
        return cls(
            os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160"),
            os.getenv("DECISION_SERVICE_TOKEN", ""),
        )

    async def _request(
        self,
        method: str,
        path: str,
        tenant_id: str,
        body: dict | None = None,
        actor: str | None = None,
        absent_ok: bool = False,
    ) -> dict | None:
        headers = {"Authorization": "Bearer " + self.token, "X-Tenant-Id": tenant_id}
        if actor is not None:
            headers["X-Verified-By"] = actor
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.request(
                    method,
                    self.base_url + path,
                    headers=headers,
                    json=body,
                )
        except httpx.HTTPError:
            raise refuse("decision_service_unavailable", 503) from None
        if absent_ok and response.status_code == 404:
            return None
        if response.status_code != 200:
            code = response.status_code
            raise refuse(
                "decision_service_refused_" + str(code), code if code in {404, 409, 422} else 503
            )
        try:
            result = response.json()
        except ValueError:
            raise refuse("decision_service_invalid_response", 503) from None
        if not isinstance(result, dict):
            raise refuse("decision_service_invalid_response", 503)
        return result

    async def discover(self, tenant_id: str, adapter_id: str, limit: int) -> dict:
        limit = max(1, min(100, limit))
        recovery = await self._request(
            "GET",
            "/v1/execution-requests/recovery?"
            + urlencode(
                {
                    "adapter_id": adapter_id,
                    "target_type": "task",
                    "limit": limit,
                }
            ),
            tenant_id,
        )
        queued = await self._request(
            "GET",
            "/v1/execution-requests?"
            + urlencode(
                {
                    "state": "queued",
                    "target_type": "task",
                    "limit": limit,
                }
            ),
            tenant_id,
        )
        items: dict[str, dict] = {}
        truncated = False
        for result, state in ((recovery, "delivering"), (queued, "queued")):
            if (
                result.get("authoritative") is not True
                or result.get("persisted") is not True
                or result.get("tenant_id") != tenant_id
                or not isinstance(result.get("items"), list)
            ):
                raise refuse("execution_feed_unproven", 503)
            truncated = truncated or len(result["items"]) >= limit
            for item in result["items"]:
                if not isinstance(item, dict):
                    raise refuse("execution_feed_unproven", 503)
                request_id = identifier(item.get("execution_request_id"))
                if request_id not in items:
                    items[request_id] = {**item, "discovery_state": state}
        return {"items": list(items.values()), "truncated": truncated}

    async def lineage(self, tenant_id: str, decision_id: str) -> dict:
        return await self._request(
            "GET",
            "/v1/decisions/" + quote(decision_id, safe="") + "/lineage",
            tenant_id,
        )

    async def plan(self, tenant_id: str, plan_id: str) -> dict:
        return await self._request(
            "GET",
            "/v1/execution-plans/" + quote(plan_id, safe=""),
            tenant_id,
        )

    async def claim(self, tenant_id: str, request_id: str, adapter_id: str, token: str) -> dict:
        return await self._request(
            "POST",
            "/v1/execution-requests/" + quote(request_id, safe="") + "/claim",
            tenant_id,
            {"adapter_id": adapter_id, "adapter_kind": "task", "delivery_token": token},
        )

    async def receipt(self, binding: ExecutionBinding, token: str) -> dict:
        return await self._request(
            "POST",
            "/v1/execution-requests/" + quote(binding.execution_request_id, safe="") + "/receipt",
            binding.tenant_id,
            {
                "adapter_id": binding.adapter_id,
                "delivery_token": token,
                "receipt_id": binding.receipt_id,
                "receipt_status": "accepted",
                "receipt_payload": binding.receipt_payload(),
            },
        )

    async def delivery_context(self, tenant_id: str, request_id: str) -> dict | None:
        return await self._request(
            "GET",
            "/v1/execution-requests/" + quote(request_id, safe="") + "/observation-context",
            tenant_id,
            absent_ok=True,
        )

    async def verify(
        self, tenant_id: str, request_id: str, verified_by: str, payload: dict
    ) -> dict:
        return await self._request(
            "POST",
            "/v1/execution-requests/" + quote(request_id, safe="") + "/verify-outcome",
            tenant_id,
            payload,
            actor=verified_by,
        )


class ExecutionAdapter:
    def __init__(
        self,
        store: ExecutionStore,
        client: DecisionClient,
        settings: ExecutionSettings | None = None,
    ):
        self.store, self.client = store, client
        self.settings = settings if settings is not None else ExecutionSettings.from_env()

    async def _binding(self, caller: Caller, item: dict, field_id: str) -> ExecutionBinding:
        if item.get("target_type") != "task" or item.get("operation_type") != OPERATION:
            raise refuse("only_field_inspection_tasks_are_supported", 422)
        lineage = await self.client.lineage(caller.tenant_id, identifier(item.get("decision_id")))
        plan = await self.client.plan(caller.tenant_id, identifier(item.get("execution_plan_id")))
        binding = binding_from_source(
            caller, item, lineage, plan, field_id, self.settings.adapter_id
        )
        self.store.source_context(binding, item, lineage, plan)
        return binding

    async def receive(
        self,
        caller: Caller,
        execution_request_id: str,
        *,
        expected_field_id: str,
    ) -> dict:
        self.settings.check()
        _operator(caller)
        request_id = identifier(execution_request_id)
        await self.store.require_field(caller, expected_field_id)
        # Locally committed task survives feed age/plan expiry and a lost receipt response.
        prior = await self.store.get_link(caller, request_id)
        replay = prior is not None
        if prior is not None:
            binding = ExecutionBinding.from_record(prior)
            if binding.field_id != expected_field_id or binding.tenant_id != caller.tenant_id:
                raise refuse("execution_field_mismatch", 404)
            if binding.adapter_id != self.settings.adapter_id:
                raise refuse("execution_adapter_identity_changed", 409)
        else:
            feed = await self.client.discover(caller.tenant_id, self.settings.adapter_id, 100)
            item = next(
                (x for x in feed["items"] if x.get("execution_request_id") == request_id), None
            )
            if item is None:
                # Bounded discovery is not a claim that the request does not exist.
                raise refuse("execution_request_not_discoverable", 409)
            binding = await self._binding(caller, item, expected_field_id)
            # Field, pin and active assignee are checked by their owner BEFORE the claim.
            await self.store.validate(caller, binding)
            claim = await self.client.claim(
                caller.tenant_id,
                request_id,
                binding.adapter_id,
                self.settings.token(caller.tenant_id, request_id),
            )
            if (
                claim.get("authoritative") is not True
                or claim.get("persisted") is not True
                or claim.get("execution_request_id") != request_id
                or claim.get("adapter_id") != binding.adapter_id
                or claim.get("adapter_kind") != "task"
                or claim.get("delivery_state") != "delivering"
            ):
                raise refuse("execution_claim_unproven", 503)
            self.store.claim_context(binding, claim)
            # No fabricated failed receipt on an uncertain store result: recovery retries this.
            stored = await self.store.ensure_task(caller, binding)
            binding = ExecutionBinding.from_record(stored)
        await self.store.readback(caller, binding)
        result = await self.client.receipt(
            binding,
            self.settings.token(binding.tenant_id, binding.execution_request_id),
        )
        if (
            result.get("authoritative") is not True
            or result.get("persisted") is not True
            or result.get("execution_request_id") != binding.execution_request_id
            or result.get("receipt_id") != binding.receipt_id
            or result.get("execution_state") != "accepted"
        ):
            raise refuse("execution_receipt_unproven", 503)
        return {
            "state": "accepted",
            "persisted": True,
            "replayed": replay or bool(result.get("replay")),
            "execution_request_id": binding.execution_request_id,
            "task_id": binding.task_id,
            "field_id": binding.field_id,
            "receipt_id": binding.receipt_id,
            "physical_execution_verified": False,
        }

    async def verify(self, caller: Caller, task_id: str, *, expected_field_id: str) -> dict:
        self.settings.check()
        _operator(caller, verification=True)
        proof = await self.store.prepare_confirmation(caller, task_id, expected_field_id)
        if proof.get("verified_by") != caller.user_id or proof.get("reviewer_id") != caller.user_id:
            raise refuse("only_current_approver_may_verify", 403)
        # prepare_confirmation has committed/closed. DS independently reads the CURRENT owner
        # proof through its authenticated S2S guard. No transaction is held across this request.
        result = await self.client.verify(
            caller.tenant_id,
            proof["execution_request_id"],
            caller.user_id,
            outcome_payload(proof),
        )
        expected = {
            "execution_request_id": proof["execution_request_id"],
            "execution_plan_id": proof["execution_plan_id"],
            "dispatch_authorization_id": proof["dispatch_authorization_id"],
            "decision_id": proof["decision_id"],
            "receipt_id": proof["receipt_id"],
            "evidence_snapshot_id": proof["evidence_snapshot_id"],
            "verification_state": "verified_success",
            "verified_by": caller.user_id,
        }
        if (
            result.get("authoritative") is not True
            or result.get("persisted") is not True
            or result.get("success") is not True
            or not result.get("outcome_id")
            or not result.get("verified_at")
            or any(result.get(k) != v for k, v in expected.items())
        ):
            raise refuse("inspection_outcome_unproven", 503)
        await self.store.save_outcome(caller, proof, result)
        return {
            "state": "verified_success",
            "persisted": True,
            "task_id": task_id,
            "execution_request_id": proof["execution_request_id"],
            "outcome_id": result["outcome_id"],
            "evidence_snapshot_id": proof["evidence_snapshot_id"],
            "verified_at": result["verified_at"],
            "replayed": bool(result.get("replay")),
        }

    async def list_for_field(self, caller: Caller, field_id: str, limit: int = 50) -> dict:
        self.settings.check()
        require(caller, FIELD_VIEW)
        limit = max(1, min(100, int(limit)))
        await self.store.require_field(caller, field_id)
        # Upstream failure stays an error even when local links happen to exist.
        feed = await self.client.discover(caller.tenant_id, self.settings.adapter_id, 100)
        links = await self.store.list_links(caller, field_id, limit)
        rows: dict[str, dict] = {}
        for link in links:
            binding = ExecutionBinding.from_record(link)
            context = await self.client.delivery_context(
                caller.tenant_id, binding.execution_request_id
            )
            state = "delivering"
            if context is not None:
                if (
                    context.get("execution_request_id") != binding.execution_request_id
                    or context.get("receipt_id") != binding.receipt_id
                    or context.get("tenant_id") != caller.tenant_id
                    or context.get("field_id") != field_id
                ):
                    raise refuse("delivery_context_mismatch", 503)
                state = "accepted"
            can_verify = False
            verification_reason = None
            try:
                _operator(caller, verification=True)
                await self.store.preview_confirmation(caller, link)
                can_verify = state == "accepted" and not link.get("outcome_id")
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409, 422}:
                    raise
                verification_reason = exc.detail
            if link.get("outcome_id"):
                state = "verified_success"
            rows[binding.execution_request_id] = {
                "execution_request_id": binding.execution_request_id,
                "field_id": field_id,
                "decision_id": binding.decision_id,
                "task_id": binding.task_id,
                "pin_id": binding.pin_id,
                "assigned_to": link.get("current_assigned_to", binding.assigned_to),
                "assignee_name": link.get("assignee_name"),
                "due_at": binding.due_at,
                "state": state,
                "can_receive": caller.role in {"owner", "manager"} and state == "delivering",
                "can_verify": can_verify,
                "verification_reason": verification_reason,
                "outcome_id": link.get("outcome_id"),
            }
        for item in feed["items"]:
            request_id = item.get("execution_request_id")
            if (
                request_id in rows
                or item.get("target_type") != "task"
                or item.get("operation_type") != OPERATION
            ):
                continue
            lineage = await self.client.lineage(
                caller.tenant_id, identifier(item.get("decision_id"))
            )
            decision = lineage.get("decision")
            if not isinstance(decision, dict):
                raise refuse("decision_lineage_unproven", 503)
            if decision.get("field_id") != field_id:
                continue
            try:
                plan = await self.client.plan(
                    caller.tenant_id, identifier(item.get("execution_plan_id"))
                )
                binding = binding_from_source(
                    caller, item, lineage, plan, field_id, self.settings.adapter_id
                )
                self.store.source_context(binding, item, lineage, plan)
                _operator(caller)
                assignee_name = await self.store.validate(caller, binding)
                row = {
                    "execution_request_id": request_id,
                    "field_id": field_id,
                    "decision_id": binding.decision_id,
                    "task_id": None,
                    "pin_id": binding.pin_id,
                    "assigned_to": binding.assigned_to,
                    "assignee_name": assignee_name,
                    "due_at": binding.due_at,
                    "state": item.get("discovery_state", "queued"),
                    "can_receive": True,
                    "can_verify": False,
                }
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409, 422}:
                    raise
                row = {
                    "execution_request_id": request_id,
                    "field_id": field_id,
                    "decision_id": item.get("decision_id"),
                    "task_id": None,
                    "state": "blocked",
                    "can_receive": False,
                    "can_verify": False,
                    "reason": exc.detail,
                }
            rows[request_id] = row
        return {
            "field_id": field_id,
            "items": list(rows.values())[:limit],
            "truncated": bool(feed["truncated"] or len(links) >= limit or len(rows) >= limit),
            "limit": limit,
        }


class HttpOwnerStore:
    """Authenticated owner port; the platform never opens a field DB connection.

    Source responses are retained only for this coordinator instance. The owner
    recomputes bindings from those source projections instead of accepting a
    client-chosen task ID, receipt, digest or actor. Delivery tokens never cross
    this channel. A separate HTTP readback follows the owner's committed create.
    """

    SCHEMA = "sahool.field-inspection-owner/v1"
    PREFIX = "/internal/field-inspection-execution-owner/"
    OPERATIONS = frozenset(
        {
            "require-field",
            "get-link",
            "list-links",
            "validate-binding",
            "ensure-task",
            "readback",
            "preview-confirmation",
            "prepare-confirmation",
            "save-outcome",
        }
    )
    CLAIM_KEYS = (
        "authoritative",
        "persisted",
        "execution_request_id",
        "adapter_id",
        "adapter_kind",
        "delivery_state",
    )

    def __init__(self, base_url: str, token: str, timeout: float = 8.0):
        try:
            parsed = urlsplit(base_url)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
            )
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise refuse("inspection_owner_url_unconfigured", 503)
        if not token.strip():
            raise refuse("inspection_coordinator_token_unconfigured", 503)
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token.strip(), timeout
        self._sources: dict[tuple[str, str], tuple[ExecutionBinding, dict]] = {}
        self._claims: dict[tuple[str, str], dict] = {}

    @classmethod
    def from_env(cls) -> HttpOwnerStore:
        return cls(
            os.getenv("FIELD_MANAGEMENT_SERVICE_URL", "http://sahool-field-management:8000"),
            os.getenv("FIELD_INSPECTION_COORDINATOR_TOKEN", ""),
        )

    def source_context(
        self, binding: ExecutionBinding, item: dict, lineage: dict, plan: dict
    ) -> None:
        self._sources[(binding.tenant_id, binding.execution_request_id)] = (
            binding,
            copy.deepcopy({"item": item, "lineage": lineage, "plan": plan}),
        )

    def claim_context(self, binding: ExecutionBinding, claim: dict) -> None:
        if (
            claim.get("authoritative") is not True
            or claim.get("persisted") is not True
            or claim.get("execution_request_id") != binding.execution_request_id
            or claim.get("adapter_id") != binding.adapter_id
            or claim.get("adapter_kind") != "task"
            or claim.get("delivery_state") != "delivering"
        ):
            raise refuse("execution_claim_unproven", 503)
        self._claims[(binding.tenant_id, binding.execution_request_id)] = {
            key: copy.deepcopy(claim[key]) for key in self.CLAIM_KEYS
        }

    def _source_body(self, caller: Caller, binding: ExecutionBinding) -> dict:
        context = self._sources.get((caller.tenant_id, binding.execution_request_id))
        if context is None or context[0] != binding or binding.received_by != caller.user_id:
            raise refuse("inspection_source_context_missing", 503)
        return {
            "field_id": binding.field_id,
            "execution_request_id": binding.execution_request_id,
            "source": copy.deepcopy(context[1]),
        }

    async def _request(self, caller: Caller, operation: str, body: dict):
        if operation not in self.OPERATIONS:
            raise refuse("inspection_owner_operation_unsupported", 422)
        try:
            tenant = str(UUID(caller.tenant_id))
            if tenant != caller.tenant_id or not str(caller.user_id).isdigit():
                raise ValueError("invalid trusted actor")
        except (ValueError, TypeError, AttributeError):
            raise refuse("inspection_owner_identity_invalid", 503) from None
        headers = {
            "X-Field-Inspection-Coordinator-Token": self.token,
            "X-Service-Name": "sahool-platform",
            "X-Tenant-Id": tenant,
            "X-User-Id": str(caller.user_id),
            "X-User-Role": caller.role,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    self.base_url + self.PREFIX + operation, headers=headers, json=body
                )
        except httpx.HTTPError:
            raise refuse("inspection_owner_unavailable", 503) from None
        if response.status_code != 200:
            status = response.status_code
            raise refuse(
                "inspection_owner_refused_" + str(status),
                status if status in {400, 403, 404, 409, 422} else 503,
            )
        if len(response.content) > 2 * 1024 * 1024:
            raise refuse("inspection_owner_response_too_large", 503)
        try:
            result = response.json()
        except ValueError:
            raise refuse("inspection_owner_invalid_response", 503) from None
        if (
            not isinstance(result, dict)
            or result.get("schema") != self.SCHEMA
            or result.get("authoritative") is not True
            or result.get("tenant_id") != tenant
            or result.get("operation") != operation
            or "data" not in result
        ):
            raise refuse("inspection_owner_invalid_response", 503)
        return result["data"]

    @staticmethod
    def _link(
        caller: Caller,
        value,
        *,
        request_id: str | None = None,
        field_id: str | None = None,
        expected: ExecutionBinding | None = None,
    ) -> dict:
        if not isinstance(value, dict):
            raise refuse("inspection_owner_link_unproven", 503)
        try:
            binding = ExecutionBinding.from_record(value)
        except (KeyError, ValueError, TypeError):
            raise refuse("inspection_owner_link_unproven", 503) from None
        if (
            binding.tenant_id != caller.tenant_id
            or (request_id is not None and binding.execution_request_id != request_id)
            or (field_id is not None and binding.field_id != field_id)
            or (expected is not None and asdict(binding) != asdict(expected))
        ):
            raise refuse("inspection_owner_link_unproven", 503)
        return value

    async def require_field(self, caller: Caller, field_id: str) -> None:
        result = await self._request(caller, "require-field", {"field_id": field_id})
        if result is not None:
            raise refuse("inspection_owner_field_unproven", 503)

    async def get_link(self, caller: Caller, request_id: str) -> dict | None:
        value = await self._request(
            caller, "get-link", {"execution_request_id": identifier(request_id)}
        )
        return None if value is None else self._link(caller, value, request_id=request_id)

    async def list_links(self, caller: Caller, field_id: str, limit: int) -> list[dict]:
        value = await self._request(caller, "list-links", {"field_id": field_id, "limit": limit})
        if not isinstance(value, list) or len(value) > limit:
            raise refuse("inspection_owner_links_unproven", 503)
        return [self._link(caller, item, field_id=field_id) for item in value]

    async def validate(self, caller: Caller, binding: ExecutionBinding) -> str | None:
        value = await self._request(caller, "validate-binding", self._source_body(caller, binding))
        if value is not None and not isinstance(value, str):
            raise refuse("inspection_owner_assignment_unproven", 503)
        return value

    async def ensure_task(self, caller: Caller, binding: ExecutionBinding) -> dict:
        body = self._source_body(caller, binding)
        claim = self._claims.get((caller.tenant_id, binding.execution_request_id))
        if claim is None:
            raise refuse("execution_claim_unproven", 503)
        body["claim"] = copy.deepcopy(claim)
        value = await self._request(caller, "ensure-task", body)
        return self._link(caller, value, expected=binding)

    async def readback(self, caller: Caller, binding: ExecutionBinding) -> dict:
        value = await self._request(
            caller,
            "readback",
            {
                "field_id": binding.field_id,
                "execution_request_id": binding.execution_request_id,
            },
        )
        return self._link(caller, value, expected=binding)

    async def preview_confirmation(self, caller: Caller, link: dict) -> dict:
        value = await self._request(
            caller, "preview-confirmation", {"execution_request_id": link["execution_request_id"]}
        )
        if (
            not isinstance(value, dict)
            or value.get("tenant_id") != caller.tenant_id
            or value.get("execution_request_id") != link["execution_request_id"]
        ):
            raise refuse("inspection_owner_confirmation_unproven", 503)
        return value

    async def prepare_confirmation(self, caller: Caller, task_id: str, field_id: str) -> dict:
        value = await self._request(
            caller, "prepare-confirmation", {"field_id": field_id, "task_id": task_id}
        )
        if (
            not isinstance(value, dict)
            or value.get("tenant_id") != caller.tenant_id
            or value.get("field_id") != field_id
            or value.get("task_id") != task_id
        ):
            raise refuse("inspection_owner_confirmation_unproven", 503)
        return value

    async def save_outcome(self, caller: Caller, proof: dict, result: dict) -> dict:
        value = await self._request(
            caller,
            "save-outcome",
            {
                "execution_request_id": proof["execution_request_id"],
                "confirmation_id": proof["confirmation_id"],
                "result": result,
            },
        )
        if (
            not isinstance(value, dict)
            or value.get("tenant_id") != caller.tenant_id
            or value.get("execution_request_id") != proof["execution_request_id"]
            or value.get("confirmation_id") != proof["confirmation_id"]
            or value.get("task_id") != proof["task_id"]
            or value.get("field_id") != proof["field_id"]
            or value.get("outcome_id") != result["outcome_id"]
        ):
            raise refuse("inspection_owner_outcome_ack_unproven", 503)
        return value


def build_adapter() -> ExecutionAdapter:
    settings = ExecutionSettings.from_env()
    settings.check()
    return ExecutionAdapter(HttpOwnerStore.from_env(), HttpDecisionClient.from_env(), settings)
