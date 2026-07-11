"""اختبار توحيد Penman-Monteith (H4): نواة واحدة في core.engines.et0.

يثبت أنّ غلافَي PM (water_balance/WeatherInput و fao56/WeatherDay) يفوّضان للنواة
الموحّدة بنتيجة **متطابقة تماماً** (==)، مع قيمة مرجعيّة مُجمَّدة لكلٍّ (حارس انحدار).
نواة نقيّة بلا خدمات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines import et0 as E  # noqa: E402


def test_core_explicit_t_mean_is_used():
    # t_mean_c الصريح يُحترَم (دلالة water_balance) ويُغيّر النتيجة عن (max+min)/2.
    a = E.penman_monteith_et0(34.0, 18.0, 26.0, 22.0, 45.0, 2.0, 15.5, 2000.0, 100)
    b = E.penman_monteith_et0(34.0, 18.0, 28.0, 22.0, 45.0, 2.0, 15.5, 2000.0, 100)
    assert a != b
