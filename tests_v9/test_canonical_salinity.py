"""اختبار الملوحة الكنسيّة (H5-residual) — ربط الملوحة بكتلة المياه خلف feature flag.

يقفل: OFF افتراضيّاً (الملوحة قرار إدخال، تُعلَن التعطيل صراحةً)؛ ON + تحليل EC موثوق ⇒
applied (قرار من جودة البيانات، إعادة استخدام salinity_decision/salinity_stress_ks لا تكرار)؛
ON + لا EC ⇒ needs_data؛ fail-safe (لا رمي على نقص). يُختبَر مباشرةً على dict فارغ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.field_state_projection import _apply_canonical_salinity
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_off_by_default_declares_disabled(monkeypatch):
    """OFF افتراضيّ (بلا env): EC موجود لكن لا يُفعَّل — يُعلن التعطيل صراحةً (H5)."""
    monkeypatch.delenv("FEATURE_CANONICAL_SALINITY", raising=False)
    water: dict = {}
    _apply_canonical_salinity(
        water,
        soil_ec=4.0,
        salinity_class="high",
        crop_id="tomato",
        analysis_age_days=30,
        confidence=0.9,
    )
    sal = water["salinity"]
    assert sal["applied"] is False
    assert "معطّل افتراضيّاً" in sal["reason_ar"]
    assert sal["salinity_class"] == "high"
    assert sal["source"] == "field_state.canonical"


def test_on_with_reliable_analysis_applies(monkeypatch):
    """ON + تحليل موثوق (EC عالٍ + عمر حديث + ثقة كافية) ⇒ applied=True."""
    monkeypatch.setenv("FEATURE_CANONICAL_SALINITY", "1")
    water: dict = {}
    _apply_canonical_salinity(
        water,
        soil_ec=3.5,
        salinity_class="high",
        crop_id="tomato",
        analysis_age_days=30,
        confidence=0.9,
    )
    sal = water["salinity"]
    assert sal["applied"] is True
    assert sal["leaching_requirement"] is None  # ECw غير مُدخَل ⇒ الغسيل غير محسوب
    assert "ks" in sal  # Ks فعليّة أو None معلَناً (لا اختلاق)
    assert sal["source"] == "field_state.canonical"


def test_on_without_ec_is_needs_data(monkeypatch):
    """ON + لا EC ⇒ غير applied (needs_data) دون رمي استثناء."""
    monkeypatch.setenv("FEATURE_CANONICAL_SALINITY", "1")
    water: dict = {}
    _apply_canonical_salinity(
        water,
        soil_ec=None,
        salinity_class=None,
        crop_id="tomato",
        analysis_age_days=None,
        confidence=None,
    )
    sal = water["salinity"]
    assert sal["applied"] is False
    assert "لا تحليل ملوحة موثوق" in sal["reason_ar"]


def test_on_with_stale_analysis_not_applied(monkeypatch):
    """ON + EC موجود لكن تحليل قديم/منخفض الثقة ⇒ غير applied + سبب من القرار."""
    monkeypatch.setenv("FEATURE_CANONICAL_SALINITY", "1")
    water: dict = {}
    _apply_canonical_salinity(
        water,
        soil_ec=4.0,
        salinity_class="high",
        crop_id="tomato",
        analysis_age_days=500,  # قديم (≥365)
        confidence=0.5,  # ثقة منخفضة
    )
    sal = water["salinity"]
    assert sal["applied"] is False
    assert "signals" in sal


def test_fail_safe_no_raise_on_missing(monkeypatch):
    """fail-safe: soil_ec=None لا يرمي (OFF أو ON)."""
    monkeypatch.delenv("FEATURE_CANONICAL_SALINITY", raising=False)
    water: dict = {}
    _apply_canonical_salinity(
        water,
        soil_ec=None,
        salinity_class=None,
        crop_id=None,
        analysis_age_days=None,
    )
    assert water["salinity"]["applied"] is False
