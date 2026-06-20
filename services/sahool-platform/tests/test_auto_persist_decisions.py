"""اختبار إدامة القرار التلقائيّة عند المصدر (auto-persist decisions، مقدّمة السلسلة).

نقاط القرار (crop-twin/decision، profit-aware، irrigation-plan) تُدِيم القرار تلقائيّاً
خلف علم تشغيليّ (SAHOOL_AUTO_PERSIST_DECISIONS) — فيُلتقَط كلّ قرار في سلسلة النَّسَب بلا
نداء /decision/record منفصل. هنا نتحقّق من المنطق الحتميّ القابل للاختبار بلا قاعدة:
تحليل العلم، قِصَر الدائرة عند الإطفاء (بلا أيّ مسّ بالقاعدة)، وبقاء النقاط مُوصَّلة async.
مسار الكتابة نفسه تكامليّ (يتطلّب Postgres) كـdecision_dispatch.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.routers.decision_record import _auto_persist_enabled, persist_decision_if_enabled
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-ap",
    tenant_id="00000000-0000-0000-0000-000000000003",
    role=UserRole.OWNER,
    name_ar="إدامة",
)


def test_flag_off_by_default(monkeypatch):
    """افتراضاً مُطفأ (إنضاج تدريجيّ) — لا إدامة بلا تفعيل صريح."""
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    assert _auto_persist_enabled() is False


def test_flag_parsing_truthy_and_falsy(monkeypatch):
    """تحليل العلم: 1/true/yes/on ⇒ مُفعَّل؛ غيرها (0/false/فارغ) ⇒ مُطفأ."""
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("SAHOOL_AUTO_PERSIST_DECISIONS", v)
        assert _auto_persist_enabled() is True
    for v in ("0", "false", "", "maybe"):
        monkeypatch.setenv("SAHOOL_AUTO_PERSIST_DECISIONS", v)
        assert _auto_persist_enabled() is False


async def test_persist_is_noop_when_flag_off(monkeypatch):
    """العلم مُطفأ ⇒ يعيد False بقِصَر دائرة دون أيّ مسّ بالقاعدة (آمن في الوحدة)."""
    monkeypatch.delenv("SAHOOL_AUTO_PERSIST_DECISIONS", raising=False)
    ok = await persist_decision_if_enabled(
        _USER,
        decision_id="dec_noop",
        decision_type="crop_twin",
        decision_value={"a": 1},
    )
    assert ok is False


def test_decision_endpoints_still_wired_async():
    """النقاط الثلاث ما زالت مُوصَّلة بنفس المسارات (POST) بعد تحويلها لأغلفة async."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/crop-twin/decision", "POST") in routes
    assert ("/api/v1/crop-twin/decision/profit-aware", "POST") in routes
    assert ("/api/v1/irrigation-plan", "POST") in routes
