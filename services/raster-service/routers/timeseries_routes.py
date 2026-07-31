"""routers/timeseries_routes.py — السلاسل الزمنيّة للصور (Imagery Time-Series)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
the extracted modules directly. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from raster_api_models import TimeSeriesAnalyzeRequest
from raster_security_context import require_service_token
from stac_search import stac_search

router = APIRouter()


@router.get("/v1/imagery/timeseries")
async def imagery_timeseries(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """تحليل زمني (سدّ فجوة P0): تركيب شهري + اتّجاه + كشف شذوذ.

    يبحث STAC عن مشاهد الفترة، يجمّعها شهريّاً (median compositing لتخفيف
    الغيوم)، ويحسب الاتّجاه (تحسّن/تدهور) والشذوذ. صدق: عند توفّر القيم
    المحسوبة لكلّ مشهد تُجمَّع؛ وإلّا يُرجِع البنية الزمنيّة + المشاهد لحساب
    العميل/العامل (لا يخترع قيم NDVI من البحث وحده).
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        search = await stac_search(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end_date}T23:59:59Z",
            max_cloud_pct,
            limit=100,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e

    scenes = search.get("items", [])
    # المشاهد من STAC تحمل التاريخ والغيوم لكن ليس NDVI محسوباً بعد —
    # نُرجِع البنية الزمنيّة (تجميع شهري بعدد المشاهد) + قائمة للمعالجة.
    # تجميع شهري لعدد المشاهد المتاحة (لا قيم مخترعة)
    from collections import Counter

    month_counts = Counter(s["datetime"][:7] for s in scenes if s.get("datetime"))
    timeline = [{"month": m, "scenes_available": c} for m, c in sorted(month_counts.items())]
    # V63 — عقد مشهد موحَّد بجانب الخام (غير كاسر): كلّ مشهد بهويّة provider + تاريخ
    # التقاط + cog_ready، كي يستهلكه UI/agent evidence دون إعادة تحليل قواميس مخصّصة.
    from raster_scene_model import normalize_search_result

    normalized = [s.to_dict() for s in normalize_search_result(search)]
    return {
        "period": {"start": start, "end": end_date},
        "total_scenes": len(scenes),
        "monthly_availability": timeline,
        "scenes": scenes,
        "normalized_scenes": normalized,
        "note": "احسب المؤشّر لكلّ مشهد عبر /v1/process ثمّ مرّر القيم لـ"
        "/v1/imagery/timeseries/analyze للحصول على الاتّجاه والشذوذ",
    }


@router.post("/v1/imagery/timeseries/analyze")
async def imagery_timeseries_analyze(
    req: TimeSeriesAnalyzeRequest, x_agent_token: str = Header(None)
):
    """يحلّل قيم مؤشّر محسوبة عبر الزمن: تركيب شهري + اتّجاه + شذوذ.

    يستقبل قيم المؤشّر المحسوبة فعليّاً لكلّ مشهد (من /v1/process) ويُرجِع
    التحليل الزمني الكامل. صدق: يعمل على قيم حقيقيّة مُمرَّرة، لا مخترعة.
    """
    require_service_token(x_agent_token)
    import time_series as ts

    return ts.build_time_series(req.scene_values, value_key="mean")


@router.post("/v1/imagery/timeseries/parallel")
async def imagery_timeseries_parallel(
    req: TimeSeriesAnalyzeRequest,
    max_concurrency: int = Query(4, ge=1, le=10),
    x_agent_token: str = Header(None),
):
    """تحليل زمني بمعالجة متوازية للمشاهد (أسرع للسلاسل الطويلة).

    يحلّل قيماً محسوبة مسبقاً (من /v1/process) بالتوازي المحدود + يبني التحليل.
    semaphore يحدّ التزامن (backpressure). عزل فشل كلّ مشهد.
    """
    require_service_token(x_agent_token)
    import time_series as ts

    async def _passthrough(sc):
        # القيم محسوبة مسبقاً — نمرّرها (لا إعادة حساب). للتوضيح: في خطّ حقيقي
        # تستبدلها بدالّة تحسب المؤشّر من COG المشهد.
        return sc.get("mean")

    return await ts.build_time_series_parallel(
        req.scene_values, _passthrough, max_concurrency=max_concurrency
    )
