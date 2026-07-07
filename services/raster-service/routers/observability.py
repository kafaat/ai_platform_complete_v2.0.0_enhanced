"""routers/observability.py — فحوص الصحّة والمقاييس والمعلومات (Observability)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة تُستورد من الوحدات المفككة مباشرة؛ يمنع الحارس رجوع الراوترات إلى ``main``.
"""

from __future__ import annotations

import logging
import os

import httpx
import object_store
import stac_search as stac_search_helpers
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from layer_lookup import grid_from_cog, resolve_field_layer, rvi_from_sar_cog
from raster_runtime_state import FIELD_LAYERS, JOBS, LAYERS
from raster_security_context import REQ_TENANT, require_service_token
from raster_settings import AGENT_TOKEN, EARTH_SEARCH_URL, UPLOAD_DIR
from tile_observability import TILE_OBS, TILE_OBS_BY_INDEX

logger = logging.getLogger("raster-service")

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "raster-service"}


@router.get("/metrics")
async def metrics():
    """مقاييس خطّ المعالجة الجغرافي (Prometheus format) — سدّ فجوة
    observability. يعرّض حالة المهامّ ليلتقطها Prometheus (لا black-box).

    تنسيق exposition نصّي بسيط — لا تبعيّة ثقيلة. يربطه prometheus.yml.
    """
    from collections import Counter

    by_status = Counter(j.get("status") for j in JOBS.values())

    # حوّل enum/قيمة لنصّ
    def _s(k):
        return getattr(k, "value", str(k))

    lines = [
        "# HELP sahool_raster_jobs_total إجمالي مهامّ المعالجة حسب الحالة",
        "# TYPE sahool_raster_jobs_total gauge",
    ]
    for status, count in by_status.items():
        lines.append(f'sahool_raster_jobs_total{{status="{_s(status)}"}} {count}')
    lines += [
        "# HELP sahool_raster_layers_total الطبقات المُنتَجة المتاحة",
        "# TYPE sahool_raster_layers_total gauge",
        f"sahool_raster_layers_total {len(LAYERS)}",
        "# HELP sahool_raster_jobs_active المهامّ قيد المعالجة الآن",
        "# TYPE sahool_raster_jobs_active gauge",
        f"sahool_raster_jobs_active "
        f"{sum(1 for j in JOBS.values() if _s(j.get('status')) == 'processing')}",
    ]
    # صحّة عميل STAC (مرونة قلب النظام)
    h = stac_search_helpers.stac_health()
    lines += [
        "# HELP sahool_stac_requests_total إجمالي طلبات STAC",
        "# TYPE sahool_stac_requests_total counter",
        f"sahool_stac_requests_total {h['requests']}",
        "# HELP sahool_stac_cache_hit_rate نسبة إصابة cache (0-1)",
        "# TYPE sahool_stac_cache_hit_rate gauge",
        f"sahool_stac_cache_hit_rate {h['cache_hit_rate']}",
        "# HELP sahool_stac_failures_total فشل STAC التامّ (لا cache)",
        "# TYPE sahool_stac_failures_total counter",
        f"sahool_stac_failures_total {h['failures']}",
        "# HELP sahool_stac_stale_served_total نتائج cache منتهية قُدّمت (انقطاع)",
        "# TYPE sahool_stac_stale_served_total counter",
        f"sahool_stac_stale_served_total {h['stale_served']}",
        "# HELP sahool_stac_fallback_served_total نتائج من المصدر الاحتياطي (PC)",
        "# TYPE sahool_stac_fallback_served_total counter",
        f"sahool_stac_fallback_served_total {h.get('fallback_served', 0)}",
    ]
    lines += [
        "# HELP sahool_raster_tilejson_requests_total TileJSON requests reaching raster-service",
        "# TYPE sahool_raster_tilejson_requests_total counter",
        f"sahool_raster_tilejson_requests_total {TILE_OBS['tilejson_requests_total']}",
        "# HELP sahool_raster_tilejson_unavailable_total TileJSON responses with available=false",
        "# TYPE sahool_raster_tilejson_unavailable_total counter",
        f"sahool_raster_tilejson_unavailable_total {TILE_OBS['tilejson_unavailable_total']}",
        "# HELP sahool_raster_tile_requests_total Field tile image requests",
        "# TYPE sahool_raster_tile_requests_total counter",
        f"sahool_raster_tile_requests_total {TILE_OBS['tile_requests_total']}",
        "# HELP sahool_raster_tile_cache_hits_total Persistent tile cache hits",
        "# TYPE sahool_raster_tile_cache_hits_total counter",
        f"sahool_raster_tile_cache_hits_total {TILE_OBS['tile_cache_hits_total']}",
        "# HELP sahool_raster_tile_cache_misses_total Persistent tile cache misses",
        "# TYPE sahool_raster_tile_cache_misses_total counter",
        f"sahool_raster_tile_cache_misses_total {TILE_OBS['tile_cache_misses_total']}",
        "# HELP sahool_raster_tile_transparent_total Transparent tiles returned because no raster data was available",
        "# TYPE sahool_raster_tile_transparent_total counter",
        f"sahool_raster_tile_transparent_total {TILE_OBS['tile_transparent_total']}",
        "# HELP sahool_raster_tile_render_errors_total Tile rendering errors hidden behind transparent fallback",
        "# TYPE sahool_raster_tile_render_errors_total counter",
        f"sahool_raster_tile_render_errors_total {TILE_OBS['tile_render_errors_total']}",
    ]
    for idx, counters in sorted(TILE_OBS_BY_INDEX.items()):
        safe_idx = idx.replace('"', "_")
        for key, value in sorted(counters.items()):
            metric = "sahool_raster_" + key
            lines.append(f'{metric}{{index="{safe_idx}"}} {int(value)}')

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/v1/tiles/observability")
async def tile_observability():
    """تشخيص سريع للبلاطات للواجهة/الدعم: يوضح إن كانت المشكلة عدم بيانات،
    cache، أو أخطاء تصيير، دون كشف مسارات COG الداخلية."""
    return {
        "status": "ok",
        "counters": dict(TILE_OBS),
        "by_index": {k: dict(v) for k, v in TILE_OBS_BY_INDEX.items()},
        "cache_enabled": os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true",
        "message": "راقب tilejson_unavailable_total و tile_transparent_total عند عدم ظهور طبقة المؤشر",
    }


