"""routers/jobs.py — حالة المهامّ ونتائجها (Jobs).

Phase 13: this router no longer imports ``main``. It consumes the extracted
runtime state, security helpers, and API models directly while preserving the
same endpoints and response contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from raster_api_models import JobStatus
from raster_runtime_state import JOBS
from raster_security_context import require_service_token

router = APIRouter()


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, x_agent_token: str = Header(None)):
    """حالة المهمّة."""
    require_service_token(x_agent_token)
    j = JOBS.get(job_id)
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
    require_service_token(x_agent_token)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    if j["status"] != JobStatus.completed:
        raise HTTPException(409, f"المهمّة غير مكتملة (الحالة: {j['status']})")
    return j["result"]
