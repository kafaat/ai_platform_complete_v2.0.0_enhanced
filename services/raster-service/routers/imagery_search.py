"""routers/imagery_search.py — البحث عن الصور والمشاهد (Imagery Search)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import main
from fastapi import APIRouter, Header, HTTPException, Query

router = APIRouter()


@router.get("/imagery/search/recent")
async def imagery_search_recent(
    west: float,
    south: float,
    east: float,
    north: float,
    days_back: int = Query(30, ge=1, le=365),
    max_cloud_pct: float = Query(30, ge=0, le=100),
):
    """آخر صور Sentinel-2 لمنطقة بـbbox (خلال days_back يوماً)."""
    now = datetime.now(UTC)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    end = now.strftime("%Y-%m-%dT23:59:59Z")
    try:
        return await main._stac_search(
            [west, south, east, north], start, end, max_cloud_pct, limit=20
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@router.get("/imagery/search/season")
async def imagery_search_season(
    west: float,
    south: float,
    east: float,
    north: float,
    sowing_date: str,
    harvest_date: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """كلّ صور الموسم الزراعي (من البذار للحصاد) — للـCropTimeline."""
    end = harvest_date or datetime.now(UTC).strftime("%Y-%m-%d")
    start = f"{sowing_date}T00:00:00Z"
    end_iso = f"{end}T23:59:59Z"
    try:
        return await main._stac_search(
            [west, south, east, north], start, end_iso, max_cloud_pct, limit=60
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@router.get("/imagery/best")
async def imagery_best_scene(
    west: float,
    south: float,
    east: float,
    north: float,
    lookback_days: int = Query(30, ge=1, le=180),
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """يختار أفضل مشهد حديث (توازن الحداثة + قلّة الغيوم) — تحسين القلب.

    بدل أخذ الأحدث دائماً (قد يكون غائماً)، يوازن: مشهد حديث منخفض الغيوم
    أفضل من أحدث غائم. درجة = أولويّة قلّة الغيوم مع تفضيل الحداثة عند التعادل.
    صدق: يختار من المتاح فعليّاً؛ لا يخترع مشهداً.
    """
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    try:
        result = await main._stac_search(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end}T23:59:59Z",
            max_cloud_pct,
            limit=30,
        )
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search: {e}") from e

    items = result.get("items", [])
    if not items:
        return {
            "best": None,
            "candidates": 0,
            "note": "لا مشاهد ضمن المعايير — وسّع lookback أو max_cloud",
        }

    # درجة: كلّما قلّ الغيوم زادت؛ مع مكافأة بسيطة للحداثة (الأحدث أوّلاً أصلاً).
    def score(idx_item):
        idx, it = idx_item
        cloud = it.get("cloud_cover_pct", 100)
        recency_bonus = (len(items) - idx) / len(items) * 10  # 0-10
        return (100 - cloud) + recency_bonus

    best_idx, best = max(enumerate(items), key=score)
    return {
        "best": best,
        "candidates": len(items),
        "selection": "أقلّ غيوم مع تفضيل الحداثة",
        "cache": result.get("cache"),
    }


@router.post("/imagery/search")
async def imagery_search(req: main.SearchRequest, x_agent_token: str = Header(None)):
    """بحث متقدّم بكلّ الخيارات."""
    main._require_service_token(x_agent_token)
    try:
        return await main._stac_search(
            req.bbox, req.datetime_start, req.datetime_end, req.max_cloud_pct, req.limit
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@router.get("/imagery/search/radar")
async def imagery_search_radar(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    limit: int = Query(20, ge=1, le=100),
):
    """بحث رادار Sentinel-1 GRD — يخترق الغيوم (مفيد لموسم الأمطار).

    لا فلتر غيوم (الرادار لا يتأثّر بها). يُرجع استقطابات VV/VH للاستخدام
    في رطوبة التربة وكشف الفيضانات — لا NDVI.
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        return await main._stac_search_radar(
            [west, south, east, north], f"{start}T00:00:00Z", f"{end_date}T23:59:59Z", limit
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search (radar): {e}") from e


@router.get("/imagery/search/landsat")
async def imagery_search_landsat(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
):
    """بحث Landsat C2 L2 — أرشيف طويل المدى (40+ سنة) تكميلي لـSentinel-2.

    دقّة 30م، تردّد 16 يوماً. مفيد للتحليل التاريخي قبل عصر Sentinel-2 (2015).
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        return await main._stac_search_landsat(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end_date}T23:59:59Z",
            max_cloud_pct,
            limit,
        )
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (landsat): {e}") from e


@router.get("/imagery/dem")
async def imagery_dem(west: float, south: float, east: float, north: float):
    """نموذج الارتفاع الرقمي (Copernicus DEM 30م) لمنطقة — للانحدار/الصرف.

    حرج لزراعة اليمن المُدرّجة الصحراويّة: تخطيط حصاد المياه، اتّجاه الجريان،
    مواقع السدود الترابيّة. DEM ثابت (لا زمني) — لا datetime/cloud.
    """
    try:
        return await main._stac_search_dem([west, south, east, north])
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (DEM): {e}") from e
