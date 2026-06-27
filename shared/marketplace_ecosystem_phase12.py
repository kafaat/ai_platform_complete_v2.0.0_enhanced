"""Phase 12 Marketplace, Plugin Ecosystem, and Developer Platform.

This module adds deterministic, dependency-light contracts for turning SAHOOL
from a closed platform into an ecosystem: plugins, marketplace apps,
installations, webhooks, connector descriptors, SDK manifests, GraphQL schema
facades, usage metering, quota enforcement, and developer portal documents.

The code is deliberately pure-Python so CI can validate the governance and
permission logic without external services. Production adapters can later back
these contracts with Postgres, Redis, Kong, Stripe, OpenAPI/GraphQL servers, and
sandboxed plugin runners.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


class PluginStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"


class InstallStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ConnectorType(str, Enum):
    ERP = "erp"
    EQUIPMENT = "equipment"
    WEATHER = "weather"
    SATELLITE = "satellite"
    IOT = "iot"
    PAYMENTS = "payments"


class WebhookDeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


SENSITIVE_PERMISSIONS = {
    "actuator.write",
    "autonomy.dispatch",
    "billing.write",
    "tenant.admin",
    "model.promote",
    "field.delete",
}

KNOWN_PERMISSIONS = {
    "field.read",
    "field.write",
    "field.delete",
    "weather.read",
    "raster.read",
    "tiles.read",
    "recommendations.read",
    "recommendations.write",
    "digital_twin.read",
    "operations.read",
    "operations.write",
    "alerts.read",
    "alerts.write",
    "billing.read",
    "billing.write",
    "webhooks.write",
    "model.read",
    "model.promote",
    "actuator.write",
    "autonomy.dispatch",
    "tenant.admin",
}

KNOWN_HOOKS = {
    "field.updated",
    "recommendation.before",
    "recommendation.after",
    "recommendation.created",
    "alert.created",
    "operation.completed",
    "model.promoted",
    "billing.usage.recorded",
    "digital_twin.snapshot.created",
}

DEFAULT_QUOTAS = {
    "api_calls_day": 10_000,
    "tiles_day": 50_000,
    "webhooks_day": 5_000,
    "inference_minutes_day": 120,
    "storage_mb": 2_000,
}


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    author: str
    description: str = ""
    permissions: tuple[str, ...] = field(default_factory=tuple)
    hooks: tuple[str, ...] = field(default_factory=tuple)
    entrypoint: str = ""
    min_platform_version: str = "1.0.0"
    billing_meter: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketplaceApp:
    app_id: str
    manifest: PluginManifest
    category: str
    status: str
    risk_level: str
    review_findings: tuple[str, ...]
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["manifest"] = self.manifest.to_dict()
        return data


@dataclass(frozen=True)
class AppInstallation:
    installation_id: str
    app_id: str
    tenant_id: str
    granted_permissions: tuple[str, ...]
    status: str
    installed_by: str
    installed_at: str
    quota: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebhookSubscription:
    webhook_id: str
    tenant_id: str
    url: str
    events: tuple[str, ...]
    secret_ref: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectorDescriptor:
    connector_id: str
    name: str
    connector_type: str
    capabilities: tuple[str, ...]
    auth_mode: str
    required_permissions: tuple[str, ...]
    sync_modes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UsageRecord:
    tenant_id: str
    app_id: str
    meter: str
    quantity: float
    idempotency_key: str
    recorded_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_plugin_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a user/plugin manifest into a strict internal contract."""
    manifest = PluginManifest(
        name=str(raw.get("name") or "").strip(),
        version=str(raw.get("version") or "").strip(),
        author=str(raw.get("author") or "").strip(),
        description=str(raw.get("description") or "").strip(),
        permissions=tuple(str(p).strip() for p in raw.get("permissions", []) if str(p).strip()),
        hooks=tuple(str(h).strip() for h in raw.get("hooks", []) if str(h).strip()),
        entrypoint=str(raw.get("entrypoint") or "").strip(),
        min_platform_version=str(raw.get("min_platform_version") or "1.0.0").strip(),
        billing_meter=raw.get("billing_meter"),
    )
    return manifest.to_dict()


