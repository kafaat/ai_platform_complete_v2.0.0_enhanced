"""اختبار وحدة لتغذية Water Twin من دفتر المياه (المرحلة الثانية) — نقيّ بلا قاعدة.

يقفل الصدق: الاشتقاق من الدفتر بأولويّة واضحة، وغياب المصدر ⇒ None + "unavailable" (لا تلفيق)،
ومصدر كلّ قيمة مُعلَن.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.water_twin_seed import (  # noqa: E402
    average_recent_etc,
    seed_daily_etc,
    seed_initial_depletion,
)


def test_average_recent_etc_ignores_none():
    """المتوسّط يتجاهل None؛ لا قيم ⇒ None (لا تلفيق صفر)."""
    assert average_recent_etc(
        [{"etc_mm": 4.0}, {"etc_mm": 6.0}, {"etc_mm": None}]
    ) == pytest.approx(5.0)
    assert average_recent_etc([{"etc_mm": None}, {}]) is None
    assert average_recent_etc([]) is None


def test_seed_depletion_priority_override_first():
    """التجاوز الصريح يسبق الدفتر، ويُقصّ إلى [0, TAW]."""
    val, src = seed_initial_depletion({"depletion_mm": 30.0}, taw_mm=100.0, override=20.0)
    assert (val, src) == (20.0, "request")
    # تجاوز يتجاوز TAW ⇒ يُقصّ.
    val2, _ = seed_initial_depletion(None, taw_mm=100.0, override=150.0)
    assert val2 == 100.0


def test_seed_depletion_from_ledger_depletion():
    """يستخدم depletion_mm المُسجَّل عند غياب التجاوز."""
    val, src = seed_initial_depletion({"depletion_mm": 35.0}, taw_mm=100.0)
    assert (val, src) == (35.0, "ledger.depletion_mm")


def test_seed_depletion_from_soil_moisture():
    """يشتقّ من soil_moisture_pct عند غياب depletion_mm: Dr = TAW·(1 − SM/100)."""
    val, src = seed_initial_depletion(
        {"depletion_mm": None, "soil_moisture_pct": 70.0}, taw_mm=100.0
    )
    assert val == pytest.approx(30.0)
    assert src == "ledger.soil_moisture_pct"


def test_seed_depletion_unavailable_is_honest_none():
    """لا دفتر ولا تجاوز ⇒ (None, "unavailable") — لا حالة مُلفّقة."""
    assert seed_initial_depletion(None, taw_mm=100.0) == (None, "unavailable")
    assert seed_initial_depletion({"depletion_mm": None, "soil_moisture_pct": None}, 100.0) == (
        None,
        "unavailable",
    )


def test_seed_daily_etc_priority_and_unavailable():
    """ETc: تجاوز صريح → متوسّط الدفتر → (None,"unavailable"). السالب يرفع خطأ."""
    assert seed_daily_etc([{"etc_mm": 5.0}], override=7.0) == (7.0, "request")
    val, src = seed_daily_etc([{"etc_mm": 4.0}, {"etc_mm": 6.0}])
    assert val == pytest.approx(5.0)
    assert src == "ledger.recent_etc_avg"
    assert seed_daily_etc([], None) == (None, "unavailable")
    with pytest.raises(ValueError):
        seed_daily_etc([], override=-1.0)
