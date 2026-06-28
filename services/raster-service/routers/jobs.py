"""routers/jobs.py — حالة المهامّ ونتائجها (Jobs)
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


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, x_agent_token: str = Header(None)):
    """حالة المهمّة."""
    main._require_service_token(x_agent_token)
    j = main._jobs.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
    }


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: str, x_agent_token: str = Header(None)):
    """نتيجة المهمّة (بعد الاكتمال)."""
    main._require_service_token(x_agent_token)
    j = main._jobs.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    if j["status"] != main.JobStatus.completed:
        raise HTTPException(409, f"المهمّة غير مكتملة (الحالة: {j['status']})")
    return j["result"]
