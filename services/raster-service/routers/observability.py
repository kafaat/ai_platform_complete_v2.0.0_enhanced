"""routers/observability.py — فحوص الصحّة والمقاييس والمعلومات (Observability)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import os

import httpx
import main
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

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

    by_status = Counter(j.get("status") for j in main._jobs.values())

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
        f"sahool_raster_layers_total {len(main._layers)}",
        "# HELP sahool_raster_jobs_active المهامّ قيد المعالجة الآن",
        "# TYPE sahool_raster_jobs_active gauge",
        f"sahool_raster_jobs_active "
        f"{sum(1 for j in main._jobs.values() if _s(j.get('status')) == 'processing')}",
    ]
    # صحّة عميل STAC (مرونة قلب النظام)
    h = main._stac.health()
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
        f"sahool_raster_tilejson_requests_total {main._TILE_OBS['tilejson_requests_total']}",
        "# HELP sahool_raster_tilejson_unavailable_total TileJSON responses with available=false",
        "# TYPE sahool_raster_tilejson_unavailable_total counter",
        f"sahool_raster_tilejson_unavailable_total {main._TILE_OBS['tilejson_unavailable_total']}",
        "# HELP sahool_raster_tile_requests_total Field tile image requests",
        "# TYPE sahool_raster_tile_requests_total counter",
        f"sahool_raster_tile_requests_total {main._TILE_OBS['tile_requests_total']}",
        "# HELP sahool_raster_tile_cache_hits_total Persistent tile cache hits",
        "# TYPE sahool_raster_tile_cache_hits_total counter",
        f"sahool_raster_tile_cache_hits_total {main._TILE_OBS['tile_cache_hits_total']}",
        "# HELP sahool_raster_tile_cache_misses_total Persistent tile cache misses",
        "# TYPE sahool_raster_tile_cache_misses_total counter",
        f"sahool_raster_tile_cache_misses_total {main._TILE_OBS['tile_cache_misses_total']}",
        "# HELP sahool_raster_tile_transparent_total Transparent tiles returned because no raster data was available",
        "# TYPE sahool_raster_tile_transparent_total counter",
        f"sahool_raster_tile_transparent_total {main._TILE_OBS['tile_transparent_total']}",
        "# HELP sahool_raster_tile_render_errors_total Tile rendering errors hidden behind transparent fallback",
        "# TYPE sahool_raster_tile_render_errors_total counter",
        f"sahool_raster_tile_render_errors_total {main._TILE_OBS['tile_render_errors_total']}",
    ]
    for idx, counters in sorted(main._TILE_OBS_BY_INDEX.items()):
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
        "counters": dict(main._TILE_OBS),
        "by_index": {k: dict(v) for k, v in main._TILE_OBS_BY_INDEX.items()},
        "cache_enabled": os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true",
        "message": "راقب tilejson_unavailable_total و tile_transparent_total عند عدم ظهور طبقة المؤشر",
    }


@router.get("/readyz")
async def readyz():
    """يتحقّق من الوصول لـEarth Search."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{main.EARTH_SEARCH_URL}/")
            ok = r.status_code < 500
        body = {
            "status": "ready" if ok else "degraded",
            "earth_search": "reachable" if ok else "unreachable",
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503, content={"status": "degraded", "earth_search": "unreachable"}
        )


@router.get("/v1/tile-cache/stats")
async def tile_cache_stats(x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    root = os.path.join(main.UPLOAD_DIR, "tile_cache")
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
    main._require_service_token(x_agent_token)
    layer = main._layers.get(layer_id)
    if not layer:
        raise HTTPException(404, "طبقة غير موجودة")
    return layer


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
    main._require_service_token(x_agent_token)
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
            m = await main._rvi_from_sar_cog(field_id, date)
            out["rvi"] = m
            if m is not None:
                out["real_data"] = True
            continue
        layer = await main._resolve_field_layer(field_id, idx, date)
        real = main._grid_from_cog(layer, idx, date, 16) if layer is not None else None
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
