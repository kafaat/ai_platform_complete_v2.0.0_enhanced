"""Phase 12 Marketplace and Developer Platform API facade.

These FastAPI routes expose pure contracts from shared.marketplace_ecosystem_phase12.
They are intentionally side-effect-light until wired to persistent stores.
"""

from __future__ import annotations

try:
    from fastapi import APIRouter, Depends, HTTPException, Request
    from pydantic import BaseModel, Field

    from api.service_token_auth import _require_service_token
except Exception:  # pragma: no cover - lets py_compile pass in minimal envs
    APIRouter = None  # type: ignore
    HTTPException = Exception  # type: ignore
    BaseModel = object  # type: ignore

    def Field(default=None, **_kwargs):  # type: ignore
        return default


from api.phase_runtime_store import (
    persist_marketplace_app,
    persist_marketplace_installation,
    persist_usage_record,
    persist_webhook_subscription,
)
from shared.marketplace_ecosystem_phase12 import (
    build_developer_portal_index,
    build_graphql_facade_schema,
    build_plugin_sandbox_policy,
    build_public_sdk_manifest,
    create_webhook_subscription,
    define_connector_descriptor,
    enforce_quota,
    install_marketplace_app,
    plan_webhook_delivery,
    record_usage,
    register_marketplace_app,
    run_phase12_ecosystem_cycle,
    validate_plugin_manifest,
)
from shared.marketplace_plugin_runtime import (
    build_plugin_event_envelope,
    build_plugin_runtime_report,
    plan_plugin_execution,
    validate_plugin_output,
)

if APIRouter is not None:
    router = APIRouter(
        prefix="/v1/ecosystem",
        tags=["phase12-ecosystem"],
        dependencies=[Depends(_require_service_token)],
    )
else:  # pragma: no cover
    router = None


if BaseModel is not object:

    class ManifestRequest(BaseModel):
        manifest: dict = Field(default_factory=dict)
        category: str = "agronomy"

    class InstallRequest(BaseModel):
        app: dict = Field(default_factory=dict)
        tenant_id: str
        installed_by: str
        requested_permissions: list[str] | None = None

    class WebhookRequest(BaseModel):
        tenant_id: str
        url: str
        events: list[str]
        secret_ref: str

    class DeliveryRequest(BaseModel):
        subscription: dict
        event_type: str
        payload: dict = Field(default_factory=dict)
        secret: str

    class ConnectorRequest(BaseModel):
        name: str
        connector_type: str
        capabilities: list[str] = Field(default_factory=list)
        auth_mode: str = "oauth2"
        required_permissions: list[str] | None = None
        sync_modes: list[str] | None = None

    class UsageRequest(BaseModel):
        tenant_id: str
        app_id: str
        meter: str
        quantity: float
        idempotency_key: str
        metadata: dict = Field(default_factory=dict)

    class QuotaRequest(BaseModel):
        installation: dict
        usage_totals: dict = Field(default_factory=dict)
        requested: dict = Field(default_factory=dict)

    class PluginExecutionRequest(BaseModel):
        app: dict = Field(default_factory=dict)
        installation: dict = Field(default_factory=dict)
        action: str
        payload: dict = Field(default_factory=dict)
        usage_totals: dict = Field(default_factory=dict)
        idempotency_key: str | None = None

    class PluginOutputValidationRequest(BaseModel):
        plan: dict = Field(default_factory=dict)
        output: dict = Field(default_factory=dict)

    class PluginEventEnvelopeRequest(BaseModel):
        plan: dict = Field(default_factory=dict)
        event_type: str
        payload: dict = Field(default_factory=dict)
        schema_version: str = "1.0"

    class PluginRuntimeReportRequest(BaseModel):
        app: dict = Field(default_factory=dict)
        installation: dict = Field(default_factory=dict)
        actions: list[str] = Field(default_factory=list)


