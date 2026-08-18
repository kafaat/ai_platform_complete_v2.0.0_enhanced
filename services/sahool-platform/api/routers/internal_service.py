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
        description="أرفِق canonical_field_state.v1 المُركَّب من منتجات المُلّاك.",
    ),
    twin: bool = Query(
        False,
        description="أرفِق Field Digital Twin مشتقاً فقط من canonical_field_state.",
    ),
    learning_model_id: str | None = Query(
        None,
        description=(
            "اختياري: أرفِق ملخص دليل التعلّم المتحقق لهذا الحقل من decision-service. "
            "لا fallback إلى execution_ledger."
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
            need_canonical = canonical or twin or bool(learning_model_id)
            canonical_state = (
                await _compose_canonical(conn, tenant_id=tenant_id, field_id=field_id)
                if need_canonical
                else None
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise main._db_unavailable("قراءة الحالة القانونيّة (خدمة)", e) from e
    if canonical_state is None:
        return result["state"]

    # الحالة تُركَّب داخليّاً لتغذية التوأم/التعلّم، لكنّ إرفاقها في الاستجابة يحكمه
    # عقد المعاملَين وحدهما: canonical صراحةً، أو twin (المشتقّ منها فيرافقها دليلاً).
    response = {"state": result["state"]}
    if canonical or twin:
        response["canonical_field_state"] = canonical_state
    if twin:
        from dataclasses import asdict

        from core.field_digital_twin import build_field_twin_from_canonical_state

        response["field_twin"] = asdict(build_field_twin_from_canonical_state(canonical_state))

    if learning_model_id:
        from api.decision_service_client import get_calibration_dataset

        try:
            season_id = canonical_state.get("season_id")
            if not season_id:
                response["twin_learning_evidence"] = {
                    "available": False,
                    "source_authority": "decision-service/verified-calibration-dataset",
                    "reason": "authoritative_verified_dataset_unavailable:no_active_season",
                    "verified_outcome_count": 0,
                    "auto_promoted": False,
                }
                return response
            dataset = await get_calibration_dataset(
                model_id=learning_model_id,
                field_id=field_id,
                season_id=season_id,
                limit=500,
                tenant_id=tenant_id,
            )
            verified = dataset.get("authoritative") is True and dataset.get("read_only") is True
            response["twin_learning_evidence"] = {
                "available": verified,
                "source_authority": "decision-service/verified-calibration-dataset",
                "verified_outcome_count": int(dataset.get("count", 0)) if verified else 0,
                "weighted_success_rate": dataset.get("weighted_success_rate") if verified else None,
                "dataset_fingerprint": dataset.get("dataset_fingerprint") if verified else None,
                "agronomic_cohort_fingerprint": (
                    dataset.get("agronomic_cohort_fingerprint") if verified else None
                ),
                "by_decision_type": dataset.get("by_decision_type", {}) if verified else {},
                "auto_promoted": False,
            }
        except HTTPException as exc:
            response["twin_learning_evidence"] = {
                "available": False,
                "source_authority": "decision-service/verified-calibration-dataset",
                "reason": f"authoritative_verified_dataset_unavailable:{exc.status_code}",
                "verified_outcome_count": 0,
                "auto_promoted": False,
            }
    return response


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
    from api.persisted_canonical_repositories import load_active_season_id
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

    season_id = await load_active_season_id(conn, field_id=field_id)

    state = compose_canonical_field_state(
        field_id=field_id,
        season_id=season_id,
        as_of_time=datetime.now(UTC).isoformat(),
        water=water_payload,
        soil=soil_payload,
        weather=weather_payload,
        spectral=spectral_payload,
    )
    return state.to_dict()
