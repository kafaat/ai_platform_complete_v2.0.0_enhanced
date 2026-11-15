"""A completed CDSE parent stores per-index outcomes under native keys."""

import pytest
from fastapi import HTTPException
from raster_api_models import JobStatus
from routers import jobs

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_cdse_job_exposes_partial_results_and_failed_indices(monkeypatch):
    record = {
        "provider": "cdse",
        "status": JobStatus.completed,
        "progress_pct": 100,
        "created_at": "2024-02-26T10:00:00Z",
        "cdse_results": {"ndvi": "layer_1"},
        "cdse_failed": {"msi": "empty_response"},
        "cdse_persisted": {"ndvi": True},
        "cdse_persisted_count": 1,
    }
    monkeypatch.setattr(jobs, "JOBS", {"test": record})
    monkeypatch.setattr(jobs, "require_service_token", lambda token: None)
    expected = {key: value for key, value in record.items() if key.startswith("cdse_")}
    assert await jobs.job_result("test", "test") == expected
    status = await jobs.job_status("test", "test")
    for key, value in expected.items():
        assert status[key] == value
    record["status"] = JobStatus.failed
    with pytest.raises(HTTPException) as error:
        await jobs.job_result("test", "test")
    assert error.value.status_code == 409
    status = await jobs.job_status("test", "test")
    assert status["cdse_failed"] == {"msi": "empty_response"}
