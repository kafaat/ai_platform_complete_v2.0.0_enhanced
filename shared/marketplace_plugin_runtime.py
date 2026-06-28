"""Phase 12 marketplace plugin runtime guardrails.

This module turns the marketplace contracts into a deterministic runtime safety
layer.  It does not execute untrusted code; it builds auditable execution plans,
sandbox contexts, quota projections, event envelopes and output validation
contracts that production adapters can later bind to gVisor/Firecracker/Docker,
Kong, Redis, NATS and billing systems.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json

from shared.marketplace_ecosystem_phase12 import (
    DEFAULT_QUOTAS,
    KNOWN_HOOKS,
    SENSITIVE_PERMISSIONS,
    build_plugin_sandbox_policy,
    enforce_plugin_permission,
    enforce_quota,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:14]}"


class PluginAction(str, Enum):
    FIELD_CONTEXT_READ = "field.context.read"
    RASTER_TILE_READ = "raster.tile.read"
    RECOMMENDATION_PROPOSE = "recommendation.propose"
    ALERT_CREATE = "alert.create"
    WEBHOOK_EMIT = "webhook.emit"
    MODEL_PROMOTION_REQUEST = "model.promotion.request"
    AUTONOMY_DISPATCH_REQUEST = "autonomy.dispatch.request"


ACTION_PERMISSIONS: dict[str, str] = {
    PluginAction.FIELD_CONTEXT_READ.value: "field.read",
    PluginAction.RASTER_TILE_READ.value: "tiles.read",
    PluginAction.RECOMMENDATION_PROPOSE.value: "recommendations.write",
    PluginAction.ALERT_CREATE.value: "alerts.write",
    PluginAction.WEBHOOK_EMIT.value: "webhooks.write",
    PluginAction.MODEL_PROMOTION_REQUEST.value: "model.promote",
    PluginAction.AUTONOMY_DISPATCH_REQUEST.value: "autonomy.dispatch",
}


ACTION_METERS: dict[str, str] = {
    PluginAction.FIELD_CONTEXT_READ.value: "api_calls_day",
    PluginAction.RASTER_TILE_READ.value: "tiles_day",
    PluginAction.RECOMMENDATION_PROPOSE.value: "api_calls_day",
    PluginAction.ALERT_CREATE.value: "api_calls_day",
    PluginAction.WEBHOOK_EMIT.value: "webhooks_day",
    PluginAction.MODEL_PROMOTION_REQUEST.value: "api_calls_day",
    PluginAction.AUTONOMY_DISPATCH_REQUEST.value: "api_calls_day",
}


class PluginRuntimeDecision(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True)
class PluginExecutionPlan:
    execution_id: str
    tenant_id: str
    app_id: str
    installation_id: str
    action: str
    decision: str
    required_permission: str
    sandbox_policy: dict[str, Any]
    quota_projection: dict[str, Any]
    idempotency_key: str
    payload_digest: str
    created_at: str
    audit_level: str
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _payload_digest(payload: dict[str, Any] | None) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _manifest_from_app(app: dict[str, Any]) -> dict[str, Any]:
    return app.get("manifest") or {}


def _quota_request_for_action(action: str) -> dict[str, float]:
    meter = ACTION_METERS.get(action, "api_calls_day")
    return {meter: 1.0}


def build_sandbox_runtime_context(app: dict[str, Any], installation: dict[str, Any], action: str) -> dict[str, Any]:
    """Build the least-privilege runtime context given to a plugin runner.

    The context intentionally contains references and capabilities, not raw
    secrets, database URLs, NATS credentials, or direct filesystem paths.
    """
    manifest = _manifest_from_app(app)
    policy = build_plugin_sandbox_policy(manifest)
    granted = tuple(sorted(set(installation.get("granted_permissions", []))))
    return {
        "sandbox_context_id": _stable_id({"app": app.get("app_id"), "installation": installation.get("installation_id"), "action": action}, "ctx"),
        "app_id": app.get("app_id"),
        "tenant_id": installation.get("tenant_id"),
        "installation_id": installation.get("installation_id"),
        "action": action,
        "capabilities": {
            "permissions": granted,
            "network": policy.get("network"),
            "filesystem": policy.get("filesystem"),
            "secrets": policy.get("secrets"),
            "cpu_seconds": policy.get("cpu_seconds"),
            "memory_mb": policy.get("memory_mb"),
        },
        "denied_capabilities": ["direct_db", "raw_nats", "host_filesystem", "unscoped_secrets", "physical_actuation"],
        "runtime_env": {
            "SAHOOL_PLUGIN_APP_ID": str(app.get("app_id")),
            "SAHOOL_TENANT_ID": str(installation.get("tenant_id")),
            "SAHOOL_INSTALLATION_ID": str(installation.get("installation_id")),
            "SAHOOL_ACTION": action,
        },
        "policy": policy,
    }


def plan_plugin_execution(
    app: dict[str, Any],
    installation: dict[str, Any],
    action: str,
    payload: dict[str, Any] | None = None,
    usage_totals: dict[str, float] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create an auditable fail-closed execution plan for a plugin action."""
    required_permission = ACTION_PERMISSIONS.get(action)
    reasons: list[str] = []
    if not required_permission:
        required_permission = "unknown"
        reasons.append("unknown_action")

    if app.get("status") != "approved":
        reasons.append("app_not_approved")
    if installation.get("status") != "active":
        reasons.append("installation_not_active")
    if app.get("app_id") and installation.get("app_id") and app.get("app_id") != installation.get("app_id"):
        reasons.append("installation_app_mismatch")

    permission = enforce_plugin_permission(installation, required_permission) if required_permission != "unknown" else {"allowed": False, "reason": "unknown_action"}
    if not permission.get("allowed"):
        reasons.append(str(permission.get("reason") or "permission_denied"))

    requested_quota = _quota_request_for_action(action)
    quota = enforce_quota({"quota": installation.get("quota") or DEFAULT_QUOTAS}, usage_totals or {}, requested_quota)
    if not quota.get("allowed"):
        reasons.append("quota_exceeded")

    sandbox_context = build_sandbox_runtime_context(app, installation, action)
    sensitive = required_permission in SENSITIVE_PERMISSIONS
    requires_human_approval = sensitive or bool(sandbox_context["policy"].get("human_approval_required_for_actuation"))
    if requires_human_approval:
        reasons.append("requires_human_approval")

    decision = PluginRuntimeDecision.DENY.value if any(r in reasons for r in ("unknown_action", "app_not_approved", "installation_not_active", "installation_app_mismatch", "permission_denied", "quota_exceeded")) else PluginRuntimeDecision.REVIEW.value if requires_human_approval else PluginRuntimeDecision.ALLOW.value
    idem = idempotency_key or _stable_id({"app": app.get("app_id"), "installation": installation.get("installation_id"), "action": action, "payload": payload}, "idem")
    plan = PluginExecutionPlan(
        execution_id=_stable_id({"idem": idem, "action": action}, "plugrun"),
        tenant_id=str(installation.get("tenant_id")),
        app_id=str(app.get("app_id")),
        installation_id=str(installation.get("installation_id")),
        action=action,
        decision=decision,
        required_permission=required_permission,
        sandbox_policy=sandbox_context["policy"],
        quota_projection=quota,
        idempotency_key=idem,
        payload_digest=_payload_digest(payload),
        created_at=_now(),
        audit_level="elevated" if sensitive or requires_human_approval else "standard",
        reasons=tuple(sorted(set(reasons))),
    )
    return {"plan": plan.to_dict(), "sandbox_context": sandbox_context, "allowed_to_execute": decision == PluginRuntimeDecision.ALLOW.value}


