"""اختبار عتبة EC محلول التسميد (Fertigation EC ≤ 2.0 dS/m) — منع حرق الجذور.

يثبت: (أ) الثابت في core.thresholds مُعرَّف ومتمايز عن ملوحة التربة؛ (ب) طبقة guardrails
البيئيّة ترفض fail-closed حين يتجاوز EC المحلول العتبة، وتمرّر تحتها، ولا تنهار عند غيابه؛
(ج) قيمة الطبقة تطابق المصدر الموحّد. نواة بلا شبكة/قاعدة.
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
    # مفهوم مستقلّ عن ملوحة التربة (حارس انجراف).
    assert T.FERTIGATION_EC_MAX_DS_M != T.SALINITY_MODERATE_ECE


def _validate(action_data):
    from tiers.environmental_tier import EnvironmentalSafetyTier

    return asyncio.run(
        EnvironmentalSafetyTier().validate("fertilization", action_data, {"crop": "tomato"})
    )


def test_ec_above_threshold_rejected():
    res = _validate({"fertigation_ec_ds_m": 2.5, "N_kg_ha": 50})
    assert res["passed"] is False
    rules = [(f.get("rule"), f.get("severity")) for f in res["findings"]]
    assert ("fertigation_ec_exceeded", "HIGH") in rules


def test_ec_at_or_below_threshold_passes_ec_check():
    for ec in (2.0, 1.2):
        res = _validate({"fertigation_ec_ds_m": ec, "N_kg_ha": 50})
        rules = [f.get("rule") for f in res["findings"]]
        assert "fertigation_ec_exceeded" not in rules


def test_missing_ec_does_not_crash_or_flag():
    res = _validate({"N_kg_ha": 50})  # تسميد جافّ بلا EC محلول
    rules = [f.get("rule") for f in res["findings"]]
    assert "fertigation_ec_exceeded" not in rules


def test_tier_value_mirrors_canonical_source():
    from core import thresholds as T
    from tiers.environmental_tier import EnvironmentalSafetyTier

    assert EnvironmentalSafetyTier.FERTIGATION_EC_MAX_DS_M == T.FERTIGATION_EC_MAX_DS_M
