"""Internal service-to-service platform routes.

Extracted from api.main as a P1 residual-bootstrap decomposition step. These
routes remain service-token protected and preserve their paths/contracts.
"""

from __future__ import annotations

from core.canonical_field_state import compose_canonical_field_state
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
    canonical: bool = Query(
        False,
        description=(
            "أرفِق canonical_field_state.v1 المُركَّب من المنتَجات المتاحة. "
            "يعود operational_eligible=false ما دام الطقس غير مُتاح كغلاف كنسيّ."
        ),
    ),
    _: None = Depends(_require_service_token),
):
    """الحالة القانونيّة للحقل لقنوات الخدمة (supervisor→guardrails).

    مع ``canonical=true`` يُرفَق ``canonical_field_state.v1`` المُركَّب من **منتَجات الحالة
    المتاحة فعلاً** في المنصّة، بلا مسار جديد (سابقة INT-004A).

    حدّ صدق صريح: العقد يشترط ``weather`` و``water`` و``soil``؛ والمنصّة تُحلّ **الماء**
    (``api/canonical_water_state.py``)، و**التربة** (``api/canonical_soil_state.py`` — عميل
    HTTP لِـ``soil-service``'s ``/v1/fields/{field_id}/soil/profile``)، و**الطيف**
    (``api/canonical_spectral_state.py`` — منتَج raster المُتحقَّق، غير مشترط في العقد).

    الطقس يُحل الآن من ``weather-service /v1/weather/current`` عند مركز الحقل؛ ذلك المسار
    يجلب من المزوّد عند حافة مالك الطقس ثم يبني ``CanonicalWeatherState`` قبل إخراج الـview.
    المنصّة لا تعيد حساب أي حقيقة طقس: تقبل فقط view يحمل ``canonical_state_id`` ونسخة الحالة
    و``source_snapshot_id``؛ غياب أيٍّ منها يُعامل كغياب صريح ويُبقي الحالة fail-closed.
    """
    from api.field_state_projection import recompute_field_state

    try:
        async with main.tenant_connection_for(tenant_id) as conn:
            await main._assert_field_in_tenant(conn, field_id)
            result = await recompute_field_state(conn, field_id)
            canonical_state = (
                await _compose_canonical(conn, tenant_id=tenant_id, field_id=field_id)
                if canonical
                else None
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise main._db_unavailable("قراءة الحالة القانونيّة (خدمة)", e) from e
    if canonical_state is None:
        return result["state"]
    return {"state": result["state"], "canonical_field_state": canonical_state}


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


async def _compose_canonical(conn, *, tenant_id: str, field_id: str) -> dict:
    """يُركّب canonical_field_state من المنتَجات المتاحة فعلاً — ولا يختلق الغائب.

    المنتَج الغائب يُمرَّر ``None`` فتُسمّيه النواة في ``limitations`` وتُسقِط
    ``operational_eligible``. البديل الوحيد المرفوض هو تلفيق منتَج بمخطّط صحيح ومحتوى
    مُختلَق لإرضاء العقد — وهو ما يجعل الحالة تبدو صالحة وهي ليست كذلك.
    """
    from datetime import UTC, datetime

    from api.canonical_soil_state import resolve_canonical_soil_state
    from api.canonical_spectral_state import resolve_canonical_spectral_state
    from api.canonical_water_state import resolve_canonical_water_state
    from api.weather_service_client import get_canonical_field_weather

    water = await resolve_canonical_water_state(conn, tenant_id=tenant_id, field_id=field_id)
    water_payload = water if isinstance(water, dict) else water.to_dict()
    if str(water_payload.get("schema_version") or "") == "":
        water_payload = None  # حمولة محجوبة بلا مخطّط ⇒ غياب مُعلَن لا قبول صامت

    soil_payload = await resolve_canonical_soil_state(tenant_id=tenant_id, field_id=field_id)
    spectral_payload = await resolve_canonical_spectral_state(
        tenant_id=tenant_id, field_id=field_id
    )

    # Field coordinates are stored with the field and are the only spatial input here.
    # weather-service remains the owner of provider I/O and canonical weather semantics.
    coords = await conn.fetchrow(
        "SELECT lat, lon FROM fields WHERE field_id=$1 AND tenant_id=$2::uuid",
        field_id,
        tenant_id,
    )
    weather_payload = None
    if coords and coords["lat"] is not None and coords["lon"] is not None:
        weather_payload = await get_canonical_field_weather(
            float(coords["lat"]), float(coords["lon"]), tenant_id=tenant_id
        )

    state = compose_canonical_field_state(
        field_id=field_id,
        season_id=None,
        as_of_time=datetime.now(UTC).isoformat(),
        water=water_payload,
        soil=soil_payload,
        weather=weather_payload,
        spectral=spectral_payload,
    )
    return state.to_dict()
