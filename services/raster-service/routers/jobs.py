"""routers/jobs.py — حالة المهامّ ونتائجها (Jobs).

Phase 13: this router no longer imports ``main``. It consumes the extracted
runtime state, security helpers, and API models directly while preserving the
same endpoints and response contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from raster_api_models import JobStatus
from raster_runtime_state import JOBS
from raster_security_context import require_job_tenant, require_service_token

router = APIRouter()


def _cdse_outcomes(job: dict) -> dict:
    """CDSE parents store per-index results, including partially successful batches."""
    if job.get("provider") != "cdse":
        return {}
    fields = ("cdse_results", "cdse_failed", "cdse_persisted", "cdse_persisted_count")
    return {key: job[key] for key in fields if key in job}


@router.get("/v1/jobs/{job_id}")
async def job_status(job_id: str, x_agent_token: str = Header(None)):
    """حالة المهمّة."""
    require_service_token(x_agent_token)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    # P3-AUTH: التوكن المشترك يُثبت أنّ المستدعي خدمة، لا لأيّ مستأجِر يعمل.
    require_job_tenant(j)
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
        **_cdse_outcomes(j),
    }


@router.get("/v1/jobs/{job_id}/result")
async def job_result(job_id: str, x_agent_token: str = Header(None)):
    """نتيجة المهمّة (بعد الاكتمال)."""
    require_service_token(x_agent_token)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    require_job_tenant(j)
    if j["status"] != JobStatus.completed:
        raise HTTPException(409, f"المهمّة غير مكتملة (الحالة: {j['status']})")
    if "result" in j:
        return j["result"]
    outcomes = _cdse_outcomes(j)
    if outcomes:
        return outcomes
    raise HTTPException(409, "بيانات نتيجة المهمّة غير متاحة")
