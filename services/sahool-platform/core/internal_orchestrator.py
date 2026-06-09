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
    SearchContext, find_similar_recommendations,
    cross_reference_summary)
from core.recommendation_bridge import (
    EnrichedRecommendation, build_provenance,
    enforce_pipeline, ContextPipelineError)
from core.recommendation_engine import (
    generate_recommendation, Recommendation, RecommendationStatus)
from core.skills_registry import model_versions_snapshot


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
    perm = (Permission.PESTICIDE_APPROVE if is_pesticide
            else Permission.RECOMMENDATION_REQUEST)
    auth_decision = authorize(user, perm,
                              resource_tenant_id=tenant_id,
                              farm_id=farm_id)

    rec_id = f"rec_{tenant_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if not auth_decision.allowed:
        # رفض مبكّر — لا حساب توصية لمستخدم بلا صلاحية
        return EnrichedRecommendation(
            rec_id=rec_id,
            base_recommendation={},
            cross_reference={"count": 0,
                            "note_ar": "لم يُجرَ بحث — صلاحية مرفوضة"},
            provenance={},
            auth_decision=asdict(auth_decision),
            delivered=False,
            reason_ar=auth_decision.reason_ar,
            timestamp=datetime.now().isoformat(),
        )

    # 2. CROSS-REFERENCE — كشف الأنماط التاريخية المشابهة
    search_ctx = SearchContext(
        tenant_id=tenant_id, field_id=field_id, crop=crop,
        growth_stage=growth_stage, issue_type=issue_type,
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

    # 4. CORE ENGINE (V1) — يبقى كما هو، لا تعديل
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

    # 5. ASSEMBLE — التوصية المُغنّاة
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

    # 6. CONTRACT GATE — لا تسليم إن نقص شيء (Fail closed)
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
        "model_versions_count": len(
            delivery.provenance.get("model_versions", {})),
        "weather_source": delivery.provenance.get("weather_source"),
        "timestamp": delivery.timestamp,
    }
