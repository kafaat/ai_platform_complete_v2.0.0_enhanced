"""
sahool_core.internal_orchestrator
==================================
المايسترو الداخلي v2 — يغلق فجوة "Contract Pipeline داخلياً".

الفجوة التي يُسدّها: قبل هذا، كان safe_delivery يحرس الطبقات الخارجية
فقط. لو استدعى أحد generate_recommendation مباشرة، يتخطّى cross_ref
+ provenance + auth. هذا الـorchestrator يضمن: كل استدعاء يمرّ في
خطّ القرار الكامل، حتى الاستدعاءات الداخلية.

الفرق عن safe_delivery:
  • safe_delivery: نقطة دخول خارجية (API/Workers)
  • internal_orchestrator: نقطة دخول داخلية (recommendation_engine V2)

النمط: side-by-side with V1
  • generate_recommendation (V1) يبقى كما هو للتوافق
  • orchestrate_recommendation (V2) هو النقطة الموصى بها
  • الاستدعاءات تهاجر تدريجياً، لا breaking change

المبادئ المحفوظة:
  • النواة محايدة: لا API specifics، لا framework dependencies
  • Composition: يستخدم generate_recommendation داخلياً، لا يستبدله
  • Fail closed: شكّ في الـcontract = منع التسليم
  • التأجيل ≠ الإغلاق: V1 يبقى متاحاً، V2 يُختار صراحةً

التكامل (الحلقة المغلقة الكاملة):
  user request
    → orchestrate_recommendation (V2)
      → authorize (RBAC + tenant + farm)
        → enrich_with_context (cross_reference)
          → generate_recommendation (V1، يبقى كما هو)
            → enforce_pipeline (Contract Gate)
              → EnrichedRecommendation مع provenance
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from core.authorization import Permission, authorize
from core.canonical_schemas import UserSchema
from core.cross_reference_finder import (
    SearchContext,
    cross_reference_summary,
    find_similar_recommendations,
)
from core.recommendation_bridge import (
    ContextPipelineError,
    EnrichedRecommendation,
    build_provenance,
    enforce_pipeline,
)
from core.recommendation_engine import Recommendation, generate_recommendation

try:  # Safe defaults keep legacy behavior unless explicitly enabled.
    from config.guardrail_feature_flags import (
        ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
        ENABLE_PONYTAIL_GUARDRAILS,
        REQUIRE_CANONICAL_FIELD_STATE,
    )
except Exception:  # pragma: no cover - config package may be absent in embedded tests
    ENABLE_PONYTAIL_GUARDRAILS = False
    ENABLE_LEGACY_RECOMMENDATION_FALLBACK = True
    REQUIRE_CANONICAL_FIELD_STATE = True

from core.guardrails import (
    EvidenceSummary,
    FieldStateSnapshot,
    PonytailAction,
    PonytailIntent,
    RecommendationPonytail,
)


def _infer_ponytail_intent(
    *, issue_type: str | None, is_pesticide: bool, irrigation, validation: dict | None
) -> PonytailIntent:
    issue = (issue_type or "").lower()
    if is_pesticide or issue in {"pesticide", "spraying", "spray"}:
        return PonytailIntent(
            type="pesticide",
            complexity="prescription",
            field_id=str((validation or {}).get("field_id", "")),
        )
    if issue in {"fertilization", "fertiliser", "fertilizer", "nutrient"}:
        return PonytailIntent(
            type="fertilization",
            complexity="prescription",
            field_id=str((validation or {}).get("field_id", "")),
        )
    if irrigation is not None or issue in {"irrigation", "water"}:
        return PonytailIntent(
            type="irrigation",
            complexity="prescription",
            field_id=str((validation or {}).get("field_id", "")),
        )
    return PonytailIntent(
        type="general",
        complexity="diagnostic",
        field_id=str((validation or {}).get("field_id", "")),
    )


def _field_state_snapshot_from_inputs(
    *, validation: dict | None, irrigation, current_indicators: dict | None
) -> FieldStateSnapshot:
    confidence = 0.85 if (validation or {}).get("quality_grade") == "READY" else 0.5
    if isinstance((validation or {}).get("confidence"), (int, float)):
        confidence = float((validation or {}).get("confidence"))
    weather_state = None
    irrigation_state = None
    if irrigation is not None:
        if hasattr(irrigation, "__dict__"):
            irrigation_state = dict(irrigation.__dict__)
        elif isinstance(irrigation, dict):
            irrigation_state = irrigation
        else:
            irrigation_state = {"value": str(irrigation)}
        weather_state = {"et0": irrigation_state.get("et0_mm"), "source": "irrigation_input"}
    return FieldStateSnapshot(
        irrigation_state=irrigation_state,
        weather_state=weather_state,
        satellite_state=current_indicators or None,
        lab_state=(validation or {}).get("lab_state"),
        confidence=confidence,
    )


def _evidence_from_inputs(
    *, validation: dict | None, irrigation, current_indicators: dict | None
) -> EvidenceSummary:
    validation = validation or {}
    lab_state = validation.get("lab_state") or {}
    return EvidenceSummary(
        has_lab=bool(validation.get("has_lab") or lab_state),
        has_weather=bool(irrigation is not None or validation.get("has_weather")),
        has_satellite=bool(current_indicators),
        has_rag=False,
        has_kg=False,
    )


def _blocked_by_ponytail_response(
    *, rec_id: str, reason: str, cross_ref: dict | None, provenance: dict | None, auth_decision
) -> EnrichedRecommendation:
    return EnrichedRecommendation(
        rec_id=rec_id,
        base_recommendation={"guardrail_blocked": True},
        cross_reference=cross_ref
        or {"count": 0, "note_ar": "لم يُجرَ بحث — حارس Ponytail منع المسار"},
        provenance=provenance or {},
        auth_decision=asdict(auth_decision),
        delivered=False,
        reason_ar=reason,
        timestamp=datetime.now().isoformat(),
    )


def orchestrate_recommendation(
    *,
    user: UserSchema,
    tenant_id: str,
    farm_id: str,
    field_id: str,
    crop: str,
    # مدخلات generate_recommendation (V1):
    validation: dict,
    irrigation=None,
    suitability=None,
    zone_factor: float | None = None,
    zone_factor_status: str = "pending",
    local_knowledge: list | None = None,
    field_state: str | None = None,
    # سياق إضافي لخطّ القرار:
    recommendation_history: list | None = None,
    current_indicators: dict | None = None,
    growth_stage: str | None = None,
    issue_type: str | None = None,
    district_id: str | None = None,
    engines_used: list[str] | None = None,
    weather_source: str = "open-meteo",
    is_pesticide: bool = False,
) -> EnrichedRecommendation:
    """المايسترو الداخلي — يفرض كل الطبقات في خطّ القرار.

    على عكس generate_recommendation (V1) الذي يُنتج Recommendation خام،
    هذا يُنتج EnrichedRecommendation مع cross_ref + provenance + auth.

    استخدمه:
    - عند بناء recommendation_engine V2
    - في any internal service يطلب توصية
    - بدلاً من generate_recommendation المباشرة

    Fail closed: إن فشل أيّ طبقة، delivered=False مع سبب صريح."""

    # 1. AUTHORIZATION — قبل أيّ حساب (Fail fast)
    perm = Permission.PESTICIDE_APPROVE if is_pesticide else Permission.RECOMMENDATION_REQUEST
    auth_decision = authorize(user, perm, resource_tenant_id=tenant_id, farm_id=farm_id)

    rec_id = f"rec_{tenant_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if not auth_decision.allowed:
        # رفض مبكّر — لا حساب توصية لمستخدم بلا صلاحية
        return EnrichedRecommendation(
            rec_id=rec_id,
            base_recommendation={},
            cross_reference={"count": 0, "note_ar": "لم يُجرَ بحث — صلاحية مرفوضة"},
            provenance={},
            auth_decision=asdict(auth_decision),
            delivered=False,
            reason_ar=auth_decision.reason_ar,
            timestamp=datetime.now().isoformat(),
        )

    # 2. CROSS-REFERENCE — كشف الأنماط التاريخية المشابهة
    search_ctx = SearchContext(
        tenant_id=tenant_id,
        field_id=field_id,
        crop=crop,
        growth_stage=growth_stage,
        issue_type=issue_type,
        current_indicators=current_indicators,
        district_id=district_id,
    )
    similar = find_similar_recommendations(
        search_ctx,
        recommendation_history or [],
        min_similarity=0.3,
    )
    cross_ref = cross_reference_summary(similar)

    # 3. PROVENANCE — لقطة كاملة قبل تشغيل المحرّك (forensic)
    provenance = build_provenance(
        engines_used=engines_used or [],
        weather_source=weather_source,
        weather_data_date=datetime.now().date().isoformat(),
        input_snapshot=current_indicators or {},
    )

    # 4. PONYTAIL GUARDRAIL GATE — optional runtime gate with legacy fallback.
    # The flag defaults OFF, so existing production paths remain stable until CI enables it.
    if ENABLE_PONYTAIL_GUARDRAILS:
        ponytail = RecommendationPonytail()
        ponytail_decision = ponytail.filter(
            _infer_ponytail_intent(
                issue_type=issue_type,
                is_pesticide=is_pesticide,
                irrigation=irrigation,
                validation=validation,
            ),
            _field_state_snapshot_from_inputs(
                validation=validation, irrigation=irrigation, current_indicators=current_indicators
            ),
            _evidence_from_inputs(
                validation=validation, irrigation=irrigation, current_indicators=current_indicators
            ),
        )
        if ponytail_decision.action in {
            PonytailAction.INSUFFICIENT_EVIDENCE,
            PonytailAction.SIMPLIFY,
        }:
            return _blocked_by_ponytail_response(
                rec_id=rec_id,
                reason=f"Ponytail guardrail: {ponytail_decision.reason}",
                cross_ref=cross_ref,
                provenance=provenance,
                auth_decision=auth_decision,
            )

    # 5. CORE ENGINE (V1) — يبقى كما هو، لا تعديل
    try:
        v1_result: Recommendation = generate_recommendation(
            validation=validation,
            irrigation=irrigation,
            suitability=suitability,
            zone_factor=zone_factor,
            zone_factor_status=zone_factor_status,
            local_knowledge=local_knowledge,
            field_state=field_state,
        )
    except Exception as e:
        # خطأ داخلي في V1 — نُسجّله صراحةً، لا نُخفيه
        return EnrichedRecommendation(
            rec_id=rec_id,
            base_recommendation={"error": str(e)},
            cross_reference=cross_ref,
            provenance=provenance,
            auth_decision=asdict(auth_decision),
            delivered=False,
            reason_ar=f"خطأ في المحرّك V1: {str(e)[:100]}",
            timestamp=datetime.now().isoformat(),
        )

    # 6. ASSEMBLE — التوصية المُغنّاة
    enriched = EnrichedRecommendation(
        rec_id=rec_id,
        base_recommendation=v1_result.to_log_dict(),
        cross_reference=cross_ref,
        provenance=provenance,
        auth_decision=asdict(auth_decision),
        delivered=True,
        reason_ar=f"مُسلَّمة: {v1_result.status.value}",
        timestamp=datetime.now().isoformat(),
    )

    # 7. CONTRACT GATE — لا تسليم إن نقص شيء (Fail closed)
    try:
        enforce_pipeline(enriched)
    except ContextPipelineError:
        # enriched عُدِّلت داخل enforce_pipeline (delivered=False)
        pass

    return enriched


def orchestrator_summary(delivery: EnrichedRecommendation) -> dict:
    """ملخّص للسجلّات والتشخيص.

    يكشف: هل اجتاز الـpipeline؟ كم سياق تاريخي استُخدم؟ أيّ نسخ نماذج؟"""
    return {
        "rec_id": delivery.rec_id,
        "delivered": delivery.delivered,
        "reason_ar": delivery.reason_ar,
        "auth_role": delivery.auth_decision.get("role"),
        "auth_permission": delivery.auth_decision.get("permission"),
        "historical_matches": delivery.cross_reference.get("count", 0),
        "model_versions_count": len(delivery.provenance.get("model_versions", {})),
        "weather_source": delivery.provenance.get("weather_source"),
        "timestamp": delivery.timestamp,
    }
