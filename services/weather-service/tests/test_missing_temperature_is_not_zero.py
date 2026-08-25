"""H1 — قراءةٌ حراريّة غائبة تبقى غائبة: من الحافّة إلى الغلاف إلى النواة.

`normalize_daily` كان يضع `0` عند غياب `temperature_2m_max/min` (`_at(..., idx, 0)`).
والصفرُ المُقنَّع لا يُخطئ قليلاً — يُخطئ في اتّجاهين معاً:

  * **يبخس التراكم:** يومٌ مفقود يساهم بـ0 GDD بدل ألّا يساهم.
  * **ويُضخّم المرصود:** `_finite(0.0)` صادقة، فيُحتسَب اليوم في `counted` وفي
    `coverage_ratio` — أي تُبلَّغ تغطيةٌ أعلى من الحقيقيّة بنفس الأيّام المفقودة.

فالنتيجة نافذةٌ حرجة تُسقَط أبعدَ ممّا هي، بثقةٍ أعلى ممّا تستحقّ.

و`0.0°C` **قراءةٌ فيزيائيّة مشروعة** — فبعد التصفير لا يبقى في البيانات ما يفصلها
عن الغياب. العلاج عند الحافّة وحدها لأنّها آخر موضعٍ يعرف الفرق.

وهذا الملفّ يقيس **السلسلة كاملةً** لا الحافّة وحدها: الحافّة تُنتِج `None` · الغلاف
يُنزِل الجودة ويُسمّي الحقل · النواة تتخطّى اليوم ولا تعدّه. كلٌّ منها كان يعمل سلفاً؛
التصفيرُ وحده هو ما كان يمنعها من أن تُطلِق.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical_weather_state import (  # noqa: E402
    _DAILY_ZERO_COERCED_FIELDS,
    build_canonical_weather_state,
)
from gdd import accumulate_gdd  # noqa: E402
from open_meteo import normalize_daily  # noqa: E402

pytestmark = pytest.mark.unit


def _payload(tmax: list, tmin: list) -> dict:
    """حمولةٌ **كاملة** عدا ما يُحقن غيابه عمداً.

    الاكتمال شرطٌ لا زينة: `_DAILY_EXPECTED_DAY_FIELDS` تضمّ `et0_mm` و`weather_code`
    أيضاً، وحمولةٌ ناقصةٌ فيهما تجعل الجواب `degraded` **دائماً** — فيمرّ تأكيدُ
    الغياب أدناه بلا أن يقيس الغياب. (مقيسٌ: أوّل صياغةٍ سقطت هكذا بالضبط.)
    """
    return {
        "daily": {
            "time": ["2026-03-01", "2026-03-02", "2026-03-03"],
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
            "precipitation_sum": [0.0, 0.0, 0.0],
            "et0_fao_evapotranspiration": [4.1, 4.2, 4.0],
            "wind_speed_10m_max": [10.0, 11.0, 9.0],
            "weather_code": [0, 1, 2],
        },
        "timezone": "Asia/Aden",
    }


def _normalized(tmax: list, tmin: list) -> dict:
    return normalize_daily(_payload(tmax, tmin), lat=15.0, lon=44.0, source="test", model="test")


# ── ① الحافّة: الغياب يبقى None ────────────────────────────────────────
def test_a_missing_daily_temperature_stays_none_at_the_edge():
    days = _normalized([30.0, None, 32.0], [18.0, None, 19.0])["days"]

    assert days[1]["temp_max_c"] is None, "قراءة غائبة صُفِّرت — الغياب صار رصداً"
    assert days[1]["temp_min_c"] is None
    assert days[0]["temp_max_c"] == 30.0 and days[2]["temp_max_c"] == 32.0


def test_a_short_provider_array_is_absence_not_zero():
    """المزوّد قد يُرجِع مصفوفةً أقصر من `time` — والنقص هنا غيابٌ كذلك."""
    days = _normalized([30.0], [18.0])["days"]

    assert days[1]["temp_max_c"] is None and days[2]["temp_max_c"] is None


def test_an_observed_zero_survives_as_an_observation():
    """الوجه الآخر للعقد: صفرٌ **مرصود** يبقى رقماً ولا يُقرأ غياباً."""
    days = _normalized([0.0, 30.0, 32.0], [-2.0, 18.0, 19.0])["days"]

    assert days[0]["temp_max_c"] == 0.0
    assert days[0]["temp_min_c"] == -2.0


# ── ② الغلاف: الغياب يُنزِل الجودة ويُسمّي الحقل ──────────────────────
def _daily_slot(series: dict) -> dict:
    state = build_canonical_weather_state(lat_deg=15.0, valid_time=None, forecast_series=series)
    return state["products"]["forecast"]


def test_the_envelope_degrades_and_names_the_missing_temperature():
    slot = _daily_slot(_normalized([30.0, None, 32.0], [18.0, 17.0, 19.0]))

    assert slot["quality_status"] == "degraded"
    assert "temp_max_c" in slot["days_missing_fields"]
    assert any("missing expected fields" in lim for lim in slot["limitations"])


def test_a_complete_series_stays_validated():
    """بلا هذا، كان «degraded دائماً» يمرّ بوصفه نجاحاً."""
    slot = _daily_slot(_normalized([30.0, 31.0, 32.0], [18.0, 17.0, 19.0]))

    assert slot["quality_status"] == "validated"
    assert slot["days_missing_fields"] == []


def test_the_envelope_no_longer_publishes_a_zero_coercion_caveat_for_temperature():
    """قيدٌ يصف تصفيراً لم يعد يقع يُقرأ **عذراً** — فالكذبة تنتقل من البيانات إلى النثر."""
    assert "temp_max_c" not in _DAILY_ZERO_COERCED_FIELDS
    assert "temp_min_c" not in _DAILY_ZERO_COERCED_FIELDS
    # والمطر والرياح ما زالا مُصفَّرَين فعلاً ⇒ قيدُهما يبقى صادقاً.
    assert set(_DAILY_ZERO_COERCED_FIELDS) == {"precipitation_mm", "wind_max_ms"}

    slot = _daily_slot(_normalized([30.0, 31.0, 32.0], [18.0, 17.0, 19.0]))
    caveat = [lim for lim in slot["limitations"] if "indistinguishable" in lim]
    assert caveat, "قيد التصفير اختفى كلّيّاً — والمطر والرياح ما زالا مُصفَّرَين"
    assert "temp_max_c" not in caveat[0] and "temp_min_c" not in caveat[0]


# ── ③ النواة: اليوم المفقود لا يُجمَع ولا يُعَدّ ──────────────────────
def test_the_gdd_core_skips_the_missing_day_instead_of_crediting_it_zero():
    """الاتّجاهان معاً في تأكيدٍ واحد: التراكم لا يُبخَس، والعدّ لا يُضخَّم."""
    days = _normalized([30.0, None, 30.0], [20.0, None, 20.0])["days"]
    daily, total, counted = accumulate_gdd(
        daily_t_min=[d["temp_min_c"] for d in days],
        daily_t_max=[d["temp_max_c"] for d in days],
        base_c=10.0,
    )

    assert daily[1] is None, "اليوم المفقود حُسِب"
    assert counted == 2, "اليوم المفقود عُدّ ضمن المرصود — تغطيةٌ مُضخَّمة"
    assert total == pytest.approx(30.0)  # يومان × (25−10)


def test_zero_coercion_would_have_inflated_the_count_and_deflated_the_sum():
    """المرجع المضادّ: ما كانت النواة تراه **قبل** الإصلاح، بنفس السلسلة.

    مكتوبٌ صراحةً لأنّ الفرق هو الحمولة كلّها — وبلا مقارنةٍ يبدو التأكيد أعلاه
    وصفاً لسلوكٍ عاديّ لا لعطلٍ أُصلِح.
    """
    _, total_zeroed, counted_zeroed = accumulate_gdd(
        daily_t_min=[20.0, 0.0, 20.0],  # ما كان يصل قبل H1
        daily_t_max=[30.0, 0.0, 30.0],
        base_c=10.0,
    )

    assert counted_zeroed == 3  # ثلاثة أيّام «مرصودة» واثنان فقط حقيقيّان
    assert total_zeroed == pytest.approx(30.0)  # نفس المجموع، موزَّعاً على أيّامٍ أكثر
