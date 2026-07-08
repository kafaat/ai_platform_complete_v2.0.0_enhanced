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

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status

from api.main import UserSchema, get_current_user

router = APIRouter()
_logger = logging.getLogger("sahool.field_intelligence")

_FIELD_INTELLIGENCE_JOBS: dict[str, dict] = {}
_JOB_TERMINAL_STATES = {"completed", "failed", "cancelled"}


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _job_public(job: dict, *, include_result: bool = True) -> dict:
    payload = {
        "job_id": job["job_id"],
        "status": job["status"],
        "field_id": job["field_id"],
        "progress": job.get("progress", 0),
        "stage": job.get("stage", "queued"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "cancel_requested": bool(job.get("cancel_requested", False)),
    }
    if job.get("error"):
        payload["error"] = job["error"]
    if include_result and job.get("status") == "completed":
        payload["result"] = job.get("result")
    return payload


def _authorize_job(job_id: str, user: UserSchema) -> dict:
    job = _FIELD_INTELLIGENCE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="field_intelligence_job_not_found"
        )
    if str(job.get("tenant_id")) != str(user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="field_intelligence_job_not_found"
        )
    return job


def _patch_job(job_id: str, **updates: object) -> dict | None:
    job = _FIELD_INTELLIGENCE_JOBS.get(job_id)
    if job is None:
        return None
    job.update(updates)
    job["updated_at"] = _utcnow_iso()
    return job


def _raise_if_cancelled(job_id: str) -> None:
    job = _FIELD_INTELLIGENCE_JOBS.get(job_id)
    if job and job.get("cancel_requested"):
        _patch_job(job_id, status="cancelled", progress=100, stage="cancelled")
        raise asyncio.CancelledError


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
# تحليلات عبر الحقول (v149): عُقَد آخر لقطة لكلّ حقل (DISTINCT ON) — التجميع في نواة صرف.
# RLS يفرض عزل المستأجِر على كلا الجدولَين، فلا حاجة لشرط tenant صريح هنا.
_GAP_ANALYTICS_SQL = (
    "WITH latest AS ("
    "  SELECT DISTINCT ON (field_id) id AS snapshot_id "
    "  FROM field_evidence_snapshots ORDER BY field_id, generated_at DESC"
    ") "
    "SELECT n.field_id, n.node_type, n.status "
    "FROM evidence_graph_nodes n JOIN latest l ON n.snapshot_id = l.snapshot_id"
)
# آخر لقطة مُطبَّعة لحقل واحد (v149): عُقَد ثمّ حوافّ عبر معرّف اللقطة نفسه.
_FIELD_LATEST_SNAPSHOT_ID_SQL = (
    "SELECT id FROM field_evidence_snapshots WHERE field_id = $1 ORDER BY generated_at DESC LIMIT 1"
)
_FIELD_NODES_SQL = (
    "SELECT node_id, node_type, source, status, reason FROM evidence_graph_nodes "
    "WHERE snapshot_id = $1 ORDER BY status, node_type"
)
_FIELD_EDGES_SQL = (
    "SELECT edge_id, edge_type, from_node, to_node FROM evidence_graph_edges "
    "WHERE snapshot_id = $1 ORDER BY edge_id"
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
                json.dumps(payload["evidence_graph"], ensure_ascii=False, default=str),
                json.dumps(payload["evidence_sources"], ensure_ascii=False, default=str),
                json.dumps(payload["knowledge_gaps"], ensure_ascii=False, default=str),
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


async def _compute_field_intelligence_response(
    *,
    field_id: str,
    lat: float | None,
    lon: float | None,
    crop: str | None,
    notify: bool,
    authorization: str | None,
    user: UserSchema,
    job_id: str | None = None,
) -> dict:
    """يشغّل التحليل الثقيل ويُرجِع النتيجة النهائية.

    استُخرج من route المتزامن حتى يصبح endpoint العام job-based: لا نُبقي اتصال
    المتصفح مفتوحاً أثناء جلب raster/weather/soil/AI، وبالتالي لا يتحوّل بطء
    التحليل إلى 499 في nginx عند إغلاق العميل.
    """
    from core.agronomic_state_engine import state_to_event_row
    from core.alert_engine import evaluate_alerts, summarize_alerts
    from core.correlation import set_correlation
    from core.field_intelligence_adapters import build_live_adapters
    from core.field_intelligence_coordinator import FieldRequest, run_field_intelligence

    correlation_id = set_correlation()
    if job_id:
        _patch_job(job_id, status="running", progress=5, stage="building_context")
        _raise_if_cancelled(job_id)

    req = FieldRequest(field_id=field_id, lat=lat, lon=lon, crop=crop, tenant_id=user.tenant_id)
    adapters = build_live_adapters(authorization=authorization)

    # run_field_intelligence يستدعي محوّلات HTTP/AI/طقس/تربة وقد يطول؛ نشغّله في
    # thread منفصل كي لا يحبس event loop ولا يعلّق اتصالات أخرى في FastAPI.
    result = await asyncio.to_thread(run_field_intelligence, req, **adapters)
    if job_id:
        _patch_job(job_id, progress=65, stage="building_operational_truth")
        _raise_if_cancelled(job_id)

    state = result.canonical_state
    alerts = evaluate_alerts(state)
    alerts_delivery = None
    if notify and alerts:
        from core.alert_delivery import deliver_alerts

        alerts_delivery = await asyncio.to_thread(
            deliver_alerts,
            alerts,
            context={
                "field_id": state.field_id,
                "tenant_id": state.tenant_id,
                "now": state.generated_at,
            },
        )
    try:
        event_row = state_to_event_row(state, actor_id=user.user_id)
    except ValueError:
        event_row = None

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
        "executable": result.executable,
        "dispatch_block_reason": result.dispatch_block_reason,
        "farm_memory_context": result.farm_memory_context,
        "correlation_id": correlation_id,
        "simulation": result.simulation,
        "alerts": alerts,
        "alerts_summary": summarize_alerts(alerts),
        "alerts_delivery": alerts_delivery,
        "_persistable_event": event_row,
    }

    if job_id:
        _patch_job(job_id, progress=78, stage="fetching_field_card_signals")
        _raise_if_cancelled(job_id)

    from core.field_intelligence_card import assemble_field_intelligence_card

    signals = await _fetch_card_signals(user, field_id, lat=lat, lon=lon)
    response["field_intelligence_card"] = assemble_field_intelligence_card(response, **signals)

    if job_id:
        _patch_job(job_id, progress=88, stage="building_evidence_graph")
        _raise_if_cancelled(job_id)

    from core.evidence_graph import build_evidence_graph

    response["evidence_graph"] = build_evidence_graph(response)

    if job_id:
        _patch_job(job_id, progress=94, stage="persisting_evidence_snapshot")
        _raise_if_cancelled(job_id)

    snapshot_id = await _persist_evidence_snapshot(user, field_id, response)
    if snapshot_id is not None:
        await _persist_evidence_graph_rows(user, field_id, snapshot_id, response)
    return response


