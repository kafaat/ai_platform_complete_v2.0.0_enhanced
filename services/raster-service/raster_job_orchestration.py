"""Batch job orchestration extracted from raster-service main.py.

The staged decomposition keeps runtime state in ``main`` for now.  This module
receives the application module as ``ctx`` so behavior and public contracts stay
unchanged while the long main.py is split into testable pieces.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException


def run_processing(ctx, job_id: str, req):
    """ينفّذ معالجة المؤشّر. البنية كاملة؛ حساب البكسلات الفعلي يتمّ عند
    توفّر rasterio في بيئة التشغيل (يُحقن هنا)."""
    # نحمّل المهمّة، نطفّرها محليّاً، ونثبّتها في المخزن (Redis/ذاكرة) عند
    # نقاط الانتقال — كي تَنفُذ التغييرات عبر العمليّات لا في dict محلّيّ فقط.
    job = ctx._jobs.get(job_id) or {"job_id": job_id}
    job["status"] = ctx.JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    job["progress_pct"] = 10
    ctx._jobs.set(job_id, job)
    try:
        # نقطة حقن المعالجة الفعليّة (rasterio/numpy):
        #   1. اقرأ الراستر من req.raster_url
        #   2. طبّق band math حسب _INDICATOR_FORMULAS[req.indicator]
        #   3. طبّق cloud mask (SCL) إن apply_cloud_mask
        #   4. clip بـclip_polygon_geojson
        #   5. أنتج بلاطات (tiling_strategy) واحفظها
        #   6. احسب الإحصاءات (min/max/mean/std)
        try:
            import numpy  # noqa: F401
            import rasterio  # noqa: F401

            _has_raster_libs = True
        except ImportError:
            _has_raster_libs = False

        layer_id = f"layer_{uuid.uuid4().hex[:12]}"
        meta: dict = {}
        if _has_raster_libs and req.raster_url:
            # المعالجة الفعليّة (تتمّ في بيئة التشغيل مع rasterio)
            if req.precomputed_index:
                # CDSE: المؤشّر محسوب خادميّاً — اقرأه نطاقاً واحداً جاهزاً.
                stats, bounds, res_m, meta = ctx._process_precomputed_pixels(req, layer_id)
            else:
                stats, bounds, res_m, meta = ctx._process_pixels(req, layer_id)
        else:
            # بنية بلا حساب فعلي (البيئة بلا rasterio) — ترجع هيكلاً صحيحاً
            stats = {
                "min": 0.0,
                "max": 1.0,
                "mean": 0.0,
                "std": 0.0,
                "valid_pixels": 0,
                "nodata_pixels": 0,
            }
            bounds = [0.0, 0.0, 0.0, 0.0]
            res_m = 10.0
            job["note"] = "rasterio غير متوفّر — بنية صحيحة بلا حساب بكسلات"

        now = datetime.now(UTC).isoformat()
        # provenance (#7): سجلّ أصل كامل لإعادة الإنتاج
        import raster_provenance as _prov

        provenance = _prov.build_provenance(
            req.indicator.value,
            scene_id=req.scene_id,
            capture_datetime=req.capture_datetime,
            raster_url=req.raster_url,
            source_format=req.source_format.value,
            crs="EPSG:4326",
            resolution_m=res_m,
            apply_cloud_mask=req.apply_cloud_mask,
            band_mapping=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
            clip_polygon=req.clip_polygon_geojson,
        )
        cog_url = meta.get("cog_url")
        # v131 (v62.3-B): مقاييس جودة الصور للطبقة في الذاكرة كي تسطّحها شبكة
        # المؤشّر مباشرةً دون دورة قاعدة (نفس منطق الكاتب: عدّادات البكسلات من stats).
        import quality_metrics as _qm

        _vp = stats.get("valid_pixels")
        _npx = stats.get("nodata_pixels")
        _tot = (int(_vp) + int(_npx)) if (_vp is not None and _npx is not None) else None
        _layer_q = _qm.compute_quality_metrics(
            valid_pixels=int(_vp) if _vp is not None else None,
            total_pixels=_tot,
            cloud_pct=stats.get("cloud_pct"),
        )
        _cloud_pct = stats.get("cloud_pct")
        ctx._layers[layer_id] = {
            "layer_id": layer_id,
            "field_id": req.field_id,
            "tenant_id": req.tenant_id,
            "index": req.indicator.value,
            "source_format": req.source_format.value,
            "width": 0,
            "height": 0,
            "band_count": 1,
            # CRS الطبقة الفعلي = CRS الـCOG (UTM للـSentinel-2)؛ الحدود معاد
            # إسقاطها إلى 4326 لعرض الخريطة.
            "crs": meta.get("cog_crs", "EPSG:4326"),
            "bounds_4326": bounds,
            "resolution_m": res_m,
            "cog_url": cog_url,  # (٤) كي يجده tilejson + شبكة المؤشّر
            "acquisition_date": req.capture_datetime,
            "provider": req.provider,  # مصدر الصورة (cdse/element84) — شفافيّة الأصل
            "cloud_pct": _cloud_pct,
            "cloud_cover": (_cloud_pct / 100.0) if _cloud_pct is not None else None,
            "valid_pixel_ratio": _layer_q["valid_pixel_ratio"],
            "coverage_ratio": _layer_q["coverage_ratio"],
            "index_quality_flags": _layer_q["index_quality_flags"],
            "cloud_mask_applied": stats.get("cloud_mask_applied"),
            "confidence": stats.get("confidence"),
            "quality": stats.get("quality"),
            "created_at": now,
            "provenance": provenance,
        }
        # فهرس حقل→طبقات (للبحث عن أحدث COG لحقل+مؤشّر في شبكة المؤشّر). يُستخدَم
        # ``ctx._field_layers`` (فهرس field_id→[layer_id]) لا ``ctx._layers`` (مخزن
        # layer_id→dict): كتب التفكيك اسماً غير مُعرَّف ومخزناً خاطئاً هنا فكان NameError
        # على كلّ معالجة لحقل. الأصل main.py:2036 قبل التفكيك: _field_layers.setdefault.
        if req.field_id:
            ctx._field_layers.setdefault(req.field_id, []).append(layer_id)
        # (٦) حفظ في raster_assets (best-effort — غياب القاعدة لا يُفشل المعالجة)
        # v5-audit F1: نلتقط persisted كي يُميّز «completed» بين الحفظ في DB والذاكرة فقط.
        persisted = (
            ctx._persist_raster_asset(req, cog_url, meta, bounds, stats, job_id=job_id)
            if cog_url
            else False
        )
        job["result"] = {
            "job_id": job_id,
            "layer_id": layer_id,
            "indicator": req.indicator.value,
            "stats": stats,
            "tile_url_template": f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png",
            "bounds_4326": bounds,
            "zoom_min": req.zoom_min,
            "zoom_max": req.zoom_max,
            "finished_at": now,
            "provenance": provenance,
            "persisted": persisted,  # v5-audit F1: هل حُفِظ في DB فعلاً (لا الذاكرة فقط)؟
        }
        job["status"] = ctx.JobStatus.completed
        job["progress_pct"] = 100
        job["finished_at"] = now
        ctx._jobs.set(job_id, job)  # تثبيت النتيجة المكتملة (Redis/ذاكرة)
        ctx.logger.info(f"job {job_id} completed → layer {layer_id} persisted={persisted}")
    except Exception as e:  # noqa: BLE001
        job["status"] = ctx.JobStatus.failed
        # لا نُخزّن تفاصيل الاستثناء الخام في job status لأنّها تُقرأ عبر API وقد
        # تحتوي مسارات ملفات/روابط/تفاصيل مكتبات. السجلّ الداخلي يحتفظ بنوع الخطأ،
        # ولـHTTPException يضيف status/detail (نصّنا المتحكَّم به) — النوع وحده جعل
        # فشل backfill غير قابل للتشخيص (بلاغ 2026-07-04: «HTTPException» بلا سبب).
        job["error_message"] = "raster_processing_failed"
        ctx._jobs.set(job_id, job)  # تثبيت الفشل (Redis/ذاكرة)
        _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
        # exc_info=True: السجلّ الداخلي يحمل التتبّع الكامل — الرسالة العامّة كانت «TypeError»
        # عارياً بعد بناء VRT فتعذّر التشخيص (بلاغ لوج المستخدم). الرمز العامّ للعميل يبقى مُعقَّماً.
        ctx.logger.error("job %s failed: %s%s", job_id, type(e).__name__, _http, exc_info=True)


def run_batch_processing(ctx, job_id: str, req):
    """يحسب عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    صدق: يعالج كلّ مؤشّر فعليّاً ويسجّل نتيجته. التوفير الحقيقي يأتي من قراءة
    المشهد مرّة (في الإنتاج مع rasterio)؛ بنيويّاً نتتبّع الكلّ في job واحد مع
    عزل فشل كلّ مؤشّر (فشل واحد لا يُسقط الباقي).
    """
    # نطفّر المهمّة محليّاً ونثبّتها في المخزن (Redis/ذاكرة) عند نقاط الانتقال.
    job = ctx._jobs.get(job_id) or {"job_id": job_id}
    job["status"] = ctx.JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    ctx._jobs.set(job_id, job)
    results = {}
    failed = {}
    total = len(req.indicators)
    for i, ind in enumerate(req.indicators):
        # ابنِ ctx.ProcessRequest فرديّاً لكلّ مؤشّر (يعيد استخدام المنطق المُختبَر)
        single = ctx.ProcessRequest(
            tenant_id=req.tenant_id,
            field_id=req.field_id,
            raster_url=req.raster_url,
            indicator=ind,
            source_format=req.source_format,
            bands=req.bands,
            clip_polygon_geojson=req.clip_polygon_geojson,
            apply_cloud_mask=req.apply_cloud_mask,
            scene_id=req.scene_id,
            capture_datetime=req.capture_datetime,
            geometry_revision=req.geometry_revision,  # v143: نَسَب الهندسة عبر المؤشّرات
        )
        sub_job_id = f"{job_id}_{ind.value}"
        ctx._jobs.set(
            sub_job_id,
            {
                "job_id": sub_job_id,
                "status": ctx.JobStatus.pending,
                "progress_pct": 0,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        try:
            ctx._run_processing(sub_job_id, single)
            sj = ctx._jobs.get(sub_job_id) or {}
            if sj["status"] == ctx.JobStatus.completed:
                results[ind.value] = sj.get("layer_id") or sub_job_id
            else:
                failed[ind.value] = sj.get("error_message", "unknown")
        except Exception as e:  # noqa: BLE001 — عزل لكلّ مؤشّر
            # توحيد main↔cert (#542): رمز عامّ للعميل + السجلّ الداخلي يحمل النوع
            # (+ status/detail لـHTTPException — نصّنا المتحكَّم به، لا تسريب نصّ خام).
            _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
            ctx.logger.warning("مهمّة فرعيّة %s فشلت: %s%s", ind.value, type(e).__name__, _http)
            failed[ind.value] = "processing_failed"
        job["progress_pct"] = int((i + 1) / total * 100)

    job["status"] = ctx.JobStatus.completed if results else ctx.JobStatus.failed
    job["finished_at"] = datetime.now(UTC).isoformat()
    job["batch_results"] = results
    job["batch_failed"] = failed
    ctx._jobs.set(job_id, job)  # تثبيت نتيجة الدفعة (Redis/ذاكرة)
    ctx.logger.info("batch %s: %d نجح، %d فشل", job_id, len(results), len(failed))
