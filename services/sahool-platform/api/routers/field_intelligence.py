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

import json
import logging

from fastapi import APIRouter, Depends, Header, Query

from api.main import UserSchema, get_current_user

router = APIRouter()
_logger = logging.getLogger("sahool.field_intelligence")

# استمرار لقطة رسم الأدلّة (v148). tenant_id من السياق الموثوق (لا الجسم)؛ RLS يفرض العزل.
_SNAPSHOT_INSERT_SQL = (
    "INSERT INTO field_evidence_snapshots "
    "(tenant_id, field_id, analysis_id, recommendation_hash, confidence_score, "
    "evidence_graph, evidence_sources, knowledge_gaps) "
    "VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb) RETURNING id"
)
# تطبيع الرسم (v149) — عُقَد/حوافّ مُشتقّة من اللقطة (idempotent عبر UNIQUE per snapshot).
_NODE_INSERT_SQL = (
    "INSERT INTO evidence_graph_nodes "
    "(tenant_id, field_id, snapshot_id, node_id, node_type, source, status, reason) "
    "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8) "
    "ON CONFLICT (snapshot_id, node_id) DO NOTHING"
)
_EDGE_INSERT_SQL = (
    "INSERT INTO evidence_graph_edges "
    "(tenant_id, field_id, snapshot_id, edge_id, edge_type, from_node, to_node) "
    "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7) "
    "ON CONFLICT (snapshot_id, edge_id) DO NOTHING"
)
_SNAPSHOT_LATEST_SQL = (
    "SELECT generated_at, recommendation_hash, confidence_score, evidence_graph, "
    "evidence_sources, knowledge_gaps FROM field_evidence_snapshots "
    "WHERE field_id = $1 ORDER BY generated_at DESC LIMIT 1"
)
_SNAPSHOT_TIMELINE_SQL = (
    "SELECT generated_at, recommendation_hash, confidence_score, "
    "(evidence_graph->'summary'->>'evidence_count')::int AS evidence_count, "
    "(evidence_graph->'summary'->>'gap_count')::int AS gap_count "
    "FROM field_evidence_snapshots WHERE field_id = $1 "
    "ORDER BY generated_at DESC LIMIT $2"
)


async def _persist_evidence_snapshot(user: UserSchema, field_id: str, response: dict) -> int | None:
    """يحفظ لقطة رسم الأدلّة ويُعيد ``snapshot_id`` (أو None) — **fail-soft** لا يكسر analyze.

    لا لقطة بلا رسم أدلّة فعليّ (``build_snapshot_payload`` يُرجِع None). القاعدة معطّلة ⇒
    تخطٍّ صامت. tenant_id من التوكن الموثوق؛ الرسم منقّى من الأسرار قبل التخزين.
    """
    from core.evidence_snapshot import build_snapshot_payload

    from api.main import _DB_POOL, tenant_connection

    if _DB_POOL is None:
        return None
    payload = build_snapshot_payload(response)
    if payload is None:
        return None
    try:
        async with tenant_connection(user) as conn:
            return await conn.fetchval(
                _SNAPSHOT_INSERT_SQL,
                str(user.tenant_id),
                field_id,
                payload["analysis_id"],
                payload["recommendation_hash"],
                payload["confidence_score"],
                json.dumps(payload["evidence_graph"], ensure_ascii=False),
                json.dumps(payload["evidence_sources"], ensure_ascii=False),
                json.dumps(payload["knowledge_gaps"], ensure_ascii=False),
            )
    except Exception as exc:  # noqa: BLE001 — fail-soft: الاستمرار لا يكسر التحليل.
        _logger.warning("evidence snapshot persist skipped for %s: %s", field_id, exc)
        return None


