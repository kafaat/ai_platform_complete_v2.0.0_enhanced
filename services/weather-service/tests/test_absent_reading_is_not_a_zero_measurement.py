"""ABSENT-READING-COERCED-TO-ZERO-READS-AS-A-MEASUREMENT-01.

**العطلُ الذي وُجِد هذا لأجله:** `normalize_current` و`normalize_hourly_sample` كانا
يقسران القراءةَ الغائبةَ إلى صفر — `float(... or 0.0)` للرياح، و`... or 0` للمطر،
و`_at(..., idx, 0)` للحرارة والرطوبة والغيوم في المسار الساعيّ.

**وليس القَسرُ إلى صفرٍ تحفّظاً بل تساهلاً**، وهذا بيتُ القصيد: صفرُ رياحٍ يُقرأ
«هدوءاً» وصفرُ مطرٍ يُقرأ «جفافاً» — وهما **أكثرُ حالتين إذناً بالرشّ**. فغيابُ
القياس كان يُنتِج نافذةَ رشٍّ تبدو مثاليّة. ولو كان الانحيازُ إلى الحظر لَكان
العطلُ إزعاجاً؛ وانحيازُه إلى الإذن يجعله خطراً زراعيّاً.

و`operation_suitability` مبنيٌّ سلفاً على `None = مفقود` (`_num(sample, key, None)`)،
فالصدقُ هنا لا يحتاج آليّةً جديدة — يبلغ آليّةَ الفشل المغلق القائمة، وقد كان
القَسرُ يمنعه من بلوغها.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "open_meteo.py"


def _mod():
    spec = importlib.util.spec_from_file_location("open_meteo_under_test", _SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


om = _mod()
_LL = {"lat": 24.7, "lon": 46.7}


def test_a_missing_wind_reading_is_none_not_calm():
    out = om.normalize_current({"temperature_2m": 30.0}, **_LL)
    assert out["wind_speed_10m_kmh"] is None, "رياحٌ مفقودةٌ تُقرأ هدوءاً"
    assert out["wind_speed_ms"] is None


def test_a_missing_precipitation_reading_is_none_not_dry():
    out = om.normalize_current({"temperature_2m": 30.0}, **_LL)
    assert out["precipitation_mm"] is None, "مطرٌ مفقودٌ يُقرأ جفافاً"


def test_present_readings_are_untouched():
    """الحالةُ السويّة لا تتغيّر — وإلّا كان العلاجُ انحداراً."""
    out = om.normalize_current(
        {"temperature_2m": 30.0, "wind_speed_10m": 18.0, "precipitation": 2.5}, **_LL
    )
    assert out["wind_speed_10m_kmh"] == 18.0
    assert out["wind_speed_ms"] == pytest.approx(5.0, abs=0.01)
    assert out["precipitation_mm"] == 2.5


def test_a_real_zero_stays_a_zero():
    """صفرٌ **مَقيسٌ** ليس غياباً: التمييزُ هو كلُّ الفرق، فيُحرَس في الاتّجاهين."""
    out = om.normalize_current({"wind_speed_10m": 0.0, "precipitation": 0.0}, **_LL)
    assert out["wind_speed_10m_kmh"] == 0.0
    assert out["wind_speed_ms"] == 0.0
    assert out["precipitation_mm"] == 0.0


def test_the_only_zero_coerced_fields_are_the_declared_daily_two():
    """راتشِتٌ على المصدر — **مُضيَّقٌ على قرارٍ قائمٍ لا مُعمَّمٌ فوقه.**

    المسارُ اليوميُّ يُصفّر المطرَ والرياحَ **قصداً**: «لا مطر» و«لا رياح» قراءتان
    معقولتان للصفر في مجموعٍ يوميّ، والتعليلُ مكتوبٌ في موضعه. فراتشِتٌ يمنع كلَّ
    تصفيرٍ كان سيُخاصِم قراراً مُعلَناً — وذلك كيف يصير الحارسُ إزعاجاً يُلتَفّ عليه.

    ولذلك يُقاس **العدد** لا الغياب: مواضعُ التصفير تساوي الحقولَ المُعلَنة، فأيُّ
    موضعٍ جديدٍ يفشل حتّى يُعلَن باسمه في `_DAILY_ZERO_COERCED_SOURCE_FIELDS`.

    **وتصحيحٌ يُسجَّل:** قيل هنا أوّلاً إنّ التعليقَ في المصدر يُحيل إلى ثابتٍ «غيرِ
    مُعرَّفٍ في الشجرة». والدعوى خطأ — `_DAILY_ZERO_COERCED_FIELDS` مُعرَّفٌ في
    `canonical_weather_state.py:273` بقيمة الطبقة القانونيّة وله اختبارُه. وسببُ
    الخطأ أنّ البحثَ جرى ودليلُ عملِ الصَّدَفة في خدمةٍ أخرى فلم يبلغ هذا الملفّ:
    **صفرُ نتائجَ ليس دليلَ غياب، بل دليلَ أنّ البحثَ لم يبلغ**.

    فأُعيدت تسميةُ ثابتِ هذه الطبقة إلى `_DAILY_ZERO_COERCED_SOURCE_FIELDS` —
    اسمان متطابقان بقيمتين مختلفتين في خدمةٍ واحدة هما الالتباسُ الذي وُجِد الاسمُ
    ليمنعه.
    """
    src = _SRC.read_text(encoding="utf-8")
    assert om._DAILY_ZERO_COERCED_SOURCE_FIELDS == ("precipitation_mm", "wind_max_kmh")
    zero_sites = src.count("idx, 0)")
    assert zero_sites == len(om._DAILY_ZERO_COERCED_SOURCE_FIELDS), (
        f"مواضعُ التصفير {zero_sites} لا تساوي الحقولَ المُعلَنة "
        f"{len(om._DAILY_ZERO_COERCED_SOURCE_FIELDS)} — أُضيف تصفيرٌ بلا إعلان، أو أُزيل مُعلَن"
    )
