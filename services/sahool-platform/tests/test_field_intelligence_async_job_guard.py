from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "api" / "routers" / "field_intelligence.py"
FRONTEND_API = ROOT.parents[1] / "frontend" / "src" / "services" / "api.ts"
FRONTEND_PAGE = ROOT.parents[1] / "frontend" / "src" / "sections" / "FieldIntelligencePage.tsx"


def test_field_intelligence_analyze_starts_async_job_not_sync_result():
    src = ROUTER.read_text(encoding="utf-8")
    assert (
        '@router.post("/api/v1/field-intelligence/analyze", status_code=status.HTTP_202_ACCEPTED)'
        in src
    )
    assert "background_tasks.add_task(" in src
    assert 'job_id = f"fia_' in src
    assert "return _job_public" in src
    # The public POST must not call the heavy coordinator directly anymore.
    public_route = src.split(
        '@router.post("/api/v1/field-intelligence/analyze", status_code=status.HTTP_202_ACCEPTED)',
        1,
    )[1]
    public_route = public_route.split(
        '@router.get("/api/v1/field-intelligence/analyze/jobs/{job_id}")', 1
    )[0]
    assert "run_field_intelligence(req" not in public_route
    assert "await _compute_field_intelligence_response" not in public_route


def test_field_intelligence_job_status_and_cancel_contract_exist():
    src = ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/api/v1/field-intelligence/analyze/jobs/{job_id}")' in src
    assert '@router.post("/api/v1/field-intelligence/analyze/jobs/{job_id}/cancel")' in src
    assert "progress" in src
    assert "stage" in src
    assert "cancel_requested" in src
    assert "completed" in src
    assert "failed" in src
    assert "cancelled" in src


def test_frontend_uses_job_polling_for_field_intelligence():
    api = FRONTEND_API.read_text(encoding="utf-8")
    page = FRONTEND_PAGE.read_text(encoding="utf-8")
    assert "startAnalyzeFieldIntelligence" in api
    assert "getFieldIntelligenceJob" in api
    assert "cancelFieldIntelligenceJob" in api
    assert "useStartFieldIntelligenceJob" in page
    assert "useFieldIntelligenceJob" in page
    assert "جاري تحليل الحقل في الخلفية" in page
    assert "إلغاء التحليل" in page
