"""routers/processing.py — معالجة المؤشّرات غير المتزامنة (Process / Batch)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة تُستورد من الوحدات المفككة مباشرة؛ يمنع الحارس رجوع الراوترات إلى ``main``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import indicator_batch_claim
import raster_api_models as api_models
import raster_batch_observability
import raster_processing_runtime
import raster_runtime_state
import raster_security_context
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

router = APIRouter()


@router.post("/process")
async def process_raster(
    req: api_models.ProcessRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    raster_security_context.require_service_token(x_agent_token)
    """يبدأ معالجة مؤشّر (خلفيّة — لا يحجب الطلب). يُرجع job_id للاستعلام."""
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    j = {
        "job_id": job_id,
        "status": api_models.JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    raster_runtime_state.JOBS.set(job_id, j)
    # معالجة في الخلفيّة — لا تحجب الطلب (مهمّ لقلب النظام تحت الحمل).
    background_tasks.add_task(raster_processing_runtime.run_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
    }


@router.post("/raw/process")
async def process_raw_data(
    req: api_models.RawDataProcessRequest,
    x_agent_token: str = Header(None),
):
    """يفحص الراستر الخام ويعيد metadata + إحصاءات النطاقات بلا حساب مؤشرات.

    هذا مسار QA/provenance للبيانات الخام قبل أي NDVI/EVI/...؛ لا يصنع مؤشراً
    زراعياً ولا يحفظ نتيجة كأنها طبقة مؤشر.
    """
    raster_security_context.require_service_token(x_agent_token)
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب لمعالجة البيانات الخام")
    try:
        return raster_processing_runtime.process_raw_raster(req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/process/batch")
async def process_batch(
    req: api_models.BatchProcessRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    بدل طلب لكلّ مؤشّر، طلب واحد يحسب NDVI+NDRE+NDSI+... من نفس المشهد. مفيد
    جدّاً للأتمتة (مشهد جديد → كلّ المؤشّرات دفعةً). خلفيّة، يُرجِع job_id.
    """
    raster_security_context.require_service_token(x_agent_token)
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    claim_key = indicator_batch_claim.batch_claim_key(req)
    proposed_job_id = f"batch_{claim_key[4:16]}"
    claim = indicator_batch_claim.BATCH_CLAIMS.claim(claim_key, proposed_job_id)
    job_id = claim.job_id
    if not claim.acquired:
        raster_batch_observability.inc("claims_deduplicated_total")
        existing = raster_runtime_state.JOBS.get(job_id) or {}
        return {
            "job_id": job_id,
            "status": existing.get("status", api_models.JobStatus.pending),
            "indicators": [i.value for i in req.indicators],
            "deduplicated": True,
            "claim_backend": claim.backend,
            "note": "طلب مطابق قيد المعالجة أو مكتمل؛ أُعيد job_id السلطوي نفسه",
        }
    raster_batch_observability.inc("claims_acquired_total")
    raster_runtime_state.JOBS.set(
        job_id,
        {
            "job_id": job_id,
            "status": api_models.JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "indicators": [i.value for i in req.indicators],
            "batch_claim_key": claim_key,
            "claim_backend": claim.backend,
        },
    )
    background_tasks.add_task(raster_processing_runtime.run_batch_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": api_models.JobStatus.pending,
        "indicators": [i.value for i in req.indicators],
        "deduplicated": False,
        "claim_backend": claim.backend,
        "note": "استعلم /jobs/{job_id} — batch_results + batch_failed عند الاكتمال",
    }
