"""اختبارات نقطة /api/v1/automation/runs — تسجيل المسار + شكل المخرجات النقيّ.

نُفضّل فحص المنطق النقيّ (LEDGER) لأنّه في الذاكرة بلا قاعدة، ونؤكّد أنّ المسار
مُسجّل فعليّاً على التطبيق (يتطلّب fastapi — يُتخطّى بأمان لو غاب).
"""

import pytest
from core.automation_ledger import LEDGER


def test_route_registered_on_app():
    """المسار /api/v1/automation/runs مُسجّل فعليّاً وقت التشغيل (لا grep على المصدر)."""
    pytest.importorskip("fastapi")
    from api.main import app

    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    assert "/api/v1/automation/runs" in paths


def test_route_is_get():
    pytest.importorskip("fastapi")
    from api.main import app
    from fastapi.routing import APIRoute

    runs = [
        r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/v1/automation/runs"
    ]
    assert runs, "المسار غير مُسجّل كـAPIRoute"
    assert "GET" in runs[0].methods


def test_endpoint_payload_shape_via_pure_ledger():
    """شكل حمولة النقطة = {runs, summary} — يُبنى من LEDGER النقيّ مباشرةً."""
    LEDGER.clear()
    rec = LEDGER.start_run("alerts_evaluation", 2)
    rec.mark_evaluated()
    rec.mark_errored("fld_x", "503")
    rec.add_alerts(1)
    rec.finish()

    payload = {"runs": LEDGER.recent(), "summary": LEDGER.summary()}
    assert isinstance(payload["runs"], list)
    assert payload["runs"][0]["task_name"] == "alerts_evaluation"
    assert payload["runs"][0]["status"] == "partial"
    assert payload["summary"]["total_runs"] == 1
    assert payload["summary"]["totals"]["alerts_created"] == 1
    LEDGER.clear()