async def _run_field_intelligence_job(
    job_id: str,
    *,
    field_id: str,
    lat: float | None,
    lon: float | None,
    crop: str | None,
    notify: bool,
    authorization: str | None,
    user: UserSchema,
) -> None:
    """خلفية job غير متزامنة: فشل/إلغاء العميل لا يفسد حالة التحليل."""
    try:
        _raise_if_cancelled(job_id)
        result = await _compute_field_intelligence_response(
            field_id=field_id,
            lat=lat,
            lon=lon,
            crop=crop,
            notify=notify,
            authorization=authorization,
            user=user,
            job_id=job_id,
        )
        if _FIELD_INTELLIGENCE_JOBS.get(job_id, {}).get("cancel_requested"):
            _patch_job(job_id, status="cancelled", progress=100, stage="cancelled")
            return
        _patch_job(job_id, status="completed", progress=100, stage="completed", result=result)
    except asyncio.CancelledError:
        _patch_job(job_id, status="cancelled", progress=100, stage="cancelled")
    except Exception as exc:  # noqa: BLE001 — job يفشل بصراحة، ولا يُترك عالقاً running.
        _logger.exception("field intelligence job failed job_id=%s field_id=%s", job_id, field_id)
        _patch_job(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            error={"code": "field_intelligence_analysis_failed", "message": str(exc)},
        )


@router.post("/api/v1/field-intelligence/analyze", status_code=status.HTTP_202_ACCEPTED)
async def field_intelligence_analyze(
    background_tasks: BackgroundTasks,
    field_id: str,
    lat: float | None = None,
    lon: float | None = None,
    crop: str | None = None,
    notify: bool = False,
    authorization: str = Header(None),
    user: UserSchema = Depends(get_current_user),
):
    """يبدأ تحليل ذكاء الحقل كـ async job ويُرجِع job_id بسرعة.

    P0 runtime/UX fix: لا يُسمح لهذا المسار الثقيل أن يبقى متزامناً؛ 499 في nginx
    غالباً يعني أن العميل أغلق الاتصال قبل انتهاء التحليل. العقد الجديد:
    POST ⇒ queued job خلال <1s، ثم GET /jobs/{job_id} أو WebSocket/polling للنتيجة.
    """
    job_id = f"fia_{uuid.uuid4().hex[:16]}"
    now = _utcnow_iso()
    _FIELD_INTELLIGENCE_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "field_id": field_id,
        "tenant_id": str(user.tenant_id),
        "user_id": str(user.user_id),
        "progress": 0,
        "stage": "queued",
        "created_at": now,
        "updated_at": now,
        "cancel_requested": False,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(
        _run_field_intelligence_job,
        job_id,
        field_id=field_id,
        lat=lat,
        lon=lon,
        crop=crop,
        notify=notify,
        authorization=authorization,
        user=user,
    )
    return _job_public(_FIELD_INTELLIGENCE_JOBS[job_id], include_result=False)


