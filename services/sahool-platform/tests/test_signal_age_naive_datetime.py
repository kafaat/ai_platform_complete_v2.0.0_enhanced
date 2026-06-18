"""BLOCKER-02 (تقرير جنائيّ): _signal_age_days كان يُسقِط محرّك الحالة على طابع بلا
منطقة زمنيّة (من mobile/IoT) — طرح naive من aware يرفع TypeError غير مُلتقَط.
BLOCKER-01: مسبح القاعدة صار قابلاً للضبط (DB_POOL_MIN/MAX) لا ثابتاً عند 10.
"""

from __future__ import annotations

import os

import pytest
from core.agronomic_state_engine import _signal_age_days

pytestmark = pytest.mark.unit


def test_naive_timestamp_does_not_crash():
    """طابع بلا منطقة (مثل ما يرسله mobile) ⇒ يُحسَب العمر بلا TypeError."""
    age = _signal_age_days("2026-06-18T10:00:00")  # naive
    assert age is not None
    assert age >= 0  # في الماضي ⇒ عمر غير سالب


def test_aware_timestamp_still_works():
    assert _signal_age_days("2026-06-18T10:00:00+00:00") is not None
    assert _signal_age_days("2026-06-18T10:00:00Z") is not None


def test_none_and_garbage_return_none():
    assert _signal_age_days(None) is None
    assert _signal_age_days("not-a-date") is None


def test_pool_env_configurable():
    """BLOCKER-01: نقطة الإقلاع تقرأ DB_POOL_MIN/MAX (لا max_size ثابت عند 10)."""
    base = os.path.join(os.path.dirname(__file__), "..", "api", "main.py")
    src = open(base, encoding="utf-8").read()
    assert "DB_POOL_MIN" in src and "DB_POOL_MAX" in src
    # مسبح التطبيق يستعمل القيمة المضبوطة لا ثابتاً (الجوبز يبقى صغيراً عمداً max_size=4).
    assert "max_size=_pool_max" in src
