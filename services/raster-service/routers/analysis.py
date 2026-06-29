"""routers/analysis.py — تحاليل المؤشّرات والتضاريس والملوحة (Analysis)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.post("/zones/classify")
async def zones_classify(req: main.ManagementZonesRequest, x_agent_token: str = Header(None)):
    """مناطق الإدارة داخل الحقل (سدّ فجوة P1): تقسيم أداء + وصفة VRT.

    يقسّم قيم بكسلات المؤشّر لمناطق (عالٍ/متوسّط/منخفض) بالكوانتايل، ويُنتج
    وصفة متغيّرة المعدّل إن مُرّر base_rate. صدق: يعمل على قيم حقيقيّة.
    """
    main._require_service_token(x_agent_token)
    import management_zones as mz

    result = mz.classify_zones(req.pixel_values, n_zones=req.n_zones)
    if req.base_rate is not None and result.get("zones"):
        result["prescription"] = mz.prescription_from_zones(
            result["zones"], req.base_rate, strategy=req.strategy
        )
    return result


@router.post("/change/detect")
async def change_detect(req: main.ChangeDetectRequest, x_agent_token: str = Header(None)):
    """كشف التغيير المكاني (per-pixel 2D) بين تاريخين — أين تدهور/تحسّن الحقل.

    يسدّ فجوة كانت placeholder: التحليل الزمني 1D (متوسّط) يُخفي التدهور الموضعي
    (زحف ملوحة من زاوية، عطل ريّ في قطاع). يستقبل شبكتي مؤشّر مُحسبتَين فعليّاً من
    COG لتاريخين (نفس النهج الصادق: لا يخترع NDVI من البحث) ويُرجِع خريطة فرق
    مُصنّفة + نسب المساحة المتدهورة + تفسير عربي. NaN/null لا تُحسب (صدق السحاب).
    """
    main._require_service_token(x_agent_token)
    # حدّ الحجم قبل أيّ تحويل numpy (حماية من DoS) ⇒ 413 عند التجاوز.
    for name, g in (("grid_before", req.grid_before), ("grid_after", req.grid_after)):
        cells = sum(len(row) for row in g)
        if cells > main.MAX_CHANGE_GRID_CELLS:
            raise HTTPException(
                status_code=413,
                detail=f"{name} كبير جدّاً: {cells} خليّة > الحدّ {main.MAX_CHANGE_GRID_CELLS}",
            )
    import change_detection as cd

    result = cd.detect_change(
        req.grid_before,
        req.grid_after,
        index=req.index,
        slight_threshold=req.slight_threshold,
        severe_threshold=req.severe_threshold,
    )
    result.update(
        {
            "field_id": req.field_id,
            "date_before": req.date_before,
            "date_after": req.date_after,
        }
    )
    return result


@router.post("/fvc/compute")
async def fvc_compute(req: main.FvcComputeRequest, x_agent_token: str = Header(None)):
    """نسبة التغطية النباتيّة (FVC) عبر نموذج البكسل الثنائي — تكمّل LAI.

    LAI (موجود) يقيس كثافة الأوراق (3D)؛ FVC يقيس نسبة الأرض المُغطّاة بالنبات
    (2D) — أساس موضوعي لرصد زحف التصحّر وتغطية المحاصيل في الجوف. يستقبل شبكة
    NDVI مُحسبة من COG ويُرجِع شبكة FVC + نسبة التصحّر + تصنيف + تفسير عربي.
    """
    main._require_service_token(x_agent_token)
    cells = sum(len(row) for row in req.ndvi_grid)
    if cells > main.MAX_CHANGE_GRID_CELLS:
        raise HTTPException(
            status_code=413, detail=f"ndvi_grid كبير جدّاً: {cells} > {main.MAX_CHANGE_GRID_CELLS}"
        )
    import fvc

    try:
        result = fvc.compute_fvc(
            req.ndvi_grid, method=req.method, ndvi_soil=req.ndvi_soil, ndvi_veg=req.ndvi_veg
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    result.update({"field_id": req.field_id, "date": req.date})
    return result


@router.post("/sar/rvi")
async def sar_rvi_endpoint(req: main.SarRviRequest, x_agent_token: str = Header(None)):
    """مؤشّر الغطاء الراداري RVI من Sentinel-1 VV/VH — يُكمل مقاومة السحاب.

    RVI = 4·σ°VH/(σ°VV+σ°VH) (قدرة خطّيّة)، مقصوص [0,1] كبديل غطاء قابل للدمج مع
    NDVI كـfamily="sar". المُدخلات شبكتا VV/VH مُحسبتان من COG رادار مُعايَر
    (العامل، rasterio). صدق: فجوات NaN محفوظة. rvi_mean يُمرَّر كإشارة source=rvi.
    """
    main._require_service_token(x_agent_token)
    cells = sum(len(row) for row in req.vv_grid)
    if cells > main.MAX_CHANGE_GRID_CELLS:
        raise HTTPException(
            status_code=413, detail=f"vv_grid كبير جدّاً: {cells} > {main.MAX_CHANGE_GRID_CELLS}"
        )
    import sar_rvi

    try:
        result = sar_rvi.compute_rvi(req.vv_grid, req.vh_grid, in_db=req.in_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    result.update({"field_id": req.field_id, "date": req.date})
    return result


@router.post("/terrain/slope")
async def terrain_slope(req: main.TerrainRequest, x_agent_token: str = Header(None)):
    """يحسب الانحدار من DEM + يصنّف ملاءمة حصاد المياه (زراعة اليمن).

    يأخذ dem_url (من /imagery/dem) ويحسب الانحدار/الاتّجاه ثمّ يوصي بتقنيّة
    حصاد المياه المناسبة. صدق: الحساب الفعلي يحتاج rasterio في التشغيل.
    """
    main._require_service_token(x_agent_token)
    import terrain_analysis as ta

    result = ta.compute_slope_aspect(main._safe_raster_source(req.dem_url), req.pixel_size_m)
    if result.get("computed") and result.get("slope_deg"):
        result["water_harvesting"] = ta.classify_water_harvesting(result["slope_deg"]["mean"])
    return result


@router.get("/cog/validate")
async def cog_validate(path: str, x_agent_token: str = Header(None)):
    """يتحقّق أنّ ملفّاً COG صالح (مبلّط + أهرامات داخليّة) — تدقيق الجودة.

    COG جيّد = قراءة جزئيّة سريعة. هذا يكشف "COG يفتح لكن بطيء".
    """
    main._require_service_token(x_agent_token)
    # حماية path traversal
    if ".." in path:
        raise HTTPException(400, "مسار غير صالح")
    import cog_writer

    return cog_writer.validate_cog(path)


@router.post("/salinity/classify")
async def salinity_classify(req: main.SalinityClassifyRequest, x_agent_token: str = Header(None)):
    """يصنّف NDSI لصنف ملوحة (heuristic إقليمي للجوف). تقديري."""
    main._require_service_token(x_agent_token)
    return main._sal.classify_ndsi_salinity(req.ndsi)


@router.post("/salinity/calibrate")
async def salinity_calibrate(req: main.SalinityFitRequest, x_agent_token: str = Header(None)):
    """يلائم انحدار NDSI→ECe من أزواج حقيقيّة (عند جمعها بإحداثيّات + EC).

    يفرض: 5 عيّنات+ وطريقة استخلاص موحّدة (لا يقبل بيانات تُنتج معايرة زائفة)."""
    main._require_service_token(x_agent_token)
    return main._sal.fit_regression(req.samples)
