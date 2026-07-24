"""سجلّ القدرات (P1-9) — القدرات المشروطة للـAI (حدود الحقل + AquaCrop) مُدرَجة وصادقة.

يؤكّد أنّ السجلّ يعكس البوّابات الحقيقيّة (env)، وأنّ الحالة تتبع المتغيّرات، ولا يُدرِج قدرةً
غير مشروطة (productivity_zones الحتميّة دائماً).
"""

import pytest
from core.capabilities import (
    all_capabilities,
    aquacrop_salinity_active,
    capabilities_report,
    dependency_status,
    ml_field_boundary_active,
)

pytestmark = pytest.mark.unit


def _keys():
    return {c.key for c in all_capabilities()}


def test_ai_fallback_capabilities_registered():
    keys = _keys()
    assert "ml_field_boundary" in keys
    assert "aquacrop_salinity" in keys
    # لا تُدرَج القدرة غير المشروطة (مناطق الإنتاجيّة حتميّة دائماً — ليست مؤجَّلة).
    assert "productivity_zones" not in keys


def test_field_boundary_gate_follows_env(monkeypatch):
    monkeypatch.delenv("SAHOOL_FIELD_BOUNDARY_BACKEND", raising=False)
    monkeypatch.delenv("SAHOOL_FTW_WEIGHTS", raising=False)
    assert ml_field_boundary_active() is False  # الافتراض الحتميّ ⇒ غير مُفعَّل
    monkeypatch.setenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "ftw")
    assert ml_field_boundary_active() is False  # backend حقيقيّ بلا أوزان ⇒ لا يزال معطَّلاً
    monkeypatch.setenv("SAHOOL_FTW_WEIGHTS", "/models/ftw.onnx")
    assert ml_field_boundary_active() is True  # backend + أوزان ⇒ مُفعَّل


def test_aquacrop_gate_follows_env(monkeypatch):
    monkeypatch.delenv("AQUACROP_ENABLED", raising=False)
    assert aquacrop_salinity_active() is False
    monkeypatch.setenv("AQUACROP_ENABLED", "1")
    assert aquacrop_salinity_active() is True


def test_capability_active_matches_gate(monkeypatch):
    monkeypatch.setenv("AQUACROP_ENABLED", "1")
    caps = {c.key: c for c in all_capabilities()}
    assert caps["aquacrop_salinity"].active is True  # الحالة تتبع البوّابة لا قيمة ثابتة


def test_dependency_status_reflects_env(monkeypatch):
    # P1-16: تهيئة التبعيّات الاختياريّة مرئيّة (لا انحدار صامت).
    monkeypatch.delenv("DECISION_SERVICE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://x:6379/0")
    deps = dependency_status()
    assert deps["decision_service"]["configured"] is False
    assert deps["redis"]["configured"] is True
    # كلّ تبعيّة تحمل اسم env الفعليّ + سلوك التدهور الصريح (لا انحدار صامت).
    for d in deps.values():
        assert d["env"] and d["degraded_behavior_ar"]


def test_capabilities_report_surfaces_dependencies():
    rep = capabilities_report()
    assert "dependencies" in rep
    # raster مُستبعَد عمداً (عنوانه يُقرأ حصراً داخل الواجهة القانونيّة — حارس الحدّ P2.5).
    assert set(rep["dependencies"]) == {"decision_service", "weather_service", "redis"}
