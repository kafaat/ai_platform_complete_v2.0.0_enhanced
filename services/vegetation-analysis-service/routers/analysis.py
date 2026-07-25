"""routers/analysis.py — مسارات تحليل الغطاء النباتيّ (analyze/timeseries/ndvi)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المعاملات/
المخرجات/المصادقة مطابقة. التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في
``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import main
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter()


@router.get("/v1/analyze")
async def analyze(
    field_id: str,
    tenant_id: str = Query(default="default"),
    # M8 FIX: لا تُقيّم date.today() في توقيع الدالّة (يُحسب مرّة عند الاستيراد ⇒
    # "اليوم" مُجمّد حتّى إعادة التشغيل). نستخدم None ونحسب النافذة لكلّ طلب.
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    # V5: سياق الموسم اختياريّ (متوافق للخلف) — يُمرَّر ويُصدَّر للنَّسَب.
    season_id: str | None = Query(default=None, max_length=128),
    token: str = Depends(main.security),
):
    claims = main._verify_claims(token)
    # المستأجِر من التوكن لا من الـquery (منع حقن موضوع NATS عابر المستأجرين)
    tenant_id = main._tenant_from_claims(claims)
    date_to = main._valid_date(date_to) if date_to else date.today().isoformat()
    date_from = (
        main._valid_date(date_from)
        if date_from
        else (date.today() - timedelta(days=30)).isoformat()
    )
    return await main.run_analysis(field_id, tenant_id, date_from, date_to, season_id=season_id)


@router.get("/v1/timeseries/{field_id}")
async def timeseries(
    field_id: str, days: int = Query(default=90, ge=5, le=365), token: str = Depends(main.security)
):
    claims = main._verify_claims(token)
    tenant_id = str(claims.get("tenant_id") or "") or None
    if (
        await main.load_field(field_id, tenant_id, user_bearer=token.credentials if token else None)
        is None
    ):
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    real, reason = await main._real_timeseries_from_raster(
        field_id, "ndvi", days, tenant_id=tenant_id
    )
    if real is None:
        if main.VEGETATION_REAL_ONLY:
            raise HTTPException(424, detail=main._ndvi_unavailable_detail(field_id, reason))
        return {
            "field_id": field_id,
            "days": days,
            "timeseries": [],
            "data_source": "raster-service",
            "real_data": False,
            "available": False,
            "synthetic": False,
            "degraded": True,
            "reason": reason or "no_processed_observation",
            "warning_ar": "لا توجد سلسلة رصد فعلية؛ لم يتم إنشاء قيم تركيبية.",
            "generated_at": main.datetime.now(main.UTC).isoformat(),
        }
    return {
        "field_id": field_id,
        "days": days,
        "timeseries": real.get("points", []),
        "monthly_composite": real.get("monthly_composite", []),
        "trend": real.get("trend"),
        "anomalies": real.get("anomalies", []),
        "data_source": "raster-service",
        "real_data": True,
        "available": True,
        "synthetic": False,
        "generated_at": main.datetime.now(main.UTC).isoformat(),
    }


@router.get("/v1/ndvi/current/{field_id}")
async def current_ndvi(field_id: str, token: str = Depends(main.security)):
    """NDVI الحالي + تصنيف الصحّة لحقل واحد (يستهلكه useCurrentNDVI في الواجهة).

    يقرأ أحدث مشاهدة NDVI موثّقة من raster-service. عند غيابها لا تُنشأ قيمة
    تركيبيّة إطلاقاً: في الإنتاج (real-only) يفشل مُغلَقاً 424، وفي التطوير يعيد
    available=false بوسم صريح.
    """
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    field = await main.load_field(
        field_id, tenant_id, user_bearer=token.credentials if token else None
    )
    if field is None:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    observed, reason = await main._current_ndvi_from_raster(field_id, tenant_id=tenant_id)
    if observed is None:
        if main.VEGETATION_REAL_ONLY:
            raise HTTPException(424, detail=main._ndvi_unavailable_detail(field_id, reason))
        return {
            "field_id": field_id,
            "field_name": field.get("name"),
            "crop": field.get("crop"),
            "ndvi": {"current": None},
            "classification": None,
            "acquisition_date": None,
            "data_source": "raster-service",
            "real_data": False,
            "available": False,
            "synthetic": False,
            "degraded": True,
            "reason": reason or "no_processed_observation",
            "warning_ar": "لا توجد مشاهدة NDVI فعليّة متاحة؛ لم يتم إنشاء قيمة تركيبيّة.",
        }
    value = observed["value"]
    return {
        "field_id": field_id,
        "field_name": field.get("name"),
        "crop": field.get("crop"),
        "ndvi": {"current": value},
        "classification": main._health_classification(value),
        "acquisition_date": observed["observed_at"],
        "scene_id": observed["scene_id"],
        "data_available_at": observed.get("data_available_at"),
        "quality_score": observed.get("quality_score"),
        "valid_pixel_pct": observed.get("valid_pixel_pct"),
        "algorithm_version": observed.get("algorithm_version"),
        "qa_mask_version": observed.get("qa_mask_version"),
        "data_source": "raster-service",
        "real_data": True,
        "available": True,
    }


@router.get("/v1/all_fields")
async def all_fields(token: str = Depends(main.security)):
    """Return current NDVI for the authenticated tenant's real platform fields."""
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    catalog = await main.list_fields_from_platform(tenant_id)
    # كلّ حقل يستدعي raster-service (HTTP، مهلة 15s)؛ الحلقة التسلسليّة تعني N جولات
    # متتابعة (أسوأ حالة N×15s). نُجريها بتزامن محدود (Semaphore=8) — نفس النتائج، زمن
    # جدار = أبطأ سلسلة لا مجموعها. الترتيب محفوظ عبر zip مع القائمة المُصفّاة.
    valid = [
        (fid, item)
        for item in catalog
        if (fid := str(item.get("id") or item.get("field_id") or "").strip())
    ]
    _sem = asyncio.Semaphore(8)

    async def _observe(fid: str):
        async with _sem:
            observed, _reason = await main._current_ndvi_from_raster(fid, tenant_id=tenant_id)
            return observed

    observed_all = await asyncio.gather(*[_observe(fid) for fid, _ in valid])
    fields_out = []
    for (fid, item), observed in zip(valid, observed_all, strict=True):
        value = observed.get("value") if observed else None
        health = main._health_classification(value, 0.5) if value is not None else None
        fields_out.append(
            {
                "field_id": fid,
                "field_name": item.get("name") or fid,
                "name": item.get("name") or fid,
                "crop": item.get("crop") or item.get("crop_type"),
                "area_ha": item.get("area_ha"),
                "ndvi": value,
                "status": health.get("status") if health else None,
                "health": health,
                "acquisition_date": observed.get("observed_at") if observed else None,
                "scene_id": observed.get("scene_id") if observed else None,
                "real_data": observed is not None,
                "available": observed is not None,
            }
        )
    return {
        "fields": fields_out,
        "count": len(fields_out),
        "tenant_id": tenant_id,
        "real_data": all(item["real_data"] for item in fields_out) if fields_out else True,
        "generated_at": main.datetime.now(main.UTC).isoformat(),
    }


@router.get("/v1/indicators/registry")
async def indicators_registry(token: str = Depends(main.security)):
    """كتالوج المؤشّرات القانونيّ (observed/derived + الأهليّة + النطاقات) للمستهلكين."""
    main._verify_claims(token)
    return {"version": main.REGISTRY_VERSION, "indicators": main.INDICATORS}


@router.get("/v1/indicators/registry/{name}")
async def indicator_registry_item(name: str, token: str = Depends(main.security)):
    main._verify_claims(token)
    try:
        return main.indicator_definition(name)
    except KeyError:
        raise HTTPException(404, "unknown indicator") from None
