"""
sahool_core.recommendation_bridge
===================================
جسر التكامل — يربط النواة الجديدة (cross_reference + authorization +
provenance) مع recommendation_engine الموجود **بدون تعديله**.

نمط Non-invasive Integration: لا نُعدّل recommendation_engine (الذي
عمل بدقّة عبر جلسات). بدلاً من ذلك، نلفّ مخرجاته بطبقة جديدة:

  recommendation_engine.make_recommendation(field_context)
              ↓
  enrich_with_context(rec) — يُضيف:
    • cross_reference_summary (حالات تاريخية مشابهة)
    • model_versions_snapshot (لـreplay drift detection)
    • provenance كامل
              ↓
  authorize_and_deliver(user, enriched_rec) — يحرس:
    • tenant isolation
    • role permissions
    • farm access
              ↓
  توصية مُسلَّمة، مُتتبَّعة، مُحرَّسة

المبادئ:
  • Non-invasive: المايسترو القديم لا يتغيّر (التوافق الخلفي)
  • Composition over modification: نضيف، لا نُعدّل
  • Single Responsibility: كل وحدة تفعل شيئاً واحداً
  • Fail closed: شكّ في الصلاحية = رفض

التكامل (الحلقة الكاملة):
  user request → authorize → recommendation_engine → enrich →
  recommendation_log (مع provenance) → returned to user
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from core.authorization import Permission, authorize, is_safety_critical_permission
from core.canonical_schemas import UserSchema
from core.cross_reference_finder import (
    SearchContext,
    cross_reference_summary,
    find_similar_recommendations,
)
from core.skills_registry import model_versions_snapshot


@dataclass
class EnrichedRecommendation:
    """توصية مُغنّاة بـcontext تاريخي + provenance + auth decision."""

    rec_id: str
    base_recommendation: dict  # ما أنتجه recommendation_engine
    cross_reference: dict  # حالات تاريخية مشابهة
    provenance: dict  # model_versions + weather + snapshot
    auth_decision: dict  # قرار الصلاحية
    delivered: bool  # هل وصلت للمستخدم؟
    reason_ar: str
    timestamp: str = ""


def build_provenance(
    engines_used: list[str],
    weather_source: str,
    weather_data_date: str,
    input_snapshot: dict,
    calibration_set_id: str | None = None,
    knowledge_snippets_ids: list | None = None,
) -> dict:
    """يبني provenance قياسي. يدمج model_versions تلقائياً من registry.

    هذه نقطة التوحيد: كل توصية تمرّ هنا تحصل على provenance كامل."""
    return {
        "model_versions": model_versions_snapshot(),
        "weather_source": weather_source,
        "weather_data_date": weather_data_date,
        "input_snapshot": input_snapshot,
        "engines_used": engines_used,
        "calibration_set_id": calibration_set_id,
        "knowledge_snippets_ids": knowledge_snippets_ids or [],
        "snapshot_taken_at": datetime.now().isoformat(),
    }


def enrich_with_context(
    base_rec: dict,
    *,
    tenant_id: str,
    field_id: str,
    crop: str,
    recommendation_history: list,
    current_indicators: dict | None = None,
    growth_stage: str | None = None,
    issue_type: str | None = None,
    engines_used: list[str] | None = None,
    weather_source: str = "open-meteo",
    district_id: str | None = None,
) -> dict:
    """يُغني توصية أساسية بحالات تاريخية + provenance.

    لا يُعدّل التوصية، يُضيف context. recommendation_engine يبقى كما هو."""
    # ١. البحث عن حالات مشابهة (Karpathy Connection Finder)
    search_ctx = SearchContext(
        tenant_id=tenant_id,
        field_id=field_id,
        crop=crop,
        growth_stage=growth_stage,
        issue_type=issue_type,
        current_indicators=current_indicators,
        district_id=district_id,  # ← يُمرّر للـsame_district الصريح
    )
    similar = find_similar_recommendations(search_ctx, recommendation_history, min_similarity=0.3)
    cross_ref = cross_reference_summary(similar)

    # ٢. بناء provenance
    prov = build_provenance(
        engines_used=engines_used or [],
        weather_source=weather_source,
        weather_data_date=datetime.now().date().isoformat(),
        input_snapshot=current_indicators or {},
    )

    # ٣. الإغناء (لا تعديل، إضافة)
    return {
        **base_rec,
        "cross_reference": cross_ref,
        "provenance": prov,
        "has_historical_context": cross_ref.get("count", 0) > 0,
    }


def authorize_and_deliver(
    user: UserSchema,
    enriched_rec: dict,
    *,
    tenant_id: str,
    farm_id: str | None = None,
    is_pesticide: bool = False,
) -> EnrichedRecommendation:
    """يحرس التوصية بصلاحيات RBAC قبل تسليمها.

    Fail closed: شكّ = رفض. كل قرار يحمل سبباً."""
    # تحديد الصلاحية المطلوبة
    perm = Permission.PESTICIDE_APPROVE if is_pesticide else Permission.RECOMMENDATION_REQUEST

    decision = authorize(user, perm, resource_tenant_id=tenant_id, farm_id=farm_id)

    # توليد rec_id قابل للتتبّع
    rec_id = (
        enriched_rec.get("rec_id") or f"rec_{tenant_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    result = EnrichedRecommendation(
        rec_id=rec_id,
        base_recommendation=enriched_rec.get("base", enriched_rec),
        cross_reference=enriched_rec.get("cross_reference", {}),
        provenance=enriched_rec.get("provenance", {}),
        auth_decision=asdict(decision),
        delivered=decision.allowed,
        reason_ar=decision.reason_ar,
        timestamp=datetime.now().isoformat(),
    )

    # تحذير إضافي للصلاحيات الحرجة (مبدأ السلامة لا تُتخطّى)
    if decision.allowed and is_safety_critical_permission(perm):
        # نُسلّمها، لكن نُعلِم بالحساسية (للتسجيل)
        result.reason_ar += " [صلاحية حرجة — مُسجَّلة في audit]"

    return result


def full_delivery_pipeline(
    *,
    user: UserSchema,
    tenant_id: str,
    field_id: str,
    farm_id: str,
    crop: str,
    base_recommendation: dict,  # من recommendation_engine
    recommendation_history: list,
    current_indicators: dict | None = None,
    growth_stage: str | None = None,
    issue_type: str | None = None,
    engines_used: list[str] | None = None,
    is_pesticide: bool = False,
    district_id: str | None = None,
) -> EnrichedRecommendation:
    """الخطّ الكامل: توصية أساسية → إغناء → حراسة → تسليم.

    هذه نقطة الدخول الموصى بها للطبقات الخارجية (API، Workers).
    لا تستدعي recommendation_engine نفسها — تأخذ مخرجها."""

    # 1. الإغناء بالسياق
    enriched = enrich_with_context(
        base_recommendation,
        tenant_id=tenant_id,
        field_id=field_id,
        crop=crop,
        recommendation_history=recommendation_history,
        current_indicators=current_indicators,
        growth_stage=growth_stage,
        issue_type=issue_type,
        engines_used=engines_used,
        district_id=district_id,
    )

    # 2. الحراسة والتسليم
    return authorize_and_deliver(
        user,
        {**enriched, "rec_id": base_recommendation.get("rec_id")},
        tenant_id=tenant_id,
        farm_id=farm_id,
        is_pesticide=is_pesticide,
    )


def delivery_summary(delivery: EnrichedRecommendation) -> str:
    """ملخّص قابل للقراءة. للتسجيل والتشخيص."""
    if not delivery.delivered:
        return f"⛔ رفض: {delivery.reason_ar}"
    cross = delivery.cross_reference
    historical = cross.get("count", 0)
    snap = delivery.provenance.get("model_versions", {})
    return (
        f"✅ مُسلَّمة (id={delivery.rec_id}). "
        f"حالات تاريخية: {historical}. "
        f"نسخ نماذج: {len(snap)}. "
        f"{delivery.reason_ar}"
    )


# ─── Contract Enforcement: المايسترو الذي يفرض الخطوات ───────────


class ContextPipelineError(Exception):
    """يُرفع عند محاولة تخطّي خطوة إلزامية في خطّ القرار.

    معالج "memory layer خارج مسار القرار": الـpipeline يجعل
    cross_reference + provenance + authorization إلزامية صراحةً،
    لا يعتمد على نيّة المستدعي."""


@dataclass
class PipelineRequirements:
    """ما يجب توفّره قبل أيّ توصية. Fail closed إن نقص شيء."""

    has_tenant_context: bool
    has_field_context: bool
    has_cross_reference: bool
    has_provenance: bool
    has_authorization: bool
    missing_ar: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return (
            self.has_tenant_context
            and self.has_field_context
            and self.has_cross_reference
            and self.has_provenance
            and self.has_authorization
        )


def validate_pipeline(delivery: EnrichedRecommendation) -> PipelineRequirements:
    """يفحص أنّ كل المراحل الإلزامية اكتملت.

    هذا هو "contract gate": لا توصية تخرج بدون اجتياز.
    يحرس ضدّ المراجعة الأهمّ: 'memory layer outside decision core'."""
    req = PipelineRequirements(
        has_tenant_context=False,
        has_field_context=False,
        has_cross_reference=False,
        has_provenance=False,
        has_authorization=False,
    )

    # ١. tenant context
    auth = delivery.auth_decision or {}
    if auth.get("tenant_id"):
        req.has_tenant_context = True
    else:
        req.missing_ar.append("tenant_id في auth_decision")

    # ٢. field context (إن وُجد resource_tenant_id متطابق)
    if auth.get("resource_tenant_id") == auth.get("tenant_id"):
        req.has_field_context = True
    else:
        req.missing_ar.append("resource_tenant_id يطابق tenant_id")

    # ٣. cross_reference موجود (حتى لو 0 matches — العزم على البحث)
    if delivery.cross_reference and "count" in delivery.cross_reference:
        req.has_cross_reference = True
    else:
        req.missing_ar.append("cross_reference (count مفقود)")

    # ٤. provenance كامل
    prov = delivery.provenance or {}
    if prov.get("model_versions") and prov.get("input_snapshot") is not None:
        req.has_provenance = True
    else:
        req.missing_ar.append("provenance ناقص (model_versions أو input_snapshot)")

    # ٥. قرار صلاحية صريح (سواء مسموح أو مرفوض)
    if auth.get("permission") and auth.get("reason_ar") is not None:
        req.has_authorization = True
    else:
        req.missing_ar.append("auth_decision غير مكتمل")

    return req


def enforce_pipeline(delivery: EnrichedRecommendation) -> EnrichedRecommendation:
    """يرفع ContextPipelineError إن نقص شيء من الـcontract.

    استدعِ هذه قبل إرسال التوصية للمزارع/التسجيل في DB.
    Fail closed: شكّ في اكتمال السياق = منع التسليم."""
    req = validate_pipeline(delivery)
    if not req.is_complete:
        # نُحوّل من delivered=True إلى delivered=False مع سبب
        if delivery.delivered:
            delivery.delivered = False
            delivery.reason_ar = (
                f"خطّ السياق غير مكتمل — ناقص: {'، '.join(req.missing_ar)}. "
                "هذا يحرس ضدّ توصية بدون cross_reference أو provenance."
            )
        raise ContextPipelineError(f"Pipeline incomplete: {req.missing_ar}")
    return delivery


def safe_delivery(
    *,
    user: UserSchema,
    tenant_id: str,
    field_id: str,
    farm_id: str,
    crop: str,
    base_recommendation: dict,
    recommendation_history: list,
    current_indicators: dict | None = None,
    growth_stage: str | None = None,
    district_id: str | None = None,
    engines_used: list[str] | None = None,
    is_pesticide: bool = False,
) -> EnrichedRecommendation:
    """نقطة الدخول الوحيدة الموصى بها للطبقات الخارجية.

    تفرض الـcontract: cross_reference + provenance + auth إلزامية.
    تُرجع EnrichedRecommendation مع validate_pipeline مُطبَّق.

    على عكس full_delivery_pipeline (يسمح بـskip محتمل)، هذه:
    - تستدعي pipeline كاملاً
    - تفرض enforce_pipeline (يرفع exception إن نقص شيء)
    - تعكس delivered=False بسبب صريح إن فشل التحقّق

    استخدمها في:
    - API endpoints
    - background workers
    - scheduled jobs
    - أيّ مكان خارج النواة"""
    delivery = full_delivery_pipeline(
        user=user,
        tenant_id=tenant_id,
        field_id=field_id,
        farm_id=farm_id,
        crop=crop,
        base_recommendation=base_recommendation,
        recommendation_history=recommendation_history,
        current_indicators=current_indicators,
        growth_stage=growth_stage,
        engines_used=engines_used,
        is_pesticide=is_pesticide,
        district_id=district_id,
    )

    # حرس الـcontract — لا توصية بدون اكتمال السياق
    try:
        enforce_pipeline(delivery)
    except ContextPipelineError:
        # delivery قد عُدِّل داخل enforce_pipeline بـreason_ar صريح
        pass
    return delivery
