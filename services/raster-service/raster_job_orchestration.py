"""Batch job orchestration extracted from raster-service main.py.

The staged decomposition keeps runtime state in ``main`` for now.  This module
receives the application module as ``ctx`` so behavior and public contracts stay
unchanged while the long main.py is split into testable pieces.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from raster_persistence_policy import terminal_status


class _LeaseHeartbeat:
    """Keep a PostgreSQL batch lease alive while a long indicator is running.

    A failed heartbeat is a fencing signal: the worker stops scheduling more
    indicators and must not write the durable terminal state. This prevents a
    healthy long-running operation from being reclaimed merely because one
    indicator exceeded the lease duration.
    """

    def __init__(self, *, claim_key: str, tenant_id: str, lease_token: str, logger):
        self.claim_key = claim_key
        self.tenant_id = tenant_id
        self.lease_token = lease_token
        self.logger = logger
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        lease_seconds = max(30, int(os.getenv("RASTER_BATCH_LEASE_SECONDS", "300")))
        configured = int(os.getenv("RASTER_BATCH_HEARTBEAT_SECONDS", "0") or 0)
        self.interval = max(5, configured or max(5, lease_seconds // 3))
        self.thread: threading.Thread | None = None

    def _beat(self) -> bool:
        try:
            import raster_batch_job_store

            ok = bool(
                raster_batch_job_store.heartbeat_sync(
                    claim_key=self.claim_key,
                    tenant_id=self.tenant_id,
                    lease_token=self.lease_token,
                )
            )
            try:
                import raster_batch_observability

                raster_batch_observability.inc(
                    "lease_heartbeat_success_total" if ok else "lease_heartbeat_failure_total"
                )
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
            return ok
        except Exception:
            try:
                import raster_batch_observability

                raster_batch_observability.inc("lease_heartbeat_exception_total")
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
            self.logger.warning("durable lease heartbeat raised", exc_info=True)
            return False

    def start(self) -> bool:
        if not self._beat():
            self.lost_event.set()
            return False
        self.thread = threading.Thread(
            target=self._run, name="raster-batch-lease-heartbeat", daemon=True
        )
        self.thread.start()
        return True

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval):
            if not self._beat():
                self.lost_event.set()
                return

    @property
    def lost(self) -> bool:
        return self.lost_event.is_set()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(1, min(self.interval, 5)))


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
        provenance["raw_processing"] = {
            "schema": "sahool.raw_processing/1",
            "raw_qa_required": bool(getattr(req, "raw_qa_required", True)),
            "quality_score": stats.get("raw_quality_score"),
            "pixel_qa": stats.get("pixel_qa"),
            "derived_product_computed": True,
            "indicator_computed": True,
            "fabricated_indicator": False,
        }
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
        _terminal, _error_code = terminal_status(persisted=bool(persisted))
        job["status"] = getattr(ctx.JobStatus, _terminal)
        job["progress_pct"] = 100 if persisted else 95
        job["finished_at"] = now
        if _error_code:
            job["error_code"] = _error_code
            job["publication_eligible"] = False
        else:
            job["publication_eligible"] = True
        ctx._jobs.set(job_id, job)
        ctx.logger.info(
            "job %s terminal=%s layer=%s persisted=%s publication_eligible=%s",
            job_id,
            _terminal,
            layer_id,
            persisted,
            job["publication_eligible"],
        )
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
    """Process several indicators with one source dataset open.

    The batch reuses the proven single-indicator persistence/provenance path while
    injecting one shared rasterio dataset and a per-band cache. Duplicate indicator
    requests are removed, failures remain isolated per indicator, and the job exposes
    the certified I/O strategy in its result metadata.
    """
    # نطفّر المهمّة محليّاً ونثبّتها في المخزن (Redis/ذاكرة) عند نقاط الانتقال.
    job = ctx._jobs.get(job_id) or {"job_id": job_id}
    job["status"] = ctx.JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    ctx._jobs.set(job_id, job)
    results = {}
    failed = {}
    unique_indicators = []
    seen_indicators = set()
    for ind in req.indicators:
        key = str(getattr(ind, "value", ind)).strip().lower()
        if not key or key in seen_indicators:
            continue
        seen_indicators.add(key)
        unique_indicators.append(ind)
    total = len(unique_indicators)
    job["requested_indicator_count"] = len(req.indicators)
    job["unique_indicator_count"] = total
    job["deduplicated_indicator_count"] = len(req.indicators) - total
    job["batch_io_strategy"] = "single_dataset_open_shared_band_cache"
    job["single_open_certified"] = False
    durable_claim_key = job.get("batch_claim_key")
    try:
        import raster_batch_runtime_leases

        durable_lease_token = raster_batch_runtime_leases.get_token(job_id)
    except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
        durable_lease_token = None
    durable_tenant_id = str(getattr(req, "tenant_id", "") or "")
    lease_heartbeat = None
    if (
        durable_claim_key
        and durable_lease_token
        and durable_tenant_id
        and job.get("claim_backend") == "postgres"
    ):
        lease_heartbeat = _LeaseHeartbeat(
            claim_key=durable_claim_key,
            tenant_id=durable_tenant_id,
            lease_token=durable_lease_token,
            logger=ctx.logger,
        )
        if not lease_heartbeat.start():
            job["status"] = ctx.JobStatus.failed
            job["error_message"] = "durable_lease_not_owned"
            job["finished_at"] = datetime.now(UTC).isoformat()
            ctx._jobs.set(job_id, job)
            try:
                import raster_batch_runtime_leases

                raster_batch_runtime_leases.pop_token(job_id)
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
            return
    try:
        import raster_batch_observability

        raster_batch_observability.inc("jobs_started_total")
        raster_batch_observability.inc("indicators_requested_total", len(req.indicators))
        raster_batch_observability.inc("indicators_unique_total", total)
        raster_batch_observability.inc("indicators_deduplicated_total", len(req.indicators) - total)
    except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
        pass
    # افتح مصدر الراستر مرة واحدة للدفعة كاملة، ومرّر dataset + cache إلى
    # المعالج الفردي المثبت. يحافظ هذا على نفس مسار الحفظ/provenance مع إزالة
    # إعادة فتح الملف وإعادة قراءة النطاقات المشتركة بين المؤشرات.
    shared_src = None
    shared_cache = {}
    original_process_pixels = getattr(ctx, "_process_pixels", None)
    try:
        if req.raster_url:
            import raster_pixel_processing
            import rasterio

            shared_src = rasterio.open(ctx._safe_raster_source(req.raster_url))
            ctx._process_pixels = lambda single_req, layer_id: (
                raster_pixel_processing.process_pixels(
                    ctx,
                    single_req,
                    layer_id,
                    shared_src=shared_src,
                    shared_cache=shared_cache,
                )
            )
            job["single_open_certified"] = True
            try:
                import raster_batch_observability

                raster_batch_observability.inc("dataset_open_actual_total", 1)
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
        else:
            job["batch_io_strategy"] = "no_raster_source"
    except Exception as exc:  # fail closed: لا نعود بصمت إلى إعادة الفتح لكل مؤشر
        job["status"] = ctx.JobStatus.failed
        job["error_message"] = "batch_shared_reader_open_failed"
        job["finished_at"] = datetime.now(UTC).isoformat()
        ctx._jobs.set(job_id, job)
        if (
            durable_claim_key
            and durable_lease_token
            and durable_tenant_id
            and job.get("claim_backend") == "postgres"
        ):
            try:
                import raster_batch_job_store

                raster_batch_job_store.finish_sync(
                    claim_key=durable_claim_key,
                    tenant_id=durable_tenant_id,
                    lease_token=durable_lease_token,
                    status="failed",
                    error_code="batch_shared_reader_open_failed",
                )
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                ctx.logger.warning("batch %s durable failure write failed", job_id)
            finally:
                try:
                    import raster_batch_runtime_leases

                    raster_batch_runtime_leases.pop_token(job_id)
                except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                    pass
        if lease_heartbeat is not None:
            lease_heartbeat.stop()
        ctx.logger.error(
            "batch %s shared reader open failed: %s", job_id, type(exc).__name__, exc_info=True
        )
        return

    for i, ind in enumerate(unique_indicators):
        if lease_heartbeat is not None and lease_heartbeat.lost:
            failed["__batch__"] = "durable_lease_lost"
            try:
                import raster_batch_observability

                raster_batch_observability.inc("lease_lost_total")
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
            break
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
            raw_qa_required=req.raw_qa_required,
            min_raw_quality_score=req.min_raw_quality_score,
            sun_azimuth_deg=getattr(req, "sun_azimuth_deg", None),
            sun_altitude_deg=getattr(req, "sun_altitude_deg", None),
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
        if lease_heartbeat is not None and lease_heartbeat.lost:
            failed["__batch__"] = "durable_lease_lost"
            break

    if lease_heartbeat is not None:
        lease_heartbeat.stop()
    if original_process_pixels is not None:
        ctx._process_pixels = original_process_pixels
    if shared_src is not None:
        shared_src.close()
    job["shared_band_cache_entries"] = len(shared_cache)
    lease_lost = bool(lease_heartbeat is not None and lease_heartbeat.lost)
    _persisted_results = [
        value
        for value in results.values()
        if isinstance(value, dict) and bool(value.get("persisted"))
    ]
    _all_persisted = bool(results) and len(_persisted_results) == len(results)
    if lease_lost:
        job["error_message"] = "durable_lease_lost"
        job["status"] = ctx.JobStatus.failed
    elif not results:
        job["status"] = ctx.JobStatus.failed
        job["error_code"] = "batch_no_products_completed"
    else:
        _terminal, _error_code = terminal_status(persisted=_all_persisted)
        job["status"] = getattr(ctx.JobStatus, _terminal)
        job["publication_eligible"] = _all_persisted
        if _error_code:
            job["error_code"] = _error_code
    job["finished_at"] = datetime.now(UTC).isoformat()
    job["batch_results"] = results
    job["batch_failed"] = failed
    ctx._jobs.set(job_id, job)  # تثبيت نتيجة الدفعة (Redis/ذاكرة)
    try:
        import raster_batch_observability

        raster_batch_observability.inc("jobs_completed_total" if results else "jobs_failed_total")
        raster_batch_observability.inc("indicator_success_total", len(results))
        raster_batch_observability.inc("indicator_failure_total", len(failed))
        raster_batch_observability.inc(
            "dataset_open_expected_total", 1 if job.get("single_open_certified") else 0
        )
    except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
        pass
    if (
        (not lease_lost)
        and durable_claim_key
        and durable_lease_token
        and durable_tenant_id
        and job.get("claim_backend") == "postgres"
    ):
        try:
            import raster_batch_job_store

            raster_batch_job_store.finish_sync(
                claim_key=durable_claim_key,
                tenant_id=durable_tenant_id,
                lease_token=durable_lease_token,
                status=str(
                    job["status"].value if hasattr(job["status"], "value") else job["status"]
                ),
                result_payload={
                    "batch_results": results,
                    "batch_failed": failed,
                    "single_open_certified": bool(job.get("single_open_certified")),
                    "shared_band_cache_entries": job.get("shared_band_cache_entries", 0),
                },
                error_code=job.get("error_code"),
            )
        except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
            ctx.logger.warning("batch %s durable terminal write failed", job_id)
        finally:
            try:
                import raster_batch_runtime_leases

                raster_batch_runtime_leases.pop_token(job_id)
            except Exception:  # noqa: BLE001 — كتابة إيجار/عدّاد best-effort لا تُسقِط المعالجة
                pass
    ctx.logger.info(
        "batch %s: %d نجح، %d فشل io_strategy=%s",
        job_id,
        len(results),
        len(failed),
        job.get("batch_io_strategy"),
    )
