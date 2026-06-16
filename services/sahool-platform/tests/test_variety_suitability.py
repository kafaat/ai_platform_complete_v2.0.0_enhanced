"""اختبارات محرّك الملاءمة على مستوى الصنف (variety_suitability).

سلوكيّة: القيم المتوقَّعة محسوبة يدويّاً من البطاقات الحقيقيّة:
  - common_bean: threshold 1.0 dS/m، slope 19% لكل dS/m.
  - common_bean_yemen_1: modifier 0.0، نضج 105، تزهير 60، تحمّلات غير فارغة.
  - common_bean_rajm_1: modifier 0.0، نضج 95، تزهير 53، تحمّلات فارغة.
"""

import datetime

import pytest
from core.variety_suitability import (
    expected_harvest,
    salinity_suitability,
    variety_disease_watch,
    variety_salinity_threshold,
)

pytestmark = pytest.mark.unit


# ── 1) عتبة الملوحة للصنف ─────────────────────────────────────
def test_threshold_yemen_1_inherits_crop_with_zero_modifier():
    # 1.0 (المحصول) + 0.0 (تعديل الصنف) = 1.0
    assert variety_salinity_threshold("common_bean_yemen_1") == 1.0


def test_threshold_unknown_variety_is_none():
    assert variety_salinity_threshold("no_such_variety") is None


# ── 2) تصنيف الملاءمة الملحيّة ────────────────────────────────
def test_salinity_at_threshold_is_suitable_zero_loss():
    r = salinity_suitability("common_bean_yemen_1", 1.0)
    assert r["class"] == "suitable"
    assert r["expected_yield_loss_pct"] == 0
    assert r["threshold_ece_ds_m"] == 1.0
    assert r["measured_ece_ds_m"] == 1.0


def test_salinity_marginal_19pct_loss():
    # فوق العتبة بـ 1 dS/m ⇒ 19 × (2−1) = 19% ⇒ ≤ 25 ⇒ marginal
    r = salinity_suitability("common_bean_yemen_1", 2.0)
    assert r["expected_yield_loss_pct"] == 19
    assert r["class"] == "marginal"


def test_salinity_unsuitable_high_loss():
    # 19 × (5−1) = 76% ⇒ > 25 ⇒ unsuitable
    r = salinity_suitability("common_bean_yemen_1", 5.0)
    assert r["expected_yield_loss_pct"] == 76
    assert r["class"] == "unsuitable"


def test_salinity_loss_clamped_to_100():
    # 19 × (10−1) = 171 ⇒ مثبَّت عند 100
    r = salinity_suitability("common_bean_yemen_1", 10.0)
    assert r["expected_yield_loss_pct"] == 100
    assert r["class"] == "unsuitable"


def test_salinity_unknown_variety_class_none():
    r = salinity_suitability("no_such_variety", 2.0)
    assert r["class"] is None
    assert r["expected_yield_loss_pct"] is None
    assert r["note_ar"] == "بيانات غير كافية"


# ── 3) تواريخ التزهير والحصاد ────────────────────────────────
def test_expected_harvest_rajm_1():
    sow = datetime.date(2026, 6, 1)
    r = expected_harvest("common_bean_rajm_1", sow)
    assert r["days_to_maturity"] == 95
    assert r["days_to_50pct_flowering"] == 53
    # الحصاد = الزراعة + 95 يوماً ؛ التزهير = الزراعة + 53 يوماً
    assert r["expected_harvest_date"] == (sow + datetime.timedelta(days=95)).isoformat()
    assert r["expected_flowering_date"] == (sow + datetime.timedelta(days=53)).isoformat()
    assert r["sowing_date"] == "2026-06-01"


def test_expected_harvest_unknown_variety_is_honest():
    sow = datetime.date(2026, 6, 1)
    r = expected_harvest("no_such_variety", sow)
    assert r["days_to_maturity"] is None
    assert r["expected_harvest_date"] is None
    assert r["days_to_50pct_flowering"] is None
    assert r["expected_flowering_date"] is None
    assert r["sowing_date"] == "2026-06-01"


# ── 4) رصد الأمراض ───────────────────────────────────────────
def test_disease_watch_yemen_1_lists_resistances():
    r = variety_disease_watch("common_bean_yemen_1")
    assert r["resistant_ar"]  # غير فارغة
    assert "تحمّل المنّ" in r["resistant_ar"]


def test_disease_watch_rajm_1_empty_scout_broadly():
    r = variety_disease_watch("common_bean_rajm_1")
    assert r["resistant_ar"] == []
    assert "مسحٍ ميدانيّ واسع" in r["note_ar"]


def test_disease_watch_unknown_variety_is_honest():
    r = variety_disease_watch("no_such_variety")
    assert r["resistant_ar"] == []
    assert r["note_ar"]  # ملاحظة صادقة، بلا استثناء