@router.get("/api/v1/field-intelligence/analyze/jobs/{job_id}")
async def field_intelligence_analyze_job_status(
    job_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """حالة job التحليل: polling صريح بدل انتظار اتصال POST طويل."""
    job = _authorize_job(job_id, user)
    return _job_public(job)


@router.post("/api/v1/field-intelligence/analyze/jobs/{job_id}/cancel")
async def field_intelligence_analyze_job_cancel(
    job_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """إلغاء منطقي آمن: لا يفسد الحالة حتى لو كان العمل الداخلي قد بدأ فعلاً."""
    job = _authorize_job(job_id, user)
    if job.get("status") in _JOB_TERMINAL_STATES:
        return _job_public(job, include_result=False)
    _patch_job(job_id, cancel_requested=True, status="cancelled", progress=100, stage="cancelled")
    return _job_public(job, include_result=False)


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


@router.get("/api/v1/evidence-graph/analytics")
async def evidence_graph_analytics(
    user: UserSchema = Depends(get_current_user),
):
    """تحليلات رسم الأدلّة عبر حقول المستأجِر (من الجداول المُطبَّعة v149).

    يجيب «ما المعلومة الأكثر غياباً عبر حقولي؟» — تجميع على **آخر لقطة لكلّ حقل**:
    أكثر الفجوات تكراراً + توزيع الحالات + عدد الحقول المُحلَّلة. معزول بالمستأجِر (RLS).
    صدق: القاعدة معطّلة أو لا لقطات مُطبَّعة ⇒ أصفار صريحة (لا اختلاق)؛ الجداول مُشتقّة
    (الكاتب fail-soft) فقد تتأخّر عن JSONB — نُعلن ذلك في ``derived``.
    """
    from core.evidence_graph_analytics import shape_gap_analytics

    from api.main import _DB_POOL, tenant_connection

    if _DB_POOL is None:
        return {
            "available": False,
            "reason": "db_disabled",
            "fields_analyzed": 0,
            "top_gaps": [],
            "status_distribution": [],
        }
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(_GAP_ANALYTICS_SQL)
    analytics = shape_gap_analytics([dict(r) for r in rows])
    return {
        "available": analytics["fields_analyzed"] > 0,
        "derived": "evidence_graph_nodes (v149) — مُشتقّ من لقطة JSONB مصدر الحقيقة",
        **analytics,
    }


@router.get("/api/v1/fields/{field_id}/evidence-graph/nodes")
async def field_evidence_graph_nodes(
    field_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """عُقَد/حوافّ **آخر لقطة مُطبَّعة** لحقل (v149) — بنية جاهزة للعرض/التحليل.

    تكمّل ``/latest`` (JSONB): تُرجِع الصفوف المُسطَّحة (present + gap) بحالتها وسببها من
    الجداول المُشتقّة. معزول بالمستأجِر (RLS). صدق: لا قاعدة/لقطة ⇒ ``available: false``.
    """
    from core.evidence_graph_analytics import shape_field_graph

    from api.main import _DB_POOL, tenant_connection

    if _DB_POOL is None:
        return {"field_id": field_id, "available": False, "reason": "db_disabled"}
    async with tenant_connection(user) as conn:
        snap = await conn.fetchval(_FIELD_LATEST_SNAPSHOT_ID_SQL, field_id)
        if snap is None:
            return {"field_id": field_id, "available": False, "reason": "no_snapshot"}
        node_rows = await conn.fetch(_FIELD_NODES_SQL, snap)
        edge_rows = await conn.fetch(_FIELD_EDGES_SQL, snap)
    graph = shape_field_graph([dict(r) for r in node_rows], [dict(r) for r in edge_rows])
    return {"field_id": field_id, **graph}


def _json_col(value):
    """عمود JSONB قد يعود نصّاً (asyncpg بلا codec) أو بنية — نطبّع إلى بنية."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value
