"""سجلّ القدرات (P1-9) — القدرات المشروطة للـAI (حدود الحقل + AquaCrop) مُدرَجة وصادقة.

يؤكّد أنّ السجلّ يعكس البوّابات الحقيقيّة (env)، وأنّ الحالة تتبع المتغيّرات، ولا يُدرِج قدرةً
غير مشروطة (productivity_zones الحتميّة دائماً).
"""

import pytest
from core.capabilities import all_capabilities, aquacrop_salinity_active, ml_field_boundary_active

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