def validate_plugin_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    manifest = PluginManifest(**parse_plugin_manifest(raw))
    findings: list[str] = []
    if not manifest.name:
        findings.append("missing_name")
    if not manifest.version:
        findings.append("missing_version")
    if not manifest.author:
        findings.append("missing_author")
    unknown_permissions = sorted(set(manifest.permissions) - KNOWN_PERMISSIONS)
    unknown_hooks = sorted(set(manifest.hooks) - KNOWN_HOOKS)
    if unknown_permissions:
        findings.append("unknown_permissions:" + ",".join(unknown_permissions))
    if unknown_hooks:
        findings.append("unknown_hooks:" + ",".join(unknown_hooks))
    if len(manifest.permissions) != len(set(manifest.permissions)):
        findings.append("duplicate_permissions")
    if len(manifest.hooks) != len(set(manifest.hooks)):
        findings.append("duplicate_hooks")
    if not manifest.entrypoint:
        findings.append("missing_entrypoint")

    sensitive = sorted(set(manifest.permissions) & SENSITIVE_PERMISSIONS)
    risk_score = 0
    risk_score += len(manifest.permissions)
    risk_score += len(sensitive) * 4
    risk_score += 2 if manifest.billing_meter else 0
    risk_level = "low" if risk_score <= 5 else "medium" if risk_score <= 12 else "high"
    requires_security_review = bool(sensitive or risk_level == "high")
    valid = not findings
    return {
        "valid": valid,
        "manifest": manifest.to_dict(),
        "findings": findings,
        "unknown_permissions": unknown_permissions,
        "unknown_hooks": unknown_hooks,
        "sensitive_permissions": sensitive,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "requires_security_review": requires_security_review,
    }


def register_marketplace_app(
    raw_manifest: dict[str, Any], category: str = "agronomy"
) -> dict[str, Any]:
    review = validate_plugin_manifest(raw_manifest)
    manifest = PluginManifest(**review["manifest"])
    app = MarketplaceApp(
        app_id=_stable_id({"manifest": manifest.to_dict(), "category": category}, "app"),
        manifest=manifest,
        category=category,
        status=PluginStatus.REVIEW.value
        if review["requires_security_review"] or not review["valid"]
        else PluginStatus.APPROVED.value,
        risk_level=review["risk_level"],
        review_findings=tuple(review["findings"]),
        published_at=_now() if review["valid"] and not review["requires_security_review"] else None,
    )
    return {"app": app.to_dict(), "review": review}


def install_marketplace_app(
    app: dict[str, Any],
    tenant_id: str,
    installed_by: str,
    requested_permissions: list[str] | None = None,
) -> dict[str, Any]:
    manifest = app.get("manifest", {})
    status = app.get("status")
    if status != PluginStatus.APPROVED.value:
        return {
            "installed": False,
            "reason": "app_not_approved",
            "app_id": app.get("app_id"),
            "tenant_id": tenant_id,
        }
    allowed = set(manifest.get("permissions", []))
    requested = set(requested_permissions or manifest.get("permissions", []))
    denied = sorted(requested - allowed)
    if denied:
        return {
            "installed": False,
            "reason": "permission_not_declared",
            "denied_permissions": denied,
        }
    granted = tuple(sorted(requested))
    installation = AppInstallation(
        installation_id=_stable_id(
            {"app_id": app.get("app_id"), "tenant_id": tenant_id, "granted": granted}, "install"
        ),
        app_id=str(app.get("app_id")),
        tenant_id=tenant_id,
        granted_permissions=granted,
        status=InstallStatus.ACTIVE.value,
        installed_by=installed_by,
        installed_at=_now(),
        quota=dict(DEFAULT_QUOTAS),
    )
    return {"installed": True, "installation": installation.to_dict()}


def enforce_plugin_permission(installation: dict[str, Any], permission: str) -> dict[str, Any]:
    if installation.get("status") != InstallStatus.ACTIVE.value:
        return {"allowed": False, "reason": "installation_not_active"}
    granted = set(installation.get("granted_permissions", []))
    if permission not in granted:
        return {"allowed": False, "reason": "permission_denied", "required": permission}
    if permission in SENSITIVE_PERMISSIONS:
        return {"allowed": True, "requires_elevated_audit": True, "permission": permission}
    return {"allowed": True, "requires_elevated_audit": False, "permission": permission}


def build_plugin_sandbox_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    permissions = set(manifest.get("permissions", []))
    network_allowed = bool(permissions & {"weather.read", "raster.read", "tiles.read"})
    write_allowed = any(p.endswith(".write") for p in permissions)
    actuation_allowed = "actuator.write" in permissions or "autonomy.dispatch" in permissions
    return {
        "sandbox": "restricted",
        "filesystem": "read_only",
        "network": "egress_allowlist" if network_allowed else "disabled",
        "secrets": "tenant_scoped_refs_only",
        "cpu_seconds": 30,
        "memory_mb": 256,
        "write_allowed": write_allowed,
        "actuation_allowed": actuation_allowed,
        "human_approval_required_for_actuation": actuation_allowed,
        "audit_level": "elevated"
        if actuation_allowed or permissions & SENSITIVE_PERMISSIONS
        else "standard",
    }


