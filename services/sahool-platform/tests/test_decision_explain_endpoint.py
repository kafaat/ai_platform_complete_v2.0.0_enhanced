"""اختبار نقطة شرح/إعادة تشغيل القرار (routers/decision_explain) — توصيل + 404 مرن.

يثبت دون قاعدة (مسار القراءة نفسه تكامليّ، يتطلّب Postgres — كـdecision_dispatch):
  • التوصيل: النقطة مُضمَّنة في التطبيق بفعل GET.
  • الإغلاق المرن: العلم المُطفأ ⇒ 404 (قبل لمس القاعدة).
  • العلم المُفعَّل يتجاوز حاجز الـ404 (يصل لمسار القراءة — مُختبَر تكامليّاً، لا هنا).

الصدق: لا يدّعي اختبار قراءة DB هنا (لا Postgres في الوحدة)؛ منطق الشرح مُختبَر
وحدويّاً في tests_v9/test_decision_explain.py. مسار القراءة يطبّقه CI Integration.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.decision_explain import _decision_studio_enabled, explain_decision_endpoint
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-explain",
    tenant_id="00000000-0000-0000-0000-000000000003",
    role=UserRole.OWNER,
    name_ar="شرح",
)


def test_explain_endpoint_wired():
    """نقطة الشرح مُضمَّنة في التطبيق بفعلها الصحيح (GET)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/decision/{decision_id}/explain", "GET") in routes


async def test_flag_off_returns_404(monkeypatch):
    """الإغلاق المرن: العلم المُطفأ ⇒ 404 (قبل لمس القاعدة)."""
    monkeypatch.delenv("FEATURE_DECISION_STUDIO", raising=False)
    assert _decision_studio_enabled() is False
    with pytest.raises(HTTPException) as e:
        await explain_decision_endpoint(decision_id="dec_x", user=_USER)
    assert e.value.status_code == 404


def test_flag_on_recognized(monkeypatch):
    """العلم المُفعَّل يُقرأ صحيحاً (يتجاوز حاجز الـ404؛ القراءة تكامليّة)."""
    monkeypatch.setenv("FEATURE_DECISION_STUDIO", "true")
    assert _decision_studio_enabled() is True
