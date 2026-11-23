"""Internal service-to-service platform routes.

Extracted from api.main as a P1 residual-bootstrap decomposition step. These
routes remain service-token protected and preserve their paths/contracts.
"""

from __future__ import annotations

import asyncio

from core.canonical_field_state import compose_canonical_field_state
from core.canonical_schemas import UserRole
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api import main, soil_hydraulic_client
from api.service_token_auth import _require_service_token, verify_platform_internal_tenant

router = APIRouter()


class _ServiceUser:
    """هويّةُ الخدمة-لخدمة كـ**كائنِ مستخدِمٍ حقيقيّ** — لا مُعرِّفُ مستأجِرٍ عارٍ.

    `main.tenant_connection` تقرأ من وسيطها ثلاث سماتٍ (`tenant_id` · `user_id` ·
    `role`) لتضبط GUCات RLS الثلاثة. وكان هذا الملفّ يستدعي `main.tenant_connection_for`
    — **دالّةٌ لا وجودَ لها في `main.py` أصلاً** (مقيسٌ: مَرجِعا `main.X` غيرُ
    المعرَّفَين في كلّ خدمة المنصّة هما هذان السطران فحسب). فكلّ نداءٍ للمسارين كان
    يرفع `AttributeError` يبتلعه `except Exception` ويُترجَم **٥٠٣ «القاعدة غير
    متاحة»** — عطلُ برمجةٍ يُروى قصّةَ بنيةٍ تحتيّة.

    والعلاجُ ليس اختراعَ الدالّة الغائبة: سياقُ المستأجِر وحدَه (ضبطُ `app.current_tenant`
    بلا غيره) يترك `app.current_user_id` و`app.current_role` غيرَ مضبوطَين، و**٢٨ موضعاً في
    `migrations/*.sql` يقرؤهما**. فالهويّةُ تُصرَّح: مستأجِرٌ صريح، فاعلٌ خدميٌّ
    مُميَّزٌ في التدقيق، ودورُ `VIEWER` (أدنى صلاحيّة — لا `owner` ولا `platform_admin`).
    """

    __slots__ = ("role", "tenant_id", "user_id")

    def __init__(self, tenant_id: str, *, user_id: str = "service:internal") -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = UserRole.VIEWER


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
    ai_context: bool = Query(False, description="Attach the platform-owned AI context and policy."),
    engine_proposals: bool = Query(
        False,
        description="F8: stored owner-engine proposals only, for specialist review (read-only).",
    ),
    request: Request = None,
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

    # W0-05 (fields-5): the shared token says "a service"; the assertion says which tenant.
    await asyncio.to_thread(verify_platform_internal_tenant, request, tenant_id)
    if engine_proposals:
        return {"engine_proposals": await _stored_engine_proposals(tenant_id, field_id)}
    try:
        async with main.tenant_connection(_ServiceUser(tenant_id)) as conn:
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
    context_pack = None
    if ai_context is True:
        from api.routers.field_ai_context import field_ai_context_pack

        context_pack = await field_ai_context_pack(
            field_id,
            days=730,
            include_weather=True,
            include_imagery=True,
            include_events=True,
            user=_ServiceUser(tenant_id),
        )
        if hasattr(context_pack, "model_dump"):
            context_pack = context_pack.model_dump(mode="json")
    if canonical_state is None and context_pack is None:
        return result["state"]

    # الحالة تُركَّب داخليّاً لتغذية التوأم/التعلّم، لكنّ إرفاقها في الاستجابة يحكمه
    # عقد المعاملَين وحدهما: canonical صراحةً، أو twin (المشتقّ منها فيرافقها دليلاً).
    response = {"state": result["state"]}
    if context_pack is not None:
        response["ai_context_pack"] = context_pack
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
    request: Request,
    _: None = Depends(_require_service_token),
):
    """Record evidence-only AI advice as a domain event through the platform outbox."""
    # W0-05 (routes-5): the body's tenant_id must be the tenant the caller signed for.
    await asyncio.to_thread(verify_platform_internal_tenant, request, req.tenant_id)
    # هويّةٌ واحدة للمسارين — والصنفُ المحلّيُّ الذي كان هنا كان بلا `role` أصلاً،
    # فحتّى لو وُجِدت `tenant_connection_for` لَسقط تمريرُه إلى `tenant_connection`.
    actor = _ServiceUser(req.tenant_id, user_id="service:ai_agronomist")
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
    validation = None
    try:
        async with main.tenant_connection(actor) as conn:
            if req.field_id:
                await main._assert_field_in_tenant(conn, req.field_id)
            if req.model_output is not None:
                validation = await _preview_advice_facts(conn, req)
                payload["advisory_validation"] = validation
            # غير حرج بالتصميم (تسجيلٌ للأثر لا كتابةُ عمل)، لكنّ الردّ يجب أن يقول ما
            # حدث فعلاً: كان ``ok: True`` ثابتاً حتّى حين ابتُلع فشلُ الإصدار (التدقيق
            # الموحَّد 2026-09-13، P0). المُستهلِك (ai_agronomist) يعرض ``persisted``.
            persisted = await main._emit_domain_event(
                conn,
                actor,
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
        "ok": bool(persisted),
        "persisted": bool(persisted),
        "reason": None if persisted else "outbox_emit_failed_non_critical",
        "event_type": "ai.suggestion.generated",
        "entity_id": req.field_id or req.tenant_id,
        "advisory_validation": validation,
        "soil_sampling_plans": await _hand_plans_to_soil_service(req),
    }


