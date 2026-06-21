"""api/routers/field_intelligence.py — التشغيل الحيّ للمايسترو (Field Intelligence)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. الاستيرادات
الكسولة داخل الدالّة تبقى كما هي. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد
هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from api.main import UserSchema, get_current_user

router = APIRouter()


@router.post("/api/v1/field-intelligence/analyze")
def field_intelligence_analyze(
    field_id: str,
    lat: float | None = None,
    lon: float | None = None,
    crop: str | None = None,
    notify: bool = False,
    authorization: str = Header(None),
    user: UserSchema = Depends(get_current_user),
):
    """يُشغّل المسار الكامل للمايسترو لحقل ويُرجِع الحالة الموحّدة + القرار.

    سيادة البيانات: tenant_id من التوكن (موثوق) لا من الجسم (لا spoofing).
    المصادر: محوّلات HTTP حيّة (weather/soil/raster). المتعذّر يُعلَن بصدق.
    الحالة الناتجة جاهزة للحفظ في events (state_to_event_row) كذاكرة موسميّة.
    """
    from core.agronomic_state_engine import state_to_event_row
    from core.alert_engine import evaluate_alerts, summarize_alerts
    from core.correlation import set_correlation
    from core.field_intelligence_adapters import build_live_adapters
    from core.field_intelligence_coordinator import FieldRequest, run_field_intelligence

    # ربط موحّد: correlation_id يمرّ بكلّ ما ينتج عن هذا الطلب (workflow/
    # events/alerts) — لتتبّع "ماذا أنتج ماذا" عبر الخدمات (نمط OpenTelemetry).
    correlation_id = set_correlation()

    # tenant_id من التوكن الموثوق (لا من جسم الطلب — حماية multi-tenant)
    req = FieldRequest(field_id=field_id, lat=lat, lon=lon, crop=crop, tenant_id=user.tenant_id)
    # تمرير رأس التفويض للمحوّلات المحميّة (memory/simulate تنادي نقاط JWT داخليّة)
    adapters = build_live_adapters(authorization=authorization)
    result = run_field_intelligence(req, **adapters)

    state = result.canonical_state
    # التنبيهات الاستباقيّة: من الحالة الموحّدة (change_detection/FVC يُمرَّران عند
    # توفّرهما من العامل — هنا الحالة فقط، فالمحرّك سلبيّ→استباقيّ على ما هو متاح).
    alerts = evaluate_alerts(state)
    # التوصيل اختياريّ (notify=true): warning فأعلى عبر القنوات المُهيّأة. صدق:
    # الإرسال الخارجي يحدث فقط عند تهيئة القناة (لا ادّعاء إرسال).
    alerts_delivery = None
    if notify and alerts:
        from core.alert_delivery import deliver_alerts

        alerts_delivery = deliver_alerts(
            alerts,
            context={
                "field_id": state.field_id,
                "tenant_id": state.tenant_id,
                "now": state.generated_at,
            },
        )
    # حدث الحفظ جاهز (الكتابة الفعليّة في events عبر event_bus على بيئة التشغيل)
    try:
        event_row = state_to_event_row(state, actor_id=user.user_id)
    except ValueError:
        event_row = None  # بلا tenant — لا يُحفَظ (لن يحدث: tenant من التوكن)

    return {
        "field_id": state.field_id,
        "tenant_id": state.tenant_id,
        "generated_at": state.generated_at,
        "operational_truths": state.operational_truths,
        "confidence": state.confidence,
        "confidence_reason": state.confidence_reason,
        "provenance": state.provenance,
        "contradictions": state.contradictions,
        "missing_signals": state.missing_signals,
        "policy_decision": result.policy_decision,
        "governance": result.governance,
        # بوّابة التنفيذ المحكومة: القرار غير قابل للتوزيع ما لم تُقَرّ الحَوكمة.
        # في المسار الحيّ لا يُمرَّر guardrails_fn ⇒ executable=False (استشاريّ فقط)،
        # وسبب المنع صريح (governance_not_evaluated) — لا تُختلق موافقة.
        "executable": result.executable,
        "dispatch_block_reason": result.dispatch_block_reason,
        "farm_memory_context": result.farm_memory_context,  # السياق التاريخي
        "correlation_id": correlation_id,  # خيط التتبّع الموحّد (OpenTelemetry-style)
        "simulation": result.simulation,  # أثر what-if المتوقّع
        "alerts": alerts,  # تنبيهات استباقيّة مُصنّفة (محرّك التنبيهات)
        "alerts_summary": summarize_alerts(alerts),
        "alerts_delivery": alerts_delivery,  # نتيجة التوصيل (إن notify=true)
        "_persistable_event": event_row,  # جاهز للإدراج في events table
    }