def _terrain_soil_readiness() -> dict:
    """حالة تفصيليّة لطبقات التضاريس/التربة (غير حاجبة لـready) — شفافيّة تشغيليّة.

    DEM/SoilGrids اختياريّان (fail-closed بلا تلفيق)، فلا يجعلان الخدمة degraded؛ لكن
    نكشف قابليّتهما للخدمة كي لا تبدو الخدمة «جاهزة» بينما الطبقات معطّلة صامتاً."""
    dem = os.getenv("FIELD_DEM_PATH") or None
    dem_readable = bool(dem and os.path.isfile(dem))
    try:
        import soil_render as _soil

        readable_layers = _soil.readable_layer_count()
        soil_declared = _soil.is_source_configured()
    except Exception:  # noqa: BLE001
        readable_layers, soil_declared = 0, False
    return {
        "terrain": {
            "enabled": dem_readable,
            "dem_path_set": bool(dem),
            "dem_readable": dem_readable,
        },
        "soilgrids": {
            "enabled": readable_layers > 0,
            "source_declared": soil_declared,
            "readable_layers": readable_layers,
        },
    }


@router.get("/readyz")
async def readyz():
    """يتحقّق من الوصول لـEarth Search + يكشف حالة طبقات التضاريس/التربة (غير حاجبة)."""
    detail = _terrain_soil_readiness()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{EARTH_SEARCH_URL}/")
            ok = r.status_code < 500
        body = {
            "status": "ready" if ok else "degraded",
            "earth_search": "reachable" if ok else "unreachable",
            **detail,
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "earth_search": "unreachable", **detail},
        )


@router.get("/v1/tile-cache/stats")
async def tile_cache_stats(x_agent_token: str = Header(None)):
    require_service_token(x_agent_token, AGENT_TOKEN)
    root = os.path.join(UPLOAD_DIR, "tile_cache")
    count = 0
    size = 0
    for base, _dirs, files in os.walk(root) if os.path.exists(root) else []:
        for fn in files:
            if fn.endswith(".png"):
                count += 1
                try:
                    size += os.path.getsize(os.path.join(base, fn))
                except OSError:
                    pass
    return {
        "enabled": os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true",
        "tiles": count,
        "bytes": size,
    }


@router.get("/info/{layer_id}")
async def raster_info(layer_id: str, x_agent_token: str = Header(None)):
    """معلومات طبقة راستر معالَجة."""
    require_service_token(x_agent_token, AGENT_TOKEN)
    layer = LAYERS.get(layer_id)
    if not layer:
        raise HTTPException(404, "طبقة غير موجودة")
    return layer


