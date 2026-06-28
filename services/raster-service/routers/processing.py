"""routers/processing.py — معالجة المؤشّرات غير المتزامنة (Process / Batch)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import main
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

router = APIRouter()


@router.post("/process")
async def process_raster(
    req: main.ProcessRequest, background_tasks: BackgroundTasks, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    """يبدأ معالجة مؤشّر (خلفيّة — لا يحجب الطلب). يُرجع job_id للاستعلام."""
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    j = {
        "job_id": job_id,
        "status": main.JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    main._jobs.set(job_id, j)
    # معالجة في الخلفيّة — لا تحجب الطلب (مهمّ لقلب النظام تحت الحمل).
    background_tasks.add_task(main._run_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
    }


@router.post("/process/batch")
async def process_batch(
    req: main.BatchProcessRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    بدل طلب لكلّ مؤشّر، طلب واحد يحسب NDVI+NDRE+NDSI+... من نفس المشهد. مفيد
    جدّاً للأتمتة (مشهد جديد → كلّ المؤشّرات دفعةً). خلفيّة، يُرجِع job_id.
    """
    main._require_service_token(x_agent_token)
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    job_id = f"batch_{uuid.uuid4().hex[:12]}"
    main._jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": main.JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "indicators": [i.value for i in req.indicators],
        },
    )
    background_tasks.add_task(main._run_batch_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": main.JobStatus.pending,
        "indicators": [i.value for i in req.indicators],
        "note": "استعلم /jobs/{job_id} — batch_results + batch_failed عند الاكتمال",
    }
