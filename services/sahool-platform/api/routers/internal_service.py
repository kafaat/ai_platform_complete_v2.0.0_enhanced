"""Internal service-to-service platform routes.

Extracted from api.main as a P1 residual-bootstrap decomposition step. These
routes remain service-token protected and preserve their paths/contracts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api import main
from api.service_token_auth import _require_service_token

router = APIRouter()

# NOTE: the tenant-scoped internal field READ routes (GET /api/v1/internal/fields
# and /api/v1/internal/fields/{field_id}) were MOVED off the platform to the new
# field-management-service (the declared owner of the `fields` table per
# docs/architecture/db_ownership.yml). vegetation-analysis now reads fields from
# FIELD_SERVICE_URL/internal/fields[...] with its service token. Keeping those reads
# here duplicated ownership and exceeded the platform route budget.


@router.get("/internal/fields/{field_id}/state")
async def internal_field_state(
    field_id: str,
    tenant_id: str = Query(..., description="معرّف المستأجِر الصريح (خدمة-لخدمة)"),
    _: None = Depends(_require_service_token),
):
    """الحالة القانونيّة للحقل لقنوات الخدمة (supervisor→guardrails)."""
    from api.field_state_projection import recompute_field_state

    try:
        async with main.tenant_connection_for(tenant_id) as conn:
            await main._assert_field_in_tenant(conn, field_id)
            result = await recompute_field_state(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise main._db_unavailable("قراءة الحالة القانونيّة (خدمة)", e) from e
    return result["state"]


@router.post("/internal/events/ai-advice")
async def internal_ai_advice_event(
    req: main.InternalAIAdviceEventRequest,
    _: None = Depends(_require_service_token),
):
    """Record evidence-only AI advice as a domain event through the platform outbox."""

    class _ServiceUser:
        tenant_id = req.tenant_id
        user_id = "service:ai_agronomist"

    payload = {
        "field_id": req.field_id,
        "question": req.question,
        "evidence_ids": req.evidence_ids[:20],
        "confidence": req.confidence,
        "selected_imagery_date": req.selected_imagery_date,
        "endpoint_mode": req.endpoint_mode,
        "decision_authority": "field_intelligence_coordinator",
        "runtime": "ai_agronomist",
    }
    try:
        async with main.tenant_connection_for(req.tenant_id) as conn:
            if req.field_id:
                await main._assert_field_in_tenant(conn, req.field_id)
            await main._emit_domain_event(
                conn,
                _ServiceUser(),
                "AI_SUGGESTION",
                "field" if req.field_id else "tenant",
                req.field_id or req.tenant_id,
                payload,
                critical=False,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise main._db_unavailable("تسجيل حدث مستشار الذكاء", e) from e
    return {
        "ok": True,
        "event_type": "ai.suggestion.generated",
        "entity_id": req.field_id or req.tenant_id,
    }
