"""routers/analysis.py — مسارات تحليل الغطاء النباتيّ (analyze/timeseries/ndvi)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المعاملات/
المخرجات/المصادقة مطابقة. التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في
``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

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
    if await main.load_field(field_id, tenant_id) is None:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    real = await main._real_timeseries_from_raster(field_id, "ndvi", days)
    if real is None:
        if main.VEGETATION_REAL_ONLY:
            raise HTTPException(424, "authoritative raster timeseries is required in production")
        return {
            "field_id": field_id,
            "days": days,
            "timeseries": [],
            "data_source": "raster-service",
            "real_data": False,
            "available": False,
            "synthetic": False,
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

    يُعيد استخدام run_analysis (نافذة آخر ٣٠ يوماً) ثمّ يستخرج NDVI الحالي عبر
    _current_ndvi_payload. صدق المصدر: تقدير من نطاقات تركيبيّة (real_data=False)
    — لا بكسلات حقيقيّة (تلك في raster-service).
    """
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    field = await main.load_field(field_id, tenant_id)
    if field is None:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=30)).isoformat()
    analysis = await main.run_analysis(field_id, tenant_id, date_from, date_to)
    payload = main._current_ndvi_payload(field_id, field, analysis)
    # production real-only mode: an estimated "current NDVI" must not masquerade
    # as an operational reading — fail closed instead of serving a simulation.
    if main.VEGETATION_REAL_ONLY and not payload.get("real_data"):
        raise HTTPException(424, "authoritative current NDVI is required in production")
    return payload


@router.get("/v1/all_fields")
async def all_fields(token: str = Depends(main.security)):
    """NDVI الحالي لكلّ الحقول المعروفة (يستهلكه useAllFieldsNdvi/لوحة المؤشّرات).

    يكرّر على فهرس الحقول (FIELD_REGISTRY هو كتالوج التعداد التركيبيّ — لا توجد
    نقطة «list fields» مستأجَرة هنا) ويُحمّل ميتاداتا كلّ حقل عبر load_field (قد
    تأتي من القاعدة/المنصّة عند تفعيل العلم). الردّ {fields:[...]} لكلّ منه
    field_id/name/crop/ndvi/health — تقدير صادق (real_data=False افتراضيّاً).
    """
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=30)).isoformat()
    # production real-only mode: FIELD_REGISTRY is a synthetic enumeration catalog;
    # a tenant-scoped platform listing does not exist here yet — honest 501.
    if main.VEGETATION_REAL_ONLY:
        raise HTTPException(
            501, "all_fields requires a tenant-scoped platform field listing in production"
        )
    fields_out = []
    for fid in main.FIELD_REGISTRY:
        field = await main.load_field(fid, tenant_id) or {}
        analysis = await main.run_analysis(fid, tenant_id, date_from, date_to)
        payload = main._current_ndvi_payload(fid, field, analysis)
        fields_out.append(
            {
                "field_id": fid,
                "field_name": field.get("name") or fid,
                "name": field.get("name") or fid,
                "crop": field.get("crop"),
                "area_ha": field.get("area_ha"),
                "ndvi": payload["ndvi"]["current"],
                "status": payload["classification"].get("status"),
                "health": payload["classification"],
                "real_data": payload["real_data"],
            }
        )
    return {
        "fields": fields_out,
        "count": len(fields_out),
        "tenant_id": tenant_id,
        "real_data": False,
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
