"""اختبارات وحدة لمحلّل مقارنة المواسم (نقيّ، حتميّ).

تغطّي: حساب نسبة التغيّر على أرقام محسوسة، معالجة None، الاتّجاهات up/down/flat،
القسمة على صفر (سابق=0 ⇒ النسبة None لا انهيار)، وحُكم التحسّن مقابل التراجع.
"""

from __future__ import annotations

import pytest
from core.season_comparison import SeasonMetrics, compare_seasons

pytestmark = pytest.mark.unit


def _seasons(**overrides):
    """يبني موسمين (حاليّ/سابق) بقيم افتراضيّة قابلة للتجاوز."""
    cur = overrides.get("current", {})
    prev = overrides.get("previous", {})
    current = SeasonMetrics(season_id="2026", crop_id="wheat", **cur)
    previous = SeasonMetrics(season_id="2025", crop_id="wheat", **prev)
    return current, previous


def test_percent_change_math_yield_up_20pct():
    """غلّة 5→6 = +20% بالضبط، فرق +1، اتّجاه up، وتحسّن (better=True)."""
    cur, prev = _seasons(current={"yield_t_ha": 6.0}, previous={"yield_t_ha": 5.0})
    result = compare_seasons(cur, prev)
    y = result["metrics"]["yield_t_ha"]
    assert y["current"] == 6.0
    assert y["previous"] == 5.0
    assert y["delta"] == 1.0
    assert y["percent_change"] == 20.0
    assert y["direction"] == "up"
    assert y["better"] is True


def test_percent_change_decrease():
    """غلّة 5→4 = -20%، اتّجاه down، تراجع (better=False)."""
    cur, prev = _seasons(current={"yield_t_ha": 4.0}, previous={"yield_t_ha": 5.0})
    y = compare_seasons(cur, prev)["metrics"]["yield_t_ha"]
    assert y["percent_change"] == -20.0
    assert y["direction"] == "down"
    assert y["better"] is False


def test_none_on_one_side_is_skipped_no_crash():
    """مقياس None على جانب واحد يُتجاهَل بلا انهيار ويُدرَج في skipped_metrics."""
    cur, prev = _seasons(
        current={"yield_t_ha": 6.0, "ndvi_peak": None},
        previous={"yield_t_ha": 5.0, "ndvi_peak": 0.7},
    )
    result = compare_seasons(cur, prev)
    assert "ndvi_peak" not in result["metrics"]
    assert "ndvi_peak" in result["skipped_metrics"]
    assert "yield_t_ha" in result["metrics"]  # المتوفّر على الجانبين يبقى


def test_direction_flat():
    """قيمتان متساويتان ⇒ اتّجاه flat، فرق صفر، نسبة 0، وbetter محايد None."""
    cur, prev = _seasons(current={"yield_t_ha": 5.0}, previous={"yield_t_ha": 5.0})
    y = compare_seasons(cur, prev)["metrics"]["yield_t_ha"]
    assert y["direction"] == "flat"
    assert y["delta"] == 0.0
    assert y["percent_change"] == 0.0
    assert y["better"] is None


def test_division_by_zero_previous_zero_percent_none():
    """سابق=0 ⇒ نسبة التغيّر None (لا قسمة على صفر) لكن الفرق/الاتّجاه يُحسبان."""
    cur, prev = _seasons(current={"water_used_m3": 100.0}, previous={"water_used_m3": 0.0})
    w = compare_seasons(cur, prev)["metrics"]["water_used_m3"]
    assert w["percent_change"] is None
    assert w["delta"] == 100.0
    assert w["direction"] == "up"


def test_verdict_improvement():
    """غلّة أعلى + كفاءة ماء أفضل ⇒ حُكم تحسّن."""
    cur, prev = _seasons(
        current={"yield_t_ha": 6.0, "water_use_efficiency": 1.2},
        previous={"yield_t_ha": 5.0, "water_use_efficiency": 1.0},
    )
    verdict = compare_seasons(cur, prev)["verdict_ar"]
    assert verdict.startswith("تحسّن")


def test_verdict_regression():
    """غلّة أقلّ + كفاءة ماء أسوأ ⇒ حُكم تراجع."""
    cur, prev = _seasons(
        current={"yield_t_ha": 4.0, "water_use_efficiency": 0.8},
        previous={"yield_t_ha": 5.0, "water_use_efficiency": 1.0},
    )
    verdict = compare_seasons(cur, prev)["verdict_ar"]
    assert verdict.startswith("تراجع")


def test_verdict_inconclusive_when_no_judging_metrics():
    """غياب الغلّة والكفاءة ⇒ حُكم غير حاسم (لا انهيار)."""
    cur, prev = _seasons(current={"et0_total_mm": 1200.0}, previous={"et0_total_mm": 1100.0})
    verdict = compare_seasons(cur, prev)["verdict_ar"]
    assert verdict.startswith("غير حاسم")
