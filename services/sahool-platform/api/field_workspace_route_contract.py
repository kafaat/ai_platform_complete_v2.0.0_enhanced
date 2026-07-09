"""api.field_workspace_route_contract — canonical Field Workspace route ownership.

UI-29 guardrail: Field Workspace endpoints must be owned by small façade routers,
not re-added into the historically large ``routers/fields.py`` module. This file is
intentionally declarative so CI can detect duplicate route drift without importing
FastAPI or connecting to external services.
"""

from __future__ import annotations

FIELD_WORKSPACE_ROUTE_OWNERSHIP: dict[str, str] = {
    "GET /api/v1/fields/{field_id}/readiness": "api.routers.field_readiness",
    "GET /api/v1/fields/{field_id}/data-completeness": "api.routers.field_completeness",
    "GET /api/v1/fields/{field_id}/priority-queue": "api.routers.field_priority_queue",
    "GET /api/v1/farms/{farm_id}/priority-queue": "api.routers.field_priority_queue",
    "GET /api/v1/fields/{field_id}/available-dates": "api.routers.field_workspace_imagery",
    "GET /api/v1/fields/{field_id}/imagery/timeline": "api.routers.field_workspace_imagery",
    "GET /api/v1/fields/{field_id}/weather/operation-windows": "api.routers.field_workspace_weather",
    "GET /api/v1/fields/{field_id}/weather/irrigation-advice": "api.routers.field_workspace_weather",
    "GET /api/v1/fields/{field_id}/weather/disease-risk": "api.routers.field_workspace_weather",
    "GET /api/v1/irrigation/schedules?field_id={field_id}": "api.routers.irrigation",
    # Still legacy-owned for now; UI-31+ can extract this once the event/timeline
    # assembler is split out of routers/fields.py safely.
    "GET /api/v1/fields/{field_id}/unified-timeline": "api.routers.field_workspace_timeline",
}

FIELD_WORKSPACE_FIELDS_ROUTER_BUDGET = {
    "allowed_workspace_routes": [],
    "reason": "Only unified timeline remains in routers/fields.py until timeline assembler extraction.",
}
