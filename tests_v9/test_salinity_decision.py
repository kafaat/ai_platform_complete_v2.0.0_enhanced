"""اختبار وحدة لسياسة قرار تفعيل الملوحة (``core.salinity_policy``) — نقيّ بلا api/قاعدة.

يُكمل H5: الملوحة مُطفأة افتراضيّاً وتُفعَّل **تلقائيّاً من جودة البيانات**. يغطّي كلّ صفوف
جدول القرار + الحدود الدقيقة (ECe=2.0، عمر=365، ثقة=0.8). يستورد ``core.salinity_policy`` فقط
(لا api) ⇒ لا حاجة لتخطٍّ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# جذر منصّة sahool على sys.path لاستيراد حزمة ``core`` (نمط test_kc_ndvi.py).
_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.salinity_policy import (  # noqa: E402
    ECE_STRONG,
    ECW_STRONG,
    MAX_AGE_DAYS,
    MIN_CONFIDENCE,
    SalinityDecision,
    salinity_decision,
)


# ── العتبات المُعلَنة (تثبيت القيم التقديريّة القابلة للمعايرة) ────────────────────
def test_thresholds_documented_values():
    assert ECE_STRONG == 2.0
    assert ECW_STRONG == 1.5
    assert MAX_AGE_DAYS == 365
    assert MIN_CONFIDENCE == 0.8


# ── (صفّ) لا بيانات ⇒ off, warn=False ────────────────────────────────────────────
def test_no_data_off_no_warn():
    d = salinity_decision(soil_ece=None, water_ecw=None, analysis_age_days=None, confidence=None)
    assert d.enabled is False
    assert d.warn is False
    assert "لا" in d.reason_ar
    assert isinstance(d, SalinityDecision)


def test_no_data_even_in_saline_region_no_warn():
    # لا قياس إطلاقاً ⇒ لا تنبيه حتى في منطقة مالحة (لا إشارة تُبنى عليها التوصية).
    d = salinity_decision(
        soil_ece=None,
        water_ecw=None,
        analysis_age_days=None,
        confidence=None,
        saline_region=True,
    )
    assert d.enabled is False
    assert d.warn is False


# ── (صفّ) إشارة قويّة + حداثة + ثقة ⇒ on ─────────────────────────────────────────
def test_strong_ece_fresh_confident_on():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=0.9)
    assert d.enabled is True
    assert d.warn is False
    assert any("ECe=3>2" in s for s in d.signals)


def test_strong_ecw_fresh_confident_on():
    d = salinity_decision(soil_ece=None, water_ecw=2.0, analysis_age_days=30, confidence=0.9)
    assert d.enabled is True
    assert any("ECw=2>1.5" in s for s in d.signals)


# ── (صفّ) ECe و ECw معاً + عمر<365 + ثقة≥0.8 ⇒ on ────────────────────────────────
def test_both_ec_fresh_confident_on():
    d = salinity_decision(soil_ece=2.5, water_ecw=1.8, analysis_age_days=100, confidence=0.85)
    assert d.enabled is True
    assert d.warn is False


# ── (صفّ) تحليل قديم ⇒ off ───────────────────────────────────────────────────────
def test_old_analysis_off():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=400, confidence=0.9)
    assert d.enabled is False
    assert any("400يوم" in s for s in d.signals)


# ── (صفّ) ثقة منخفضة ⇒ off ───────────────────────────────────────────────────────
def test_low_confidence_off():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=0.6)
    assert d.enabled is False
    assert any("ثقة" in s and "<0.8" in s for s in d.signals)


# ── (صفّ) منطقة مالحة + تحليل قديم ⇒ off + warn=True ─────────────────────────────
def test_saline_region_old_analysis_off_with_warn():
    d = salinity_decision(
        soil_ece=3.0,
        water_ecw=None,
        analysis_age_days=540,
        confidence=0.9,
        saline_region=True,
    )
    assert d.enabled is False
    assert d.warn is True
    assert "إعادة التحليل" in d.reason_ar
    assert any("منطقة" in s for s in d.signals)


def test_saline_region_low_confidence_off_with_warn():
    d = salinity_decision(
        soil_ece=1.0,
        water_ecw=None,
        analysis_age_days=30,
        confidence=0.5,
        saline_region=True,
    )
    assert d.enabled is False
    assert d.warn is True


# ── (صفّ) محصول حسّاس + EC موجود (حديث/موثوق) ⇒ on ──────────────────────────────
def test_sensitive_crop_low_ec_but_reliable_on():
    # EC تحت العتبات القويّة، لكن المحصول حسّاس جدّاً + تحليل موثوق ⇒ تفعيل.
    d = salinity_decision(
        soil_ece=1.0,
        water_ecw=None,
        analysis_age_days=50,
        confidence=0.95,
        crop_sensitive=True,
    )
    assert d.enabled is True
    assert any("حسّاس" in s for s in d.signals)


def test_sensitive_crop_but_no_data_off():
    # حسّاسيّة المحصول وحدها لا تكفي — لا بدّ من قياس EC موثوق.
    d = salinity_decision(
        soil_ece=None,
        water_ecw=None,
        analysis_age_days=None,
        confidence=None,
        crop_sensitive=True,
    )
    assert d.enabled is False


# ── (صفّ إضافيّ صادق) تحليل موثوق + EC منخفض غير حسّاس ⇒ on (القياس الموثوق يحسم) ──
def test_reliable_low_ec_non_sensitive_on():
    d = salinity_decision(soil_ece=0.8, water_ecw=None, analysis_age_days=10, confidence=0.9)
    assert d.enabled is True
    assert d.warn is False


# ── الحدود الدقيقة ───────────────────────────────────────────────────────────────
def test_boundary_ece_exactly_strong_not_strong_but_reliable_on():
    # ECe=2.0 بالضبط ⇒ ليست «قويّة» (الشرط >)، لكن التحليل موثوق ⇒ on عبر المسار العامّ.
    d = salinity_decision(soil_ece=ECE_STRONG, water_ecw=None, analysis_age_days=30, confidence=0.9)
    assert d.enabled is True
    # لا تُسجَّل إشارة «قويّة» عند المساواة بالضبط.
    assert not any(">2" in s for s in d.signals)


def test_boundary_age_exactly_365_is_old_off():
    # العمر=365 بالضبط ⇒ قديم (الحداثة تتطلّب < MAX_AGE_DAYS).
    d = salinity_decision(
        soil_ece=3.0, water_ecw=None, analysis_age_days=MAX_AGE_DAYS, confidence=0.9
    )
    assert d.enabled is False
    assert any("365يوم≥365" in s for s in d.signals)


def test_boundary_age_364_is_fresh_on():
    d = salinity_decision(
        soil_ece=3.0, water_ecw=None, analysis_age_days=MAX_AGE_DAYS - 1, confidence=0.9
    )
    assert d.enabled is True


def test_boundary_confidence_exactly_min_is_accepted_on():
    # الثقة=0.8 بالضبط ⇒ مقبولة (الشرط >=).
    d = salinity_decision(
        soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=MIN_CONFIDENCE
    )
    assert d.enabled is True


def test_boundary_confidence_just_below_min_off():
    d = salinity_decision(
        soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=MIN_CONFIDENCE - 0.01
    )
    assert d.enabled is False


def test_boundary_ecw_exactly_strong_not_strong_but_reliable_on():
    # ECw=1.5 بالضبط ⇒ ليست «قويّة»، لكن التحليل موثوق ⇒ on.
    d = salinity_decision(soil_ece=None, water_ecw=ECW_STRONG, analysis_age_days=30, confidence=0.9)
    assert d.enabled is True
    assert not any(">1.5" in s for s in d.signals)


# ── الصدق: عمر/ثقة مفقودان مع وجود قياس ⇒ off (لا تفعيل على افتراض) ──────────────
def test_missing_age_with_ec_off():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=None, confidence=0.9)
    assert d.enabled is False
    assert any("غير معروف" in s for s in d.signals)


def test_missing_confidence_with_ec_off():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=None)
    assert d.enabled is False


# ── to_dict شفّاف وقابل للتسلسل ─────────────────────────────────────────────────
def test_to_dict_shape():
    d = salinity_decision(soil_ece=3.0, water_ecw=None, analysis_age_days=30, confidence=0.9)
    out = d.to_dict()
    assert set(out.keys()) == {"enabled", "reason_ar", "warn", "signals"}
    assert out["enabled"] is True
    assert isinstance(out["signals"], list)
    # نسخة (لا مرجع مشترك) — تعديلها لا يؤثّر على القرار.
    out["signals"].append("x")
    assert "x" not in d.signals
