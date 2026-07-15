"""Internal service-to-service platform routes.

Extracted from api.main as a P1 residual-bootstrap decomposition step. These
routes remain service-token protected and preserve their paths/contracts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api import main
from api.service_token_auth import _require_service_token

router = APIRouter()


@router.get("/api/v1/internal/fields/{field_id}")
async def internal_get_field(
    field_id: str,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    _: None = Depends(_require_service_token),
):
    """Service-to-service field read for tenant-scoped consumers (e.g. vegetation
    analysis) that hold a service token but no user JWT.

    Contract (SEC-3):
      • service-token only — ``_require_service_token`` (X-Agent-Token); a user JWT
        alone is rejected. Never widens the public ``get_field`` authz.
      • tenant is taken from the verified ``X-Tenant-Id`` header (the caller derives it
        from a verified user JWT), never from body/query. Missing ⇒ 400.
      • the query is scoped by BOTH field_id AND tenant_id under RLS (app.current_tenant),
        so a field owned by another tenant is indistinguishable from a missing one ⇒ 404
        (no cross-tenant existence disclosure).
    """
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required for internal field read")
    from api.field_models import _FIELD_DETAIL_SELECT, _row_to_field_detail

    try:
        pool = main.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await main._apply_tenant_guc(conn, x_tenant_id)
                row = await conn.fetchrow(
                    f"SELECT {_FIELD_DETAIL_SELECT} FROM fields "
                    "WHERE field_id = $1 AND tenant_id = $2::uuid",
                    field_id,
                    str(x_tenant_id),
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise main._db_unavailable("قراءة الحقل الداخليّة (خدمة)", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    return _row_to_field_detail(row)


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
