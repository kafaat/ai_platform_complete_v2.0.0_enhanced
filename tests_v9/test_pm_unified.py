"""اختبار توحيد Penman-Monteith (H4): نواة واحدة في core.engines.et0.

يثبت أنّ غلافَي PM (water_balance/WeatherInput و fao56/WeatherDay) يفوّضان للنواة
الموحّدة بنتيجة **متطابقة تماماً** (==)، مع قيمة مرجعيّة مُجمَّدة لكلٍّ (حارس انحدار).
نواة نقيّة بلا خدمات.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines import et0 as E  # noqa: E402
from core.engines.fao56 import WeatherDay, penman_monteith_et0  # noqa: E402


def test_fao56_wrapper_equals_core_and_golden():
    wd = WeatherDay(
        temp_max_c=42,
        temp_min_c=22,
        humidity_pct=27,
        wind_speed_m_s=3.5,
        solar_radiation_mj_m2=16.15,
        latitude_deg=15.5,
        elevation_m=1100,
        day_of_year=200,
    )
    core = E.penman_monteith_et0(42, 22, wd.temp_mean_c, 16.15, 27, 3.5, 15.5, 1100, 200)
    assert penman_monteith_et0(wd) == core  # تفويض تامّ (لا تقريب)
    # قيمة مرجعيّة مُجمَّدة (السلوك المحفوظ؛ الفرع الحدّيّ Rso≤0 غير قابل للوصول هنا).
    assert math.isclose(penman_monteith_et0(wd), 8.720097532111124, rel_tol=1e-12)


def test_core_explicit_t_mean_is_used():
    # t_mean_c الصريح يُحترَم (دلالة water_balance) ويُغيّر النتيجة عن (max+min)/2.
    a = E.penman_monteith_et0(34.0, 18.0, 26.0, 22.0, 45.0, 2.0, 15.5, 2000.0, 100)
    b = E.penman_monteith_et0(34.0, 18.0, 28.0, 22.0, 45.0, 2.0, 15.5, 2000.0, 100)
    assert a != b
