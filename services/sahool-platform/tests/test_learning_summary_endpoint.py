"""اختبار نقطة تلخيص حلقة التعلّم (routers/learning_summary) — توصيل + 404 مرن.

يثبت دون قاعدة (مسار القراءة نفسه تكامليّ، يتطلّب Postgres — كـdecision_dispatch):
  • التوصيل: النقطة مُضمَّنة في التطبيق بفعل GET.
  • الإغلاق المرن: العلم المُطفأ ⇒ 404 (قبل لمس القاعدة).
  • العلم المُفعَّل يتجاوز حاجز الـ404 (يصل لمسار القراءة — مُختبَر تكامليّاً، لا هنا).

الصدق: لا يدّعي اختبار قراءة DB هنا (لا Postgres في الوحدة)؛ منطق التجميع مُختبَر
وحدويّاً في tests_v9/test_learning_summary.py. مسار القراءة يطبّقه CI Integration.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.learning_summary import _learning_dashboard_enabled, get_learning_summary
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-learn",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="تعلّم",
)


def test_summary_endpoint_wired():
    """نقطة التلخيص مُضمَّنة في التطبيق بفعلها الصحيح (GET)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/learning/summary", "GET") in routes


async def test_flag_off_returns_404(monkeypatch):
    """الإغلاق المرن: العلم المُطفأ ⇒ 404 (قبل لمس القاعدة)."""
    monkeypatch.delenv("FEATURE_LEARNING_DASHBOARD", raising=False)
    assert _learning_dashboard_enabled() is False
    with pytest.raises(HTTPException) as e:
        await get_learning_summary(user=_USER)
    assert e.value.status_code == 404


def test_flag_on_recognized(monkeypatch):
    """العلم المُفعَّل يُقرأ صحيحاً (يتجاوز حاجز الـ404؛ القراءة تكامليّة)."""
    monkeypatch.setenv("FEATURE_LEARNING_DASHBOARD", "true")
    assert _learning_dashboard_enabled() is True


def test_optional_reads_run_inside_savepoints():
    """Copilot على #1001: جدولٌ اختياريّ غائب كان يُفسِد المعاملة الخارجيّة فيعود 503 رغم الالتقاط.

    كلُّ قراءة اختياريّة (recommendation_outcomes/dispatch_decisions هنا، والقراءاتُ الستّ
    التكميليّة في حالة الحقل-الموسم: المؤشّرات · عجز الماء · المهام · outcome_record ·
    التوصيات · الربط) تجري داخل ``async with conn.transaction()`` — نقطةُ حفظ تُرتَدّ
    وحدَها — والالتقاطُ خارجها.
    """
    import re
    from pathlib import Path

    routers = Path(__file__).resolve().parents[1] / "api" / "routers"
    summary = (routers / "learning_summary.py").read_text(encoding="utf-8")
    body = summary.split("async def get_learning_summary(", 1)[1]
    # كلُّ `try:` اختياريّ يتبعه مباشرةً `async with conn.transaction():` (نقطة حفظ).
    tries = re.findall(r"try:\n\s+(\S[^\n]*)", body)
    assert len(tries) >= 2
    assert all(t.startswith("async with conn.transaction():") for t in tries[1:]), tries
    seasons = (routers / "seasons.py").read_text(encoding="utf-8")
    state = seasons.split("assemble_field_season_state\n", 1)[1]
    inner = re.findall(r"            try:\n\s+(\S[^\n]*)", state)
    assert len(inner) == 6, inner
    assert all(t.startswith("async with conn.transaction():") for t in inner), inner