async def _persist_evidence_graph_rows(
    user: UserSchema, field_id: str, snapshot_id: int, response: dict
) -> None:
    """يشتقّ عُقَد/حوافّ اللقطة إلى الجدولَين المُطبَّعَين (v149) — **fail-soft، مُشتقّ فقط**.

    اللقطة JSONB (v148) هي مصدر الحقيقة؛ فشل هذا الاشتقاق **لا يكسر** analyze ولا اللقطة
    (معاملة منفصلة). ``ON CONFLICT DO NOTHING`` يمنع التكرار لنفس اللقطة (idempotent).
    """
    from core.evidence_graph_normalize import normalize_graph_to_rows

    from api.main import tenant_connection

    rows = normalize_graph_to_rows(response.get("evidence_graph"))
    if not rows["nodes"] and not rows["edges"]:
        return
    tid = str(user.tenant_id)
    try:
        async with tenant_connection(user) as conn:
            for n in rows["nodes"]:
                await conn.execute(
                    _NODE_INSERT_SQL,
                    tid,
                    field_id,
                    snapshot_id,
                    n["node_id"],
                    n["node_type"],
                    n["source"],
                    n["status"],
                    n["reason"],
                )
            for e in rows["edges"]:
                await conn.execute(
                    _EDGE_INSERT_SQL,
                    tid,
                    field_id,
                    snapshot_id,
                    e["edge_id"],
                    e["edge_type"],
                    e["from_node"],
                    e["to_node"],
                )
    except Exception as exc:  # noqa: BLE001 — fail-soft: الاشتقاق لا يكسر اللقطة/التحليل.
        _logger.warning("evidence graph normalize skipped for %s: %s", field_id, exc)


# NDVI history (zonal_stats) + أحدث مشهد (raster_assets) لتغذية أقسام البطاقة — RLS.
_CARD_NDVI_SQL = (
    "SELECT mean FROM zonal_stats WHERE field_id = $1 AND index_name = 'ndvi' "
    "ORDER BY stat_date DESC LIMIT 24"
)
_CARD_SCENE_SQL = (
    "SELECT scene_id, acquisition_date, cloud_pct FROM raster_assets "
    "WHERE field_id = $1 ORDER BY acquisition_date DESC NULLS LAST LIMIT 1"
)


async def _fetch_card_signals(
    user: UserSchema, field_id: str, *, lat: float | None = None, lon: float | None = None
) -> dict:
    """يجلب إشارات البطاقة (ndvi_history/latest_scene) مُقيَّدة بالمستأجِر — سقوط آمن.

    أيّ تعذّر (قاعدة معطّلة/خطأ استعلام) ⇒ إشارات فارغة فتبقى أقسام البطاقة ``missing``
    صراحةً (سلوك ما قبل التغذية دون تغيير) — لا اختلاق ولا انحدار.
    """
    from core.field_intelligence_card import (
        card_signals_from_db_rows,
        provider_status_signal,
        soil_baseline_signal,
        terrain_signal,
        weather_window_signal,
    )

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

    # terrain من raster-service (/v1/fields/{id}/terrain) — يعمل من field_id (raster يشتقّ
    # المضلّع). tenant-scoped عبر X-Tenant-Id الموثوق (لا lat/lon). آمن الفشل (DEM/هندسة
    # متعذّرة ⇒ القسم يبقى missing بصدق).
    try:
        from types import SimpleNamespace

        from core.field_intelligence_adapters import fetch_terrain_summary

        ts = terrain_signal(
            fetch_terrain_summary(SimpleNamespace(field_id=field_id), tenant_id=user.tenant_id)
        )
        if ts:
            signals["terrain"] = ts
    except Exception as exc:  # noqa: BLE001 — تغذية اختياريّة.
        _logger.warning("terrain fetch failed for %s: %s", field_id, exc)

    # soil_baseline من soil-service (/soil/soilgrids) — يتطلّب lat/lon؛ آمن الفشل
    # (soil-service/تغطية/توكن متعذّر ⇒ القسم يبقى missing بصدق). خطّ أساس عالميّ لا مختبر.
    if lat is not None and lon is not None:
        try:
            from types import SimpleNamespace

            from core.field_intelligence_adapters import fetch_soil_baseline

            sb = soil_baseline_signal(
                fetch_soil_baseline(SimpleNamespace(field_id=field_id, lat=lat, lon=lon))
            )
            if sb:
                signals["soil_baseline"] = sb
        except Exception as exc:  # noqa: BLE001 — تغذية اختياريّة.
            _logger.warning("soil baseline fetch failed for %s: %s", field_id, exc)

        # weather_window من توقّع Open-Meteo (keyless، نشط) — دوافع اليوم الموضوعيّة.
        # آمن الفشل (منع خروج/شبكة ⇒ القسم يبقى missing بصدق). لا يُعيد حساب الرشّ/الريّ.
        try:
            from types import SimpleNamespace

            from core.field_intelligence_adapters import weather_forecast_adapter

            ww = weather_window_signal(
                weather_forecast_adapter(SimpleNamespace(field_id=field_id, lat=lat, lon=lon))
            )
            if ww:
                signals["weather_window"] = ww
        except Exception as exc:  # noqa: BLE001 — تغذية اختياريّة.
            _logger.warning("weather window fetch failed for %s: %s", field_id, exc)

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

    signals = await _fetch_card_signals(user, field_id, lat=lat, lon=lon)
    response["field_intelligence_card"] = assemble_field_intelligence_card(response, **signals)
    # رسم الأدلّة (Evidence Graph): يُهيكل أدلّة البطاقة كعُقَد/حوافّ مع مصادرها وفجوات
    # المعرفة — لتفسير التوصية وإثبات مصدر كلّ معلومة. منطق صرف من المُجمَّع (بلا جلب).
    from core.evidence_graph import build_evidence_graph

    response["evidence_graph"] = build_evidence_graph(response)
    # استمرار اللقطة (v148) — fail-soft: فشل الكتابة لا يكسر التحليل (persistence غير حاجبة).
    snapshot_id = await _persist_evidence_snapshot(user, field_id, response)
    # تطبيع المرحلة 2 (v149) — عُقَد/حوافّ مُشتقّة (fail-soft، معاملة منفصلة، اللقطة مصدر الحقيقة).
    if snapshot_id is not None:
        await _persist_evidence_graph_rows(user, field_id, snapshot_id, response)
    return response