if router is not None:

    @router.post("/plugins/validate")
    def validate_plugin(req: ManifestRequest):
        return validate_plugin_manifest(req.manifest)

    @router.post("/marketplace/apps")
    async def create_marketplace_app(req: ManifestRequest, request: Request):
        result = register_marketplace_app(req.manifest, req.category)
        result["runtime_persistence"] = await persist_marketplace_app(request, result)
        return result

    @router.post("/marketplace/installations")
    async def install_app(req: InstallRequest, request: Request):
        result = install_marketplace_app(
            req.app, req.tenant_id, req.installed_by, req.requested_permissions
        )
        if not result.get("installed"):
            raise HTTPException(status_code=409, detail=result)
        result["runtime_persistence"] = await persist_marketplace_installation(
            request, result, req.app.get("app_id")
        )
        return result

    @router.post("/plugins/sandbox-policy")
    def sandbox_policy(req: ManifestRequest):
        return build_plugin_sandbox_policy(req.manifest)

    @router.post("/webhooks")
    async def create_webhook(req: WebhookRequest, request: Request):
        result = create_webhook_subscription(req.tenant_id, req.url, req.events, req.secret_ref)
        if not result.get("created"):
            raise HTTPException(status_code=400, detail=result)
        result["runtime_persistence"] = await persist_webhook_subscription(request, result)
        return result

    @router.post("/webhooks/delivery-plan")
    def webhook_delivery_plan(req: DeliveryRequest):
        return plan_webhook_delivery(req.subscription, req.event_type, req.payload, req.secret)

    @router.post("/connectors/descriptor")
    def connector_descriptor(req: ConnectorRequest):
        result = define_connector_descriptor(
            req.name,
            req.connector_type,
            req.capabilities,
            req.auth_mode,
            req.required_permissions,
            req.sync_modes,
        )
        if not result.get("valid"):
            raise HTTPException(status_code=400, detail=result)
        return result

    @router.get("/sdk/manifest")
    def sdk_manifest():
        return build_public_sdk_manifest()

    @router.get("/graphql/schema")
    def graphql_schema():
        return build_graphql_facade_schema()

    @router.get("/developer-portal/index")
    def developer_portal_index():
        return build_developer_portal_index()

    @router.post("/usage")
    async def usage_record(req: UsageRequest, request: Request):
        result = record_usage(
            req.tenant_id, req.app_id, req.meter, req.quantity, req.idempotency_key, req.metadata
        )
        if not result.get("recorded"):
            raise HTTPException(status_code=400, detail=result)
        result["runtime_persistence"] = await persist_usage_record(request, result)
        return result

    @router.post("/quota/check")
    def quota_check(req: QuotaRequest):
        return enforce_quota(req.installation, req.usage_totals, req.requested)

    @router.post("/plugins/runtime/plan")
    def plugin_runtime_plan(req: PluginExecutionRequest):
        return plan_plugin_execution(
            req.app,
            req.installation,
            req.action,
            req.payload,
            req.usage_totals,
            req.idempotency_key,
        )

    @router.post("/plugins/runtime/validate-output")
    def plugin_runtime_validate_output(req: PluginOutputValidationRequest):
        return validate_plugin_output(req.plan, req.output)

    @router.post("/plugins/runtime/event-envelope")
    def plugin_runtime_event_envelope(req: PluginEventEnvelopeRequest):
        result = build_plugin_event_envelope(
            req.plan, req.event_type, req.payload, req.schema_version
        )
        if not result.get("created"):
            raise HTTPException(status_code=400, detail=result)
        return result

    @router.post("/plugins/runtime/report")
    def plugin_runtime_report(req: PluginRuntimeReportRequest):
        return build_plugin_runtime_report(req.app, req.installation, req.actions)

    @router.post("/cycle")
    def ecosystem_cycle(req: ManifestRequest):
        return run_phase12_ecosystem_cycle(req.manifest)
