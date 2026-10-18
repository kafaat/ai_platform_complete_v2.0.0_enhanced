"""اختبار مرجعيّ (golden master): نسخة WOFOST من Hargreaves تطابق المصدر الكنسيّ.

``shared/wofost/engine.py:hargreaves_et0`` تُعلِن أنّها «نسخة حرفيّة مُتطابقة عمداً»
مع ``services/weather-service/et0.py:hargreaves_et0_mm``. الإعلانُ وحده ادّعاء؛ هذا
الاختبار يجعله مقيساً. **العطلُ الذي وُجِد لأجله:** النسخة كانت تختلف بأرضيّة 0.5
mm/يوم (الكنسيّ 0.0) وبـ``acos`` بلا قصّ يرمي عند خطوط العرض القطبيّة، فاختلف
الناتج على شبكة عالميّة رغم تطابقه على شبكة اليمن.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_WS = _ROOT / "services" / "weather-service"


def _canonical():
    if str(_WS) not in sys.path:
        sys.path.insert(0, str(_WS))
    spec = importlib.util.spec_from_file_location("_canonical_et0", _WS / "et0.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.hargreaves_et0_mm


def _wofost():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from shared.wofost.engine import hargreaves_et0

    return hargreaves_et0


_LATS = (-90.0, -66.0, -35.0, 0.0, 12.8, 15.4, 35.0, 66.6, 80.0, 90.0)
_DOYS = (1, 80, 172, 266, 355)
_TEMPS = ((-30.0, -40.0), (2.0, 1.5), (24.0, 11.0), (36.0, 22.0), (45.0, 30.0))


@pytest.mark.parametrize("lat", _LATS)
def test_wofost_copy_matches_canonical_on_a_global_grid(lat):
    canonical, wofost = _canonical(), _wofost()
    for doy in _DOYS:
        for tmax, tmin in _TEMPS:
            expected = round(canonical(t_max_c=tmax, t_min_c=tmin, lat_deg=lat, doy=doy), 2)
            got = wofost(tmax, tmin, lat, doy)
            assert math.isfinite(got)
            assert got == pytest.approx(expected, abs=0.006), (lat, doy, tmax, tmin)
