"""اختبار كفاءة استخدام المياه (Outcome KPI) — تجميع نقيّ من دفتر المياه.

يقفل: WUE من التوازن المائيّ (ETc مقابل المُورَّد)؛ كشف الإفراط (over_application + WUE<1)؛
بوّابات الصدق (needs_data بلا طلب · needs_irrigation_data بلا ريّ مُسجَّل) — لا رقم مُضلِّل،
لا غلّة (خارج النطاق)، fail-safe على مدخل فاسد.
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
    from api.water_efficiency import compute_water_efficiency
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def _day(etc=None, rain=None, irr=None):
    return {"etc_mm": etc, "rain_mm": rain, "irrigation_mm": irr}


def test_over_irrigation_lowers_wue():
    """إفراط ريّ (مُورَّد > طلب) ⇒ WUE<1 + over_application>0 (ذراع الخفض)."""
    rows = [_day(etc=5, rain=0, irr=6) for _ in range(3)]  # etc=15, irr=18
    r = compute_water_efficiency(rows)
    assert r["status"] == "ok"
    assert r["etc_mm_total"] == 15.0
    assert r["supplied_mm_total"] == 18.0
    assert r["water_use_efficiency"] == 0.833  # 15/18 مقصوصة
    assert r["demand_met_pct"] == 100.0
    assert r["over_application_mm"] == 3.0
    assert r["calibrated"] is False
    assert r["source"] == "water_ledger"


def test_matched_supply_is_efficient():
    """تطابق المُورَّد والطلب ⇒ WUE=1، لا إفراط."""
    rows = [_day(etc=5, rain=0, irr=5), _day(etc=5, rain=0, irr=5)]
    r = compute_water_efficiency(rows)
    assert r["water_use_efficiency"] == 1.0
    assert r["over_application_mm"] == 0.0
    assert r["demand_met_pct"] == 100.0


def test_under_irrigation_efficient_use_but_deficit():
    """نقص ريّ ⇒ كلّ المُورَّد مُستغَلّ (WUE=1) لكن demand_met<100 (إجهاد)."""
    rows = [_day(etc=10, rain=0, irr=5), _day(etc=10, rain=0, irr=5)]  # etc=20, supplied=10
    r = compute_water_efficiency(rows)
    assert r["water_use_efficiency"] == 1.0
    assert r["demand_met_pct"] == 50.0
    assert r["over_application_mm"] == 0.0


def test_effective_rain_capped_at_demand():
    """المطر الفعّال = min(rain, etc) (الفائض يُفقَد) — تبسيط مُعلَن."""
    rows = [_day(etc=5, rain=20, irr=3)]  # eff_rain=5, supplied=8
    r = compute_water_efficiency(rows)
    assert r["effective_rain_mm_total"] == 5.0
    assert r["supplied_mm_total"] == 8.0
    assert r["water_use_efficiency"] == 0.625  # 5/8


def test_needs_irrigation_data_when_no_irrigation_logged():
    """طلب مُسجَّل لكن لا ريّ فعليّ ⇒ needs_irrigation_data (لا WUE مُضلِّل من المطر وحده)."""
    rows = [_day(etc=5, rain=2, irr=None), _day(etc=5, rain=2, irr=0)]
    r = compute_water_efficiency(rows)
    assert r["status"] == "needs_irrigation_data"
    assert r["water_use_efficiency"] is None
    assert "سجّل الريّ" in r["note_ar"]


def test_needs_data_when_no_etc_or_empty():
    """لا طلب (ETc) أو قائمة فارغة ⇒ needs_data (لا كفاءة محسوبة)."""
    assert compute_water_efficiency([])["status"] == "needs_data"
    assert compute_water_efficiency([_day(etc=None, rain=5, irr=5)])["status"] == "needs_data"
    assert compute_water_efficiency([_day(etc=0, irr=5)])["status"] == "needs_data"


def test_fail_safe_on_invalid_input():
    """مدخل غير قائمة / عناصر فاسدة ⇒ كتلة needs_data (لا رمي)."""
    assert compute_water_efficiency(None)["status"] == "needs_data"
    assert compute_water_efficiency("nope")["status"] == "needs_data"
    # عنصر فاسد ضمن القائمة يُتخطّى بأمان
    r = compute_water_efficiency(["bad", _day(etc=5, irr=5)])
    assert r["status"] == "ok"
    assert r["days_counted"] == 1
