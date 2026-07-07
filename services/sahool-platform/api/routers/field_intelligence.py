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

import logging

from fastapi import APIRouter, Depends, Header

from api.main import UserSchema, get_current_user

router = APIRouter()
_logger = logging.getLogger("sahool.field_intelligence")

# NDVI history (zonal_stats) + أحدث مشهد (raster_assets) لتغذية أقسام البطاقة — RLS.
_CARD_NDVI_SQL = (
    "SELECT mean FROM zonal_stats WHERE field_id = $1 AND index_name = 'ndvi' "
    "ORDER BY stat_date DESC LIMIT 24"
)
_CARD_SCENE_SQL = (
    "SELECT scene_id, acquisition_date, cloud_pct FROM raster_assets "
    "WHERE field_id = $1 ORDER BY acquisition_date DESC NULLS LAST LIMIT 1"
)


async def _fetch_card_signals(user: UserSchema, field_id: str) -> dict:
    """يجلب إشارات البطاقة (ndvi_history/latest_scene) مُقيَّدة بالمستأجِر — سقوط آمن.

    أيّ تعذّر (قاعدة معطّلة/خطأ استعلام) ⇒ إشارات فارغة فتبقى أقسام البطاقة ``missing``
    صراحةً (سلوك ما قبل التغذية دون تغيير) — لا اختلاق ولا انحدار.
    """
    from core.field_intelligence_card import card_signals_from_db_rows, provider_status_signal

    from api.main import _DB_POOL, tenant_connection

    signals: dict = {}
    # provider_status من raster-service (/v1/providers/status) — آمن الفشل (raster متعذّر
    # ⇒ القسم يبقى missing بصدق). خارج معاملة القاعدة كي لا يعطّله تعذّرها.
    try:
        from core.field_intelligence_adapters import fetch_provider_status

        ps = provider_status_signal(fetch_provider_status())
        if ps:
            signals["provider_status"] = ps
    except Exception as exc:  # noqa: BLE001 — تغذية اختياريّة.
        _logger.warning("provider status fetch failed: %s", exc)

    if _DB_POOL is None:
        return signals
    try:
        async with tenant_connection(user) as conn:
            ndvi_rows = await conn.fetch(_CARD_NDVI_SQL, field_id)
            scene = await conn.fetchrow(_CARD_SCENE_SQL, field_id)
        signals.update(
            card_signals_from_db_rows([dict(r) for r in ndvi_rows], dict(scene) if scene else None)
        )
    except Exception as exc:  # noqa: BLE001 — تغذية اختياريّة؛ فشلها لا يكسر التحليل.
        _logger.warning("card signal fetch failed for %s: %s", field_id, exc)
    return signals


@router.post("/api/v1/field-intelligence/analyze")
async def field_intelligence_analyze(
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

    response = {
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
    # V65 — بطاقة ذكاء الحقل الموحّدة: تجميع صادق للأوليّات القائمة في بطاقة قرار
    # واحدة (أحدث مشهد/حالة مزوّد/NDVI-تاريخيّ/عجز مائيّ/مناطق ضعيفة/تنبيهات/أدلّة/ثقة).
    # P1 — تُغذّى أقسام المشهد/NDVI-التاريخيّ من قاعدة المنصّة (zonal_stats/raster_assets)
    # مُقيَّدةً بالمستأجِر؛ التعذّر ⇒ الأقسام تبقى missing صراحةً (لا اختلاق ولا انحدار).
    from core.field_intelligence_card import assemble_field_intelligence_card

    signals = await _fetch_card_signals(user, field_id)
    response["field_intelligence_card"] = assemble_field_intelligence_card(response, **signals)
    return response