def create_webhook_subscription(
    tenant_id: str, url: str, events: list[str], secret_ref: str
) -> dict[str, Any]:
    normalized_events = tuple(sorted(set(str(e).strip() for e in events if str(e).strip())))
    unknown_events = sorted(set(normalized_events) - KNOWN_HOOKS)
    if unknown_events:
        return {"created": False, "reason": "unknown_events", "unknown_events": unknown_events}
    if not (url.startswith("https://") or url.startswith("http://localhost")):
        return {"created": False, "reason": "insecure_webhook_url"}
    subscription = WebhookSubscription(
        webhook_id=_stable_id(
            {"tenant_id": tenant_id, "url": url, "events": normalized_events}, "wh"
        ),
        tenant_id=tenant_id,
        url=url,
        events=normalized_events,
        secret_ref=secret_ref,
        active=True,
    )
    return {"created": True, "webhook": subscription.to_dict()}


def sign_webhook_payload(payload: dict[str, Any], secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def plan_webhook_delivery(
    subscription: dict[str, Any], event_type: str, payload: dict[str, Any], secret: str
) -> dict[str, Any]:
    if not subscription.get("active"):
        return {
            "status": WebhookDeliveryStatus.DEAD_LETTER.value,
            "reason": "subscription_inactive",
        }
    if event_type not in set(subscription.get("events", [])):
        return {"status": "ignored", "reason": "event_not_subscribed"}
    envelope = {
        "event_id": _stable_id(
            {
                "event_type": event_type,
                "payload": payload,
                "webhook_id": subscription.get("webhook_id"),
            },
            "evt",
        ),
        "event_type": event_type,
        "tenant_id": subscription.get("tenant_id"),
        "created_at": _now(),
        "payload": payload,
    }
    return {
        "status": WebhookDeliveryStatus.PENDING.value,
        "target_url": subscription.get("url"),
        "headers": {
            "X-Sahool-Event": event_type,
            "X-Sahool-Signature": sign_webhook_payload(envelope, secret),
            "Content-Type": "application/json",
        },
        "envelope": envelope,
        "retry_policy": {"max_attempts": 8, "backoff": "exponential", "dead_letter_after": "24h"},
    }


def define_connector_descriptor(
    name: str,
    connector_type: str,
    capabilities: list[str],
    auth_mode: str = "oauth2",
    required_permissions: list[str] | None = None,
    sync_modes: list[str] | None = None,
) -> dict[str, Any]:
    if connector_type not in {c.value for c in ConnectorType}:
        return {
            "valid": False,
            "reason": "unknown_connector_type",
            "connector_type": connector_type,
        }
    descriptor = ConnectorDescriptor(
        connector_id=_stable_id(
            {"name": name, "type": connector_type, "capabilities": capabilities}, "conn"
        ),
        name=name,
        connector_type=connector_type,
        capabilities=tuple(sorted(set(capabilities))),
        auth_mode=auth_mode,
        required_permissions=tuple(sorted(set(required_permissions or ["field.read"]))),
        sync_modes=tuple(sorted(set(sync_modes or ["incremental", "backfill"]))),
    )
    return {"valid": True, "connector": descriptor.to_dict()}


def build_public_sdk_manifest(platform_url: str = "https://api.sahool.local") -> dict[str, Any]:
    resources = {
        "fields": ["list", "get", "history", "geometry_revisions"],
        "weather": ["current", "forecast", "operation_windows"],
        "recommendations": ["generate", "approve", "lifecycle", "feedback"],
        "digital_twin": ["snapshot", "scenario"],
        "marketplace": ["apps", "install", "usage"],
        "webhooks": ["create", "test", "deliveries"],
    }
    return {
        "base_url": platform_url.rstrip("/"),
        "languages": ["python", "typescript", "flutter"],
        "auth": ["api_key", "oauth2_client_credentials", "tenant_scoped_jwt"],
        "resources": resources,
        "examples": {
            "python": "client.fields.list()",
            "typescript": "await client.recommendations.generate({ fieldId })",
            "flutter": "await sahool.digitalTwin.snapshot(fieldId)",
        },
    }


def build_graphql_facade_schema() -> dict[str, Any]:
    types = {
        "Field": ["id", "name", "geometry", "crop", "latestState", "recommendations"],
        "CanonicalFieldState": ["fieldId", "confidence", "operationalTruths", "missingSignals"],
        "Recommendation": ["id", "action", "status", "lifecycle", "feedback"],
        "DigitalTwin": ["field", "weather", "soil", "water", "economics", "scenarios"],
        "MarketplaceApp": ["id", "name", "version", "category", "permissions", "status"],
    }
    queries = [
        "field(id: ID!)",
        "fields",
        "digitalTwin(fieldId: ID!)",
        "marketplaceApps",
        "recommendations(fieldId: ID!)",
    ]
    mutations = [
        "installApp(appId: ID!)",
        "createWebhook(input: WebhookInput!)",
        "approveRecommendation(id: ID!)",
    ]
    return {
        "schema_id": _stable_id(
            {"types": types, "queries": queries, "mutations": mutations}, "graphql"
        ),
        "types": types,
        "queries": queries,
        "mutations": mutations,
    }


def record_usage(
    tenant_id: str,
    app_id: str,
    meter: str,
    quantity: float,
    idempotency_key: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qty = _num(quantity)
    if qty < 0:
        return {"recorded": False, "reason": "negative_quantity"}
    record = UsageRecord(
        tenant_id=tenant_id,
        app_id=app_id,
        meter=meter,
        quantity=qty,
        idempotency_key=idempotency_key,
        recorded_at=_now(),
        metadata=metadata or {},
    )
    return {
        "recorded": True,
        "usage": record.to_dict(),
        "usage_id": _stable_id(record.to_dict(), "usage"),
    }


def enforce_quota(
    installation: dict[str, Any], usage_totals: dict[str, float], requested: dict[str, float]
) -> dict[str, Any]:
    quota = installation.get("quota", DEFAULT_QUOTAS)
    violations: list[str] = []
    projections: dict[str, float] = {}
    for meter, amount in requested.items():
        current = _num(usage_totals.get(meter))
        projected = current + _num(amount)
        projections[meter] = projected
        limit = quota.get(meter)
        if limit is not None and projected > float(limit):
            violations.append(meter)
    return {
        "allowed": not violations,
        "violations": violations,
        "projections": projections,
        "quota": quota,
        "mode": "enforce" if violations else "allow",
    }


def build_developer_portal_index() -> dict[str, Any]:
    sections = [
        {"slug": "getting-started", "title": "Getting Started", "required": True},
        {"slug": "authentication", "title": "Authentication and Tenant Scope", "required": True},
        {"slug": "sdks", "title": "SDKs", "required": True},
        {"slug": "webhooks", "title": "Webhooks and Event Signatures", "required": True},
        {"slug": "plugins", "title": "Plugin Manifest and Sandbox", "required": True},
        {"slug": "connectors", "title": "Connector Framework", "required": False},
        {"slug": "billing", "title": "Usage Metering and Quotas", "required": True},
        {"slug": "sandbox", "title": "Developer Sandbox", "required": False},
    ]
    return {
        "portal_id": _stable_id(sections, "portal"),
        "sections": sections,
        "status": "ready_for_static_site",
    }


def run_phase12_ecosystem_cycle(
    manifest: dict[str, Any],
    tenant_id: str = "tenant-demo",
    installed_by: str = "admin-demo",
    webhook_secret: str = "dev-secret",
) -> dict[str, Any]:
    registration = register_marketplace_app(manifest)
    app = registration["app"]
    sandbox = build_plugin_sandbox_policy(app["manifest"])
    install = install_marketplace_app(app, tenant_id=tenant_id, installed_by=installed_by)
    webhook = create_webhook_subscription(
        tenant_id=tenant_id,
        url="https://example.com/sahool/webhook",
        events=["recommendation.created", "operation.completed"],
        secret_ref="secret/demo",
    )
    delivery = (
        plan_webhook_delivery(
            webhook.get("webhook", {}),
            "recommendation.created",
            {"recommendation_id": "rec-1", "app_id": app["app_id"]},
            webhook_secret,
        )
        if webhook.get("created")
        else {"status": "skipped"}
    )
    sdk = build_public_sdk_manifest()
    graphql = build_graphql_facade_schema()
    portal = build_developer_portal_index()
    usage = record_usage(tenant_id, app["app_id"], "api_calls_day", 1, "idem-1")
    quota = (
        enforce_quota(
            install.get("installation", {"quota": DEFAULT_QUOTAS}),
            {"api_calls_day": 0},
            {"api_calls_day": 1},
        )
        if install.get("installed")
        else {"allowed": False, "reason": "not_installed"}
    )
    return {
        "cycle_id": _stable_id({"manifest": manifest, "tenant_id": tenant_id}, "ecosystem"),
        "registration": registration,
        "sandbox_policy": sandbox,
        "installation": install,
        "webhook": webhook,
        "delivery_plan": delivery,
        "sdk_manifest": sdk,
        "graphql_schema": graphql,
        "developer_portal": portal,
        "usage": usage,
        "quota": quota,
    }
