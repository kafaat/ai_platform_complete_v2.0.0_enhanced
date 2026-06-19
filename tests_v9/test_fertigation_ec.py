"""اختبار عتبة EC محلول التسميد لكلّ محصول/مرحلة (Fertigation) + PASS/WARN/REJECT.

يثبت: (أ) الثابت العامّ في core.thresholds متمايز عن ملوحة التربة؛ (ب) عتبة الصنف/المرحلة
(دالّة نقيّة)؛ (ج) تصنيف PASS/WARN/REJECT؛ (د) إنفاذ guardrails (REJECT يحجب، WARN
يحذّر دون حجب، الغياب لا ينهار)؛ (هـ) تطابق العامّ مع المصدر الموحّد. نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
_GR = os.path.join(os.path.dirname(__file__), "..", "services/guardrails-engine")
for _p in (_PLATFORM, _GR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_constant_defined_and_distinct():
    from core import thresholds as T

    assert T.FERTIGATION_EC_MAX_DS_M == 2.0
    assert T.FERTIGATION_EC_MAX_DS_M != T.SALINITY_MODERATE_ECE  # مفهوم مستقلّ


def test_crop_ec_threshold_pure():
    from tiers.environmental_tier import crop_ec_threshold

    assert crop_ec_threshold("citrus", "flowering") == 1.7  # تجاوز المرحلة
    assert crop_ec_threshold("citrus", "vegetative") == 2.0  # غير مُعرّفة ⇒ _default
    assert crop_ec_threshold("potato", "tuber_initiation") == 1.5
    assert crop_ec_threshold("alfalfa", None) == 2.5
    assert crop_ec_threshold("CITRUS", "FLOWERING") == 1.7  # غير حسّاس للحالة
    assert crop_ec_threshold("unknown_crop", "x") == 2.0  # ⇒ العتبة العامّة


def test_check_fertigation_ec_status():
    from tiers.environmental_tier import check_fertigation_ec

    # potato/tuber: عتبة 1.5، هامش تحذير ×1.15 = 1.725.
    assert check_fertigation_ec("potato", "tuber_initiation", 1.4)[0] == "PASS"
    assert check_fertigation_ec("potato", "tuber_initiation", 1.6)[0] == "WARN"
    assert check_fertigation_ec("potato", "tuber_initiation", 2.0)[0] == "REJECT"


def _validate(action_data, crop="wheat"):
    from tiers.environmental_tier import EnvironmentalSafetyTier

    return asyncio.run(
        EnvironmentalSafetyTier().validate("fertilization", action_data, {"crop": crop})
    )


def test_tier_rejects_above_threshold():
    # wheat مجهول ⇒ عتبة عامّة 2.0؛ ec=3.0 > 2.3 ⇒ REJECT يحجب.
    res = _validate({"fertigation_ec_ds_m": 3.0, "N_kg_ha": 50})
    assert res["passed"] is False
    rules = [(f.get("rule"), f.get("severity")) for f in res["findings"]]
    assert ("fertigation_ec_exceeded", "HIGH") in rules


def test_tier_warns_in_margin_without_blocking():
    # عتبة 2.0، ec=2.2 ضمن +15% (≤2.3) ⇒ WARN (MEDIUM) لا يحجب التير.
    res = _validate({"fertigation_ec_ds_m": 2.2, "N_kg_ha": 50})
    rules = [(f.get("rule"), f.get("severity")) for f in res["findings"]]
    assert ("fertigation_ec_borderline", "MEDIUM") in rules
    assert res["passed"] is True  # WARN لا يحجب الطبقة


def test_per_crop_threshold_applied():
    # potato/tuber عتبة 1.5؛ ec=1.8 (يمرّ عامّاً 2.0) ⇒ REJECT لحسّاسيّة الصنف.
    res = _validate({"fertigation_ec_ds_m": 1.8, "growth_stage": "tuber_initiation"}, crop="potato")
    assert res["passed"] is False


def test_missing_ec_does_not_crash_or_flag():
    res = _validate({"N_kg_ha": 50})
    rules = [f.get("rule") for f in res["findings"]]
    assert "fertigation_ec_exceeded" not in rules
    assert "fertigation_ec_borderline" not in rules


def test_tier_default_mirrors_canonical_source():
    from core import thresholds as T
    from tiers.environmental_tier import EnvironmentalSafetyTier

    assert EnvironmentalSafetyTier.FERTIGATION_EC_MAX_DS_M == T.FERTIGATION_EC_MAX_DS_M