@router.get("/v1/providers/status")
async def providers_status():
    """حالة مزوّدي الصور (سِجِلّ صادق) — يكشف ``PROVIDER_REGISTRY`` كعقد HTTP.

    يمكّن المنصّة/الواجهة من ملء ``provider_status`` في بطاقة ذكاء الحقل من مصدر واحد
    صادق. صدق: ``active`` يعكس الوصل الفعليّ لا الطموح (wapor/worldcereal/nasa_hls/
    planetary_computer مُخطَّطة active=False)؛ المصادر البحثيّة (Gitee) منفصلة تماماً
    (``provides_imagery=False``). بيانات وصفيّة غير حسّاسة (لا معلومات مستأجِر).
    """
    import raster_scene_model as _sm

    return {
        "default_historical_provider": stac_search_helpers.HISTORICAL_SEARCH_PROVIDER,
        "active": _sm.active_providers(),
        "planned": _sm.planned_providers(),
        "providers": _sm.PROVIDER_REGISTRY,
        "research_sources": _sm.RESEARCH_REGISTRY,
        "external_sources": _sm.EXTERNAL_SOURCE_REGISTRY,
        "ai_models": _sm.AI_MODEL_REGISTRY,
        # تشخيص جاهزيّة OlmoEarth على العتاد (صادق): ما ينقص لتفعيله (أوزان/GPU/تحقّق محلّيّ).
        # يبقى ready=False حتّى بعد الأوزان+GPU (تفعيل بشريّ بعد benchmark يمنيّ).
        "olmoearth_runtime": _sm.olmoearth_runtime_status(),
    }


@router.get("/indices")
async def field_indices(
    field_id: str,
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    date: str = Query("latest"),
    indices: str = Query("ndvi,ndre,ndsi,ndwi,bsi,si,rvi"),
    cloud_cover: float | None = Query(None),
    x_agent_token: str = Header(None),
):
    """متوسّط كلّ مؤشّر للحقل (للدمج الحيّ في field-intelligence) + غطاء السحب.

    يسدّ ثغرة wiring حقيقيّة: sensing_adapter كان ينادي /indices غير الموجودة ⇒
    المسار الطيفي الحيّ بلا تغذية. يعيد استخدام مسار indicator-grid
    (_resolve_field_layer + _grid_from_cog): لكلّ مؤشّر يقرأ COG المقصوص ويُرجِع
    المتوسّط (real_data=True). صدق: لا COG ⇒ قيم null + real_data=False + note (لا
    اختراع). cloud_cover يُمرَّر إن توفّر (من eo:cloud_cover عبر المستدعي) ليُفعّل
    تحويل الوزن للرادار في fuse_health.
    """
    require_service_token(x_agent_token, AGENT_TOKEN)
    requested = [i.strip() for i in indices.split(",") if i.strip()]
    out: dict = {
        "field_id": field_id,
        "real_data": False,
        "observed_at": None,
        "field_coverage": None,
        "cloud_cover": cloud_cover,
        "resolution_m": 10.0,
    }
    coverage_val = None
    for idx in requested:
        # rvi رادارية: تُحسب من COG ثنائي النطاق (VV/VH) لا band واحد
        if idx == "rvi":
            m = await rvi_from_sar_cog(
                field_id,
                date,
                layers=LAYERS,
                field_layers=FIELD_LAYERS,
                tenant_getter=REQ_TENANT.get,
                logger=logger,
                object_store_module=object_store,
            )
            out["rvi"] = m
            if m is not None:
                out["real_data"] = True
            continue
        layer = await resolve_field_layer(
            field_id,
            idx,
            date,
            layers=LAYERS,
            field_layers=FIELD_LAYERS,
            tenant_getter=REQ_TENANT.get,
            logger=logger,
            object_store_module=object_store,
        )
        real = grid_from_cog(layer, idx, date, 16, object_store) if layer is not None else None
        if real is None:
            out[idx] = None
            continue
        out[idx] = real["stats"]["mean"]
        out["real_data"] = True
        out["observed_at"] = out["observed_at"] or real.get("date")
        if coverage_val is None:
            cells = [v for row in real["grid"] for v in row]
            coverage_val = (
                round(sum(v is not None for v in cells) / len(cells), 4) if cells else None
            )
    out["field_coverage"] = coverage_val
    out["note"] = (
        None if out["real_data"] else "لا COG مقصوص للحقل — شغّل /process أوّلاً (لا قيم مخترعة)"
    )
    return out