def build_plugin_event_envelope(
    plan: dict[str, Any],
    event_type: str,
    payload: dict[str, Any] | None = None,
    schema_version: str = "1.0",
) -> dict[str, Any]:
    """Build a sanitized event envelope for plugin-originated events."""
    if event_type not in KNOWN_HOOKS and not event_type.startswith("plugin."):
        return {"created": False, "reason": "event_type_not_allowed", "event_type": event_type}
    safe_payload = dict(payload or {})
    for forbidden in ("secret", "password", "token", "api_key", "DATABASE_URL", "NATS_URL"):
        safe_payload.pop(forbidden, None)
    envelope = {
        "event_id": _stable_id({"plan": plan.get("execution_id"), "event": event_type, "payload": safe_payload}, "plug_evt"),
        "event_type": event_type,
        "schema_version": schema_version,
        "tenant_id": plan.get("tenant_id"),
        "app_id": plan.get("app_id"),
        "installation_id": plan.get("installation_id"),
        "execution_id": plan.get("execution_id"),
        "created_at": _now(),
        "payload": safe_payload,
        "audit_level": plan.get("audit_level", "standard"),
    }
    return {"created": True, "envelope": envelope}


def validate_plugin_output(plan: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """Validate plugin output before it can affect SAHOOL runtime state.

    Plugins may propose changes, but they cannot directly write field state,
    execute physical commands or promote models. Sensitive effects must be
    routed to the appropriate governed workflow.
    """
    findings: list[str] = []
    allowed_effects: list[str] = []
    blocked_effects: list[str] = []
    effects = output.get("effects") or []
    if not isinstance(effects, list):
        findings.append("effects_must_be_list")
        effects = []

    for effect in effects:
        kind = str((effect or {}).get("kind") or "")
        if kind in {"direct_db_write", "raw_nats_publish", "host_file_write", "secret_read"}:
            blocked_effects.append(kind)
            findings.append(f"blocked_effect:{kind}")
        elif kind in {"actuator_command", "autonomy_dispatch"}:
            blocked_effects.append(kind)
            findings.append("actuation_must_use_phase9_iot_adapter")
        elif kind == "model_promote":
            blocked_effects.append(kind)
            findings.append("model_promotion_must_use_phase10_registry")
        elif kind in {"recommendation_proposal", "alert_proposal", "webhook_event", "field_annotation"}:
            allowed_effects.append(kind)
        else:
            blocked_effects.append(kind or "unknown")
            findings.append(f"unknown_effect:{kind or 'unknown'}")

    valid = not findings and plan.get("decision") == PluginRuntimeDecision.ALLOW.value
    return {
        "valid": valid,
        "findings": findings,
        "allowed_effects": allowed_effects,
        "blocked_effects": blocked_effects,
        "requires_review": bool(blocked_effects) or plan.get("decision") == PluginRuntimeDecision.REVIEW.value,
        "execution_id": plan.get("execution_id"),
    }


def build_plugin_runtime_report(app: dict[str, Any], installation: dict[str, Any], actions: list[str]) -> dict[str, Any]:
    plans = [plan_plugin_execution(app, installation, action, payload={}, usage_totals={})["plan"] for action in actions]
    decisions = {p["decision"] for p in plans}
    return {
        "report_id": _stable_id({"app": app.get("app_id"), "installation": installation.get("installation_id"), "actions": actions}, "plug_report"),
        "created_at": _now(),
        "app_id": app.get("app_id"),
        "installation_id": installation.get("installation_id"),
        "tenant_id": installation.get("tenant_id"),
        "summary": {
            "actions_checked": len(plans),
            "all_allowed": decisions == {PluginRuntimeDecision.ALLOW.value},
            "has_review": PluginRuntimeDecision.REVIEW.value in decisions,
            "has_denied": PluginRuntimeDecision.DENY.value in decisions,
        },
        "plans": plans,
    }
