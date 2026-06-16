"""اختبارات سلوكيّة لتسجيل المسارات وقت التشغيل (فجوة A2) — مجموعة المنصّة.

تُحمّل التطبيق الكامل (api.main.app) وتفحص app.routes الفعليّة — بديل سلوكيّ للحارس
البنيويّ الذي يفحص نصّ المصدر (grep على "/api/v1"). الفرق: الحارس البنيويّ يمرّ حتى
لو سُجّل الراوتر بخطأ أو استُبعد include_router؛ هذا يفحص الحالة الحقيقيّة وقت التشغيل.

في مجموعة المنصّة لأنّها تتطلّب fastapi (وظيفة Unit Tests ببيئة دنيا بلا fastapi).
"""

from api.main import app


def _api_v1_paths() -> set[str]:
    """مجموعة مسارات /api/v1/* المُسجّلة فعليّاً على التطبيق وقت التشغيل."""
    return {
        r.path
        for r in app.routes
        if isinstance(getattr(r, "path", None), str) and r.path.startswith("/api/v1")
    }


def test_app_imports_and_titled():
    """التطبيق يُحمّل فعليّاً دون أخطاء استيراد/تسجيل راوتر (نجاح الاستيراد = include_router نُفّذ)."""
    assert app is not None
    assert app.title == "SAHOOL Core API"


def test_api_v1_routes_registered_at_runtime():
    """عدد مسارات /api/v1/* المُسجّلة فعليّاً معقول (الحالة الفعليّة، لا grep).

    grep على "/api/v1" في main.py قد يمرّ بينما لا يُسجَّل أيّ مسار (راوترات منقولة
    لم تُضَمّ). سلوكيّاً نفحص app.routes نفسها.
    """
    paths = _api_v1_paths()
    assert len(paths) >= 20, f"عدد مسارات /api/v1 منخفض بشكل مريب: {len(paths)}"


def test_expected_api_v1_endpoints_present_at_runtime():
    """نقاط متوقّعة موجودة فعلاً في app.routes (لا فحص نصّ المصدر).

    /api/v1/fields أساسيّة و/api/v1/harvest-lots حديثة (تتبّع supply-chain v65).
    غيابهما رغم وجود الكود يدلّ على عدم ضمّ الراوتر — لا يمسكه grep على المصدر.
    """
    paths = _api_v1_paths()
    for expected in ("/api/v1/fields", "/api/v1/harvest-lots"):
        assert expected in paths, f"المسار المتوقّع {expected} غير مُسجّل وقت التشغيل"


def test_api_v1_routes_have_http_methods():
    """كلّ مسار /api/v1/* مُسجّل بطريقة HTTP فعليّة (راوتر مضموم بلا طرق = نقطة ميّتة)."""
    from fastapi.routing import APIRoute

    api_routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1")]
    assert api_routes, "لا APIRoute فعليّة تحت /api/v1"
    for r in api_routes:
        assert r.methods, f"المسار {r.path} بلا طرق HTTP"
