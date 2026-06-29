"""عقد «مساحة عمل الموسم» (Season Workspace) — نموذج قراءة موحّد لرحلة الحقل.

النقطة ``GET /api/v1/fields/{id}/season-workspace`` تجمع ملفّ الحقل + الموسم + جاهزيّة
البيانات + الحالة الموحّدة + التوصيات + المهامّ + الأنشطة + الإجراءات التالية في حمولة
واحدة صادقة (الفجوات تُبلَّغ في ``gaps``). هذه الاختبارات تثبّت:
  • المنطق النقيّ للجاهزيّة (``_readiness``) ومستوياتها (insufficient/partial/ready).
  • تجميع/ترتيب الإجراءات التالية (``_next_actions``) مع السقف.
  • تعاقُد البنية: النقطة مُسجَّلة وتتطلّب صلاحيّة عرض الحقل (لا وصول مجهول).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")


def _load_module():
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    pytest.importorskip("fastapi")
    try:
        import api.routers.season_workspace as sw
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محلّيّاً (asyncpg…)
        pytest.skip(f"platform deps missing: {e}")
    return sw


def test_readiness_insufficient_when_empty():
    """حقل بلا حدود/موقع/محصول/موسم/EC/حالة ⇒ نقص حادّ (insufficient)."""
    sw = _load_module()
    r = sw._readiness(field={}, season=None, soil_tests=[], state=None)
    assert r["level"] == "insufficient"
    assert r["score"] < 60
    # فحص EC التربة إلزاميّ وغير محقَّق (المفتاح soil_ec).
    assert any(c["key"] == "soil_ec" and not c["ok"] for c in r["checks"])
    assert r["missing"], "يجب أن تُذكَر العناصر الناقصة"


def test_readiness_ready_when_complete():
    """كلّ الإلزاميّ (حدود/موقع/محصول/موسم/زراعة/EC/حالة) + اختياريّ ⇒ جاهز (ready)."""
    sw = _load_module()
    # _latest_published_soil يقرأ result المتداخل لاختبار منشور.
    soil = [
        {
            "status": "published",
            "result": {
                "ec_ds_m": 2.1,
                "water_ec_ds_m": 1.3,
                "ph": 7.2,
                "n_ppm": 20,
                "p_ppm": 10,
                "k_ppm": 180,
            },
        }
    ]
    r = sw._readiness(
        field={"geometry": {"type": "Polygon"}, "lat": 15.3, "lon": 44.2, "crop": "wheat"},
        season={"season_id": "s1", "sowing_date": "2026-01-01", "target_yield_kg_ha": 5000},
        soil_tests=soil,
        state={"validity": "valid"},
    )
    assert r["level"] == "ready", r
    assert r["score"] >= 85


def test_readiness_score_monotonic_with_data():
    """إضافة بيانات لا تُنقص النقاط (اتّساق التهديف)."""
    sw = _load_module()
    empty = sw._readiness(field={}, season=None, soil_tests=[], state=None)["score"]
    partial = sw._readiness(
        field={}, season={"season_id": "s"}, soil_tests=[{"ec_ds_m": 2.0}], state=None
    )["score"]
    assert partial >= empty


def test_next_actions_prioritizes_and_caps():
    """الإجراءات تُرتَّب بالأولويّة (1 أوّلاً) وتُحَدّ بسقف 8."""
    sw = _load_module()
    readiness = {
        "missing": [
            {"key": "ec", "label_ar": "EC", "action_ar": "أضف EC", "required": True},
            {"key": "npk", "label_ar": "N/P/K", "action_ar": "أضف", "required": False},
        ]
    }
    recs = {"recommendations": [{"priority": 1, "title_ar": "ريّ"}], "requires_review": True}
    tasks = [{"task_id": f"t{i}", "priority": 2, "notes": "مهمة"} for i in range(10)]
    actions = sw._next_actions(readiness, recs, tasks)
    assert len(actions) <= 8
    prios = [a["priority"] for a in actions]
    assert prios == sorted(prios), "غير مرتّبة بالأولويّة"
    # فجوة بيانات إلزاميّة (priority 1) تتصدّر.
    assert actions[0]["type"] in {"data_gap", "recommendation"}


def test_next_actions_empty_inputs():
    """مدخلات فارغة ⇒ قائمة فارغة (لا تلفيق إجراءات)."""
    sw = _load_module()
    assert sw._next_actions({"missing": []}, None, []) == []


def test_endpoint_registered_and_requires_field_view():
    """تعاقُد البنية: النقطة مُعرَّفة على راوتر الوحدة (تُكتشَف تلقائيّاً عبر iter_modules)
    وتتطلّب صلاحيّة FIELD_VIEW (لا وصول مجهول)."""
    sw = _load_module()

    # راوتر الوحدة هو مصدر الحقيقة للمسار (register_routers يضمّ أيّ وحدة تحمل `router`)؛
    # فحصه حتميّ بصرف النظر عن ترتيب استيراد api.main في جلسة pytest.
    paths = {getattr(r, "path", None) for r in sw.router.routes}
    assert "/api/v1/fields/{field_id}/season-workspace" in paths, "النقطة غير مُعرَّفة على الراوتر"
    methods = {
        meth
        for r in sw.router.routes
        if getattr(r, "path", None) == "/api/v1/fields/{field_id}/season-workspace"
        for meth in (getattr(r, "methods", set()) or set())
    }
    assert "GET" in methods
    # المصدر يفرض صلاحيّة العرض عبر require_permission(FIELD_VIEW) — لا اعتماد على عميل.
    src = open(
        os.path.join(_CORE, "api", "routers", "season_workspace.py"), encoding="utf-8"
    ).read()
    assert "require_permission(Permission.FIELD_VIEW)" in src
    assert "tenant_connection(user)" in src  # عزل RLS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
