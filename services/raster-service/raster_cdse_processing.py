"""CDSE processing orchestration for raster-service.

Extracted from ``main.py`` as a conservative decomposition step.  The function
still receives the live application module as ``ctx`` so shared in-memory job
state, model classes, and compatibility wrappers remain the single source of
truth during the transition.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import scene_policy


def run_cdse_processing(ctx: Any, job_id: str, field_id: str, req: Any) -> None:
    """Compute CDSE indices and register each successful output as a raster layer.

    Each index is isolated: one failed CDSE request records a per-index failure
    instead of failing the whole job.  The persisted counter deliberately tracks
    DB persistence, not only processing completion, so job status remains honest.
    """
    import cdse_client

    job = ctx._jobs.get(job_id) or {"job_id": job_id}
    job["status"] = ctx.JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    ctx._jobs.set(job_id, job)

    dt_to = datetime.now(UTC)
    dt_from = dt_to - timedelta(days=max(int(req.lookback_days), 1))

    def _day_window(value: str | None) -> tuple[str, str] | None:
        if not value:
            return None
        day = str(value)[:10]
        if len(day) != 10:
            return None
        return f"{day}T00:00:00Z", f"{day}T23:59:59Z"

    explicit_from = req.date_from or req.date_to
    explicit_to = req.date_to or req.date_from
    if explicit_from or explicit_to:
        # Bare YYYY-MM-DD must mean the full acquisition day, not a zero-length
        # 00:00→00:00 interval. Zero-length timeRange can cause CDSE 400/empty
        # processing and can make the UI fall back to stale/latest tiles.
        from_day = str(explicit_from or explicit_to)[:10]
        to_day = str(explicit_to or explicit_from)[:10]
        if len(from_day) == 10 and len(to_day) == 10:
            time_from = f"{from_day}T00:00:00Z"
            time_to = f"{to_day}T23:59:59Z"
            capture_datetime = f"{to_day}T12:00:00Z"
        else:
            time_from = cdse_client._to_rfc3339(explicit_from or explicit_to)
            time_to = cdse_client._to_rfc3339(explicit_to or explicit_from)
            capture_datetime = time_to
        scene_id = f"cdse:{str(capture_datetime)[:10]}"
    else:
        # Search Catalog first to bind processing to a real acquisition date.
        # Without this, Process API may return a least-cloud mosaic from the
        # lookback window while we persist acquisition_date=time_to (today),
        # making available-dates and selected tile dates point at the wrong COG.
        time_from = dt_from.strftime("%Y-%m-%dT00:00:00Z")
        time_to = dt_to.strftime("%Y-%m-%dT23:59:59Z")
        capture_datetime = time_to
        scene_id = "cdse:latest"

    client = cdse_client.get_client()
    if not (explicit_from or explicit_to):
        try:
            scenes = client.search_scenes(
                bbox=req.bbox,
                time_from=time_from,
                time_to=time_to,
                max_cloud_pct=req.max_cloud_pct,
                limit=10,
                geometry=req.geometry,
            )
            ranked = (
                scene_policy.rank_scenes(scenes, max_cloud_pct=req.max_cloud_pct) if scenes else []
            )
            best = ranked[0] if ranked else None
            if best:
                capture_datetime = (
                    best.get("datetime") or best.get("properties", {}).get("datetime") or time_to
                )
                scene_id = (
                    best.get("item_id") or best.get("id") or f"cdse:{str(capture_datetime)[:10]}"
                )
                daywin = _day_window(capture_datetime)
                if daywin:
                    time_from, time_to = daywin
        except Exception as e:  # noqa: BLE001
            ctx.logger.warning("CDSE scene date binding skipped; using lookback window: %s", e)

    supported = cdse_client.supported_indices()
    results: dict[str, str] = {}
    failed: dict[str, str] = {}
    # v9-F1: «نجاح» المؤشّر لا يعني بالضرورة الحفظ في DB. نفصل الحفظ الفعليّ عن اكتمال
    # المعالجة كي لا يُعلن اللوج «5 نجح» بينما لم يُحفَظ أيّ صفّ في raster_assets.
    persisted_indices: dict[str, bool] = {}
    total = max(len(req.indicators), 1)
    for i, ind in enumerate(req.indicators):
        if ind not in supported:
            failed[ind] = "unsupported_index"
            continue
        try:
            tiff = client.process_index(
                index=ind,
                bbox=req.bbox,
                time_from=time_from,
                time_to=time_to,
                geometry=req.geometry,
                max_cloud_pct=req.max_cloud_pct,
            )
            if not tiff:
                failed[ind] = "empty_response"
                continue
            tif_path = os.path.join(ctx.UPLOAD_DIR, f"cdse_{ind}_{uuid.uuid4().hex[:8]}.tif")
            with open(tif_path, "wb") as fh:
                fh.write(tiff)
            preq = ctx.ProcessRequest(
                tenant_id=req.tenant_id or "",
                field_id=field_id,
                raster_url=tif_path,
                indicator=ctx.IndicatorKind(ind),
                source_format=ctx.SourceFormat.sentinel2_l2a,
                bands=ctx.BandMapping(),
                precomputed_index=True,
                provider="cdse",
                scene_id=f"{scene_id}:{ind}",
                capture_datetime=capture_datetime,
                clip_polygon_geojson=req.geometry,
                apply_cloud_mask=False,  # CDSE قنّع الغيوم خادميّاً (dataMask + maxCloudCoverage)
                geometry_revision=req.geometry_revision,  # v143: نَسَب الهندسة (المسار الافتراضيّ)
            )
            sub_job_id = f"{job_id}_{ind}"
            ctx._run_processing(sub_job_id, preq)
            sj = ctx._jobs.get(sub_job_id) or {}
            if sj.get("status") == ctx.JobStatus.completed:
                _sres = sj.get("result") or {}
                results[ind] = _sres.get("layer_id") or sub_job_id
                # v9-F1: نُسجّل هل حُفِظ الأصل في DB فعلاً (لا مجرّد اكتمال المعالجة).
                persisted_indices[ind] = bool(_sres.get("persisted") is True)
            else:
                failed[ind] = sj.get("error_message", "unknown")
        except cdse_client.CdseQuotaExhausted as e:
            # نفاد رصيد الحساب حالة نهائيّة: كلّ مؤشّر لاحق سيُرفَض بـ403 أيضاً. نتوقّف
            # فوراً ونُعلن السبب بوضوح (بدل طحن بقيّة المؤشّرات وإغراق السجلّ بالـ403).
            failed[ind] = "cdse_quota_exhausted"
            job["cdse_quota_exhausted"] = True
            job["cdse_error_reason"] = str(e)
            ctx.logger.warning("cdse %s: توقّف مبكّر — رصيد الحساب نفد (%s)", job_id, e)
            job["progress_pct"] = int((i + 1) / total * 100)
            ctx._jobs.set(job_id, job)
            break
        except Exception as e:  # noqa: BLE001 — عزل لكلّ مؤشّر (فشل CDSE → يُسجَّل)
            failed[ind] = type(e).__name__
        job["progress_pct"] = int((i + 1) / total * 100)
        ctx._jobs.set(job_id, job)

    job["status"] = ctx.JobStatus.completed if results else ctx.JobStatus.failed
    job["finished_at"] = datetime.now(UTC).isoformat()
    job["provider"] = "cdse"
    job["cdse_results"] = results
    job["cdse_failed"] = failed
    # v9-F1: صدق الحفظ — العدّاد الحقيقيّ هو ما حُفِظ في DB لا ما اكتملت معالجته.
    _persisted_count = sum(1 for v in persisted_indices.values() if v)
    job["cdse_persisted"] = persisted_indices
    job["cdse_persisted_count"] = _persisted_count
    ctx._jobs.set(job_id, job)
    ctx.logger.info(
        "cdse %s: %d اكتمل (%d محفوظ في DB)، %d فشل",
        job_id,
        len(results),
        _persisted_count,
        len(failed),
    )