@router.get("/api/v1/fields/{field_id}/evidence-graph/latest")
async def field_evidence_graph_latest(
    field_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """أحدث لقطة رسم أدلّة محفوظة للحقل (معزولة بالمستأجِر عبر RLS).

    صدق: لا لقطة بعد ⇒ ``{available: false}`` (لا اختلاق). القاعدة معطّلة ⇒ نفسه.
    """
    from api.main import _DB_POOL, tenant_connection

    if _DB_POOL is None:
        return {"field_id": field_id, "available": False, "reason": "db_disabled"}
    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(_SNAPSHOT_LATEST_SQL, field_id)
    if row is None:
        return {"field_id": field_id, "available": False, "reason": "no_snapshot"}
    r = dict(row)
    return {
        "field_id": field_id,
        "available": True,
        "generated_at": r["generated_at"],
        "recommendation_hash": r["recommendation_hash"],
        "confidence_score": (
            float(r["confidence_score"]) if r["confidence_score"] is not None else None
        ),
        "evidence_graph": _json_col(r["evidence_graph"]),
        "evidence_sources": _json_col(r["evidence_sources"]),
        "knowledge_gaps": _json_col(r["knowledge_gaps"]),
    }


@router.get("/api/v1/fields/{field_id}/evidence-graph/timeline")
async def field_evidence_graph_timeline(
    field_id: str,
    limit: int = Query(20, ge=1, le=100),
    user: UserSchema = Depends(get_current_user),
):
    """خطّ زمنيّ مُوجَز للقطات الأدلّة (تنازليّاً): بصمة القرار + الثقة + عدّ الأدلّة/الفجوات.

    يخدم audit «كيف تطوّرت الأدلّة/التوصية عبر الزمن» دون نقل الرسم كاملاً كلّ مرّة.
    معزول بالمستأجِر (RLS). لا لقطات ⇒ قائمة فارغة صريحة.
    """
    from api.main import _DB_POOL, tenant_connection

    if _DB_POOL is None:
        return {"field_id": field_id, "snapshots": [], "reason": "db_disabled"}
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(_SNAPSHOT_TIMELINE_SQL, field_id, limit)
    return {
        "field_id": field_id,
        "snapshots": [
            {
                "generated_at": r["generated_at"],
                "recommendation_hash": r["recommendation_hash"],
                "confidence_score": (
                    float(r["confidence_score"]) if r["confidence_score"] is not None else None
                ),
                "evidence_count": r["evidence_count"],
                "gap_count": r["gap_count"],
            }
            for r in rows
        ],
    }


def _json_col(value):
    """عمود JSONB قد يعود نصّاً (asyncpg بلا codec) أو بنية — نطبّع إلى بنية."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value