# F8: the owner reads its own stored, recommendation-only irrigation schedules. SELECT only;
# the tenant is bound by RLS (tenant_connection) AND by this predicate.
_STORED_IRRIGATION_PROPOSALS_SQL = """
SELECT schedule_id::text AS schedule_id, tenant_id::text AS tenant_id, field_id, season_id,
       solver_version, status, recommendation_only, execution_allowed, horizon_start,
       horizon_hours, initial_depletion_mm, required_refill_mm, scheduled_irrigation_mm,
       scheduled_volume_m3, schedule_digest, payload, created_at
  FROM hourly_irrigation_mpc_schedules
 WHERE tenant_id = $1::uuid AND field_id = $2
 ORDER BY created_at DESC
 LIMIT 10
"""


async def load_stored_engine_proposals(conn, *, tenant_id: str, field_id: str) -> dict:
    """Proposals an owning engine already stored for this field — read, never computed."""
    from datetime import UTC, datetime
    from uuid import UUID

    from shared.ai import engine_proposal_review as review

    if not review.flag_enabled():
        return review.disabled_envelope(tenant_id=tenant_id, field_id=field_id)
    tenant_id = str(UUID(str(tenant_id)))
    rows = await conn.fetch(_STORED_IRRIGATION_PROPOSALS_SQL, tenant_id, field_id)
    return review.build_review(rows, tenant_id=tenant_id, field_id=field_id, now=datetime.now(UTC))


async def _stored_engine_proposals(tenant_id: str, field_id: str) -> dict:
    """F8 branch of the field-state route: stored proposals only, for specialist review.

    Returned alone (no field-state recompute) so this branch performs reads only. The flag is
    checked before a connection is opened; with it off the database is not touched.
    """
    from shared.ai import engine_proposal_review as review

    if not review.flag_enabled():
        return review.disabled_envelope(tenant_id=tenant_id, field_id=field_id)
    try:
        async with main.tenant_connection(_ServiceUser(tenant_id)) as conn:
            await main._assert_field_in_tenant(conn, field_id)
            return await load_stored_engine_proposals(conn, tenant_id=tenant_id, field_id=field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise main._db_unavailable("قراءة مقترحات المحرّكات المخزَّنة (خدمة)", e) from e


async def _hand_plans_to_soil_service(req) -> dict | None:
    """soil-service stores the plan copies (it owns them); the platform only forwards them.

    Non-critical for the advice event. A plan that did not reach soil-service is not resolvable,
    so a lab sample naming one of its points is refused later rather than stored unverified."""
    if not (req.field_id and req.soil_sampling_plans):
        return None
    try:
        return await soil_hydraulic_client.store_sampling_plan_copies(
            tenant_id=req.tenant_id,
            field_id=req.field_id,
            plans=req.soil_sampling_plans,
            source="ai_agronomist.plan_soil_sampling",
        )
    except soil_hydraulic_client.SamplingPlanVerificationUnavailable as exc:
        return {"stored": 0, "error": str(exc)[:200]}


async def _preview_advice_facts(conn, req) -> dict:
    """Reload owner data after generation; no model-authored action can cross here."""
    from core.field_intelligence_coordinator import preview_model_advisory

    from shared.ai.structured_advisory import AdvisoryRejected, digest

    async def current_state(**scope):
        return await _compose_canonical(conn, **scope)

    async def owner_candidates(**_scope):
        # Model-selectable catalog: stays empty by owner decision (F8) — the model must not
        # choose an action. Stored engine proposals reach the chat for specialist review only,
        # through _stored_engine_proposals (engine_proposals=true), never through this path.
        return []

    try:
        if not req.field_id:
            raise AdvisoryRejected("field_id_required")
        result = await preview_model_advisory(
            req.model_output,
            tenant_id=req.tenant_id,
            field_id=req.field_id,
            load_current_canonical=current_state,
            load_owner_candidates=owner_candidates,
            evaluate_candidate=None,
        )
        return {"status": "verified", "model_output_digest": digest(req.model_output), **result}
    except AdvisoryRejected as exc:
        return {"status": "blocked", "reason": str(exc)}


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
