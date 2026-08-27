"""A-SILENT-CLAMP-HIDES-AN-OUT-OF-RANGE-INPUT-01 — القصُّ محدودٌ بضجيج المستشعر.

**العطلُ الذي وُجِد هذا لأجله:** `actual_vapor_pressure_from_rh_kpa` كان يقصّ أيَّ
`rh_pct` إلى `[0, 100]` بلا حدّ. فقراءةُ 350٪ — وهي عطلُ مستشعرٍ لا رطوبة — تصير
100٪، ويخرج `ea` **سليمَ الشكل** ويمضي إلى ET0 ومنه إلى قرار ريّ. لا استثناء، ولا
سجلّ، ولا حقلَ جودةٍ يقول إنّ المُدخَل كان مكسوراً.

وهذا الصنفُ بعينه هو ما تحرسه بقيّةُ هذه الطبقة: **غيابُ قياسٍ لا يُحوَّل إلى قياسٍ
واثق**. والقصُّ غيرُ المحدود يفعل ذلك بالضبط، وبصمت.

والحدُّ ليس اعتباطاً: مقاييسُ الرطوبة تُبلِّغ تجاوزاتٍ صغيرةً حول التشبّع والصفر،
فيُقبَل ذلك ضجيجاً ويُقصّ؛ وما جاوز النطاقَ يُرفَض.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "vapor_pressure.py"


def _mod():
    spec = importlib.util.spec_from_file_location("vapor_pressure", _SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


vp = _mod()
_ES = 2.0  # kPa — قيمةُ تشبّعٍ واقعيّة عند ~17°م، تُبقي الحسابَ قابلاً للقراءة


@pytest.mark.parametrize("rh", [0.0, 50.0, 100.0])
def test_readings_in_range_are_unchanged(rh: float):
    """الحالةُ السويّة لا تتأثّر — وإلّا كان العلاجُ انحداراً."""
    assert vp.actual_vapor_pressure_from_rh_kpa(_ES, rh) == pytest.approx(_ES * rh / 100.0)


@pytest.mark.parametrize("rh", [100.4, 103.0, -0.3, -4.0])
def test_sensor_noise_at_the_boundaries_is_still_clamped(rh: float):
    """تجاوزٌ صغيرٌ حول الحدّين ضجيجٌ مشروع: يُقصّ ولا يُرفَض.

    هذا هو نصفُ العقد الذي يمنع العلاجَ من أن يصير إزعاجاً يُلتَفّ عليه.
    """
    out = vp.actual_vapor_pressure_from_rh_kpa(_ES, rh)
    assert 0.0 <= out <= _ES


@pytest.mark.parametrize("rh", [350.0, 106.0, -40.0, -5.1])
def test_a_broken_reading_is_refused_not_turned_into_a_valid_number(rh: float):
    """ما جاوز نطاقَ الضجيج يُرفَض — لا يُقصّ إلى رقمٍ يبدو قياساً."""
    with pytest.raises(ValueError) as err:
        vp.actual_vapor_pressure_from_rh_kpa(_ES, rh)
    assert "خارج نطاق ضجيج المستشعر" in str(err.value)
    assert repr(rh) in str(err.value), "الرسالةُ يجب أن تسمّي القيمةَ الجانية"


def test_the_tolerance_is_a_named_constant_not_a_literal_in_the_condition():
    """حدُّ الضجيج قرارٌ يُراجَع، فيُسمّى في موضعٍ واحد.

    حرفيّةٌ مبثوثةٌ في الشرط تجعل توسيعَ النطاق سهواً تغييراً غيرَ مرئيّ في المراجعة.
    """
    assert vp._RH_SENSOR_TOLERANCE_PCT == 5.0
    src = _SRC.read_text(encoding="utf-8")
    assert "_RH_SENSOR_TOLERANCE_PCT <= rh_pct <= 100.0 + _RH_SENSOR_TOLERANCE_PCT" in src
