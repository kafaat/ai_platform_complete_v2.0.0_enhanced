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


def test_the_only_zero_coerced_daily_fields_are_the_declared_ones():
    """راتشِتٌ على المصدر — **مُضيَّقٌ على قرارٍ قائمٍ لا مُعمَّمٌ فوقه.**

    المسارُ اليوميُّ يُصفّر الرياحَ **قصداً**: «لا رياح» قراءةٌ معقولةٌ للصفر في
    مجموعٍ يوميّ، والتعليلُ مكتوبٌ في موضعه. فراتشِتٌ يمنع كلَّ تصفيرٍ كان سيُخاصِم
    قراراً مُعلَناً — وذلك كيف يصير الحارسُ إزعاجاً يُلتَفّ عليه.

    **وكان المطرُ معها حتّى 2026-09-04.** خرج لأنّ معقوليّةَ الصفر تعتمد على المستهلك
    لا على الحقل: «لا مطر» معقولةٌ لعرضٍ على خريطة، وكاذبةٌ لكمّيّةِ ريٍّ تُطرَح منها.

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
    # **خرج `precipitation_mm` من الإعلان (2026-09-04)** — والحارسُ أمسك الخروجَ
    # بشقّه الثاني («أو أُزيل مُعلَن») كما صُمِّم. والسببُ أنّ «لا مطر» قراءةٌ معقولةٌ
    # **للعرض** وكاذبةٌ **للريّ**: المطرُ الأخير يُطرَح من الاحتياج، فالصفرُ المُقنَّع
    # يرفع الكمّيّةَ الموصى بها — انحيازٌ في اتّجاه الإذن بالريّ. والرياحُ تبقى: لا
    # مستهلكَ يطرحها من كمّيّةٍ يُصدِرها لمزارع.
    # **وخرجت الرياحُ (2026-09-22) فصارت القائمةُ فارغة** — والحارسُ أمسك خروجَها بشقّه
    # الثاني كما أمسك خروجَ المطر. والحجّةُ المكتوبة أعلاه («لا مستهلكَ يطرحها من كمّيّةٍ
    # يُصدِرها لمزارع») سقطت بالقياس لا بالرأي: `phase_runtime_workers.py:608` يمرّر
    # `wind_max_ms` إلى `wind_2m_ms` في ET0، وET0 يقود دفترَ الماء الذي يُصدِر كمّيّةَ الريّ.
    # وريحٌ صفرٌ **تُنقِص** ET0 فتُنقِص الكمّيّة — عطشٌ حيث كان المطرُ يُغرِق.
    #
    # والحارسُ يبقى حيّاً بفراغه: أيُّ تصفيرٍ جديدٍ عند هذه الحافّة يجعل العدَّ واحداً
    # مقابل صفرٍ مُعلَن فيحمرّ حتّى يُعلَن باسمه.
    assert om._DAILY_ZERO_COERCED_SOURCE_FIELDS == ()
    zero_sites = src.count("idx, 0)")
    assert zero_sites == len(om._DAILY_ZERO_COERCED_SOURCE_FIELDS), (
        f"مواضعُ التصفير {zero_sites} لا تساوي الحقولَ المُعلَنة "
        f"{len(om._DAILY_ZERO_COERCED_SOURCE_FIELDS)} — أُضيف تصفيرٌ بلا إعلان، أو أُزيل مُعلَن"
    )


def test_a_missing_daily_precipitation_is_none_not_dry():
    """المسارُ **اليوميّ** — لا الآنيّ وحدَه: مطرٌ مفقودٌ يبقى ``None``.

    كان `normalize_daily` يُصفّر `precipitation_sum` الغائب بإعلانٍ صريح، وكانت الحجّة
    أنّ «لا مطر» قراءةٌ معقولةٌ لصفرِ مجموعٍ يوميّ. **والمعقوليّةُ تعتمد على المستهلك**:
    معقولةٌ لعرضٍ على خريطة، وكاذبةٌ لكمّيّةِ ريٍّ يُطرَح منها المطرُ الأخير — فيرتفع
    الرقمُ الموصى به، والانحيازُ في اتّجاه **الإذن بالريّ**.

    وقد أُغلِق الطرفُ الآخر أوّلاً: مستهلكُ الريّ في المنصّة صار يفشل مغلقاً عند غياب
    المطر. **والتصفيرُ هنا كان يمنعه من أن يرى الغيابَ أصلاً** — حاجزٌ عند الحافّة
    يُبطِل فشلاً مُغلَقاً في النواة، فيمرّ الصفرُ المُختلَق عبر بوّابةٍ بُنِيت لتردّه.
    """
    out = om.normalize_daily(
        {"daily": {"time": ["2026-07-10"], "temperature_2m_max": [33.0]}},
        lat=24.7,
        lon=46.7,
        source="test",
        model="best_match",
    )
    assert out["days"][0]["precipitation_mm"] is None, "مطرٌ يوميٌّ مفقودٌ يُقرأ جفافاً"


def test_a_real_daily_zero_precipitation_stays_zero():
    """والاتّجاه الآخر: يومٌ **قِيس** بلا مطرٍ يبقى صفراً لا ``None``."""
    out = om.normalize_daily(
        {"daily": {"time": ["2026-07-10"], "precipitation_sum": [0.0]}},
        lat=24.7,
        lon=46.7,
        source="test",
        model="best_match",
    )
    assert out["days"][0]["precipitation_mm"] == 0.0


def test_a_missing_daily_wind_is_none_not_calm():
    """المسارُ **اليوميّ**: ريحٌ مفقودةٌ تبقى ``None`` — آخِرُ حقلٍ خرج من التصفير.

    كانت الحجّةُ أنّ «لا رياح» قراءةٌ معقولةٌ لصفرِ مجموعٍ يوميّ، وأنّ لا مستهلكَ يطرحها
    من كمّيّةٍ تُصدَر لمزارع. **والثانيةُ سقطت بالقياس:** `phase_runtime_workers.py:608`
    يمرّر `wind_max_ms` إلى `wind_2m_ms` في `get_et0_product`، و`et0_mm` يقود
    `compute_daily_ledger_entry`.

    والاتّجاهُ معكوسُ اتّجاه المطر: في Penman-Monteith يدخل `u2` بسطاً ومقاماً، فريحٌ
    صفرٌ **تُنقِص** ET0 ⇒ احتياجاً أقلّ ⇒ ريّاً دون الحاجة. والمطرُ كان يُغرِق؛ فالغيابُ
    المُقنَّع يكذب في الاتّجاهين.
    """
    out = om.normalize_daily(
        {"daily": {"time": ["2026-07-10"], "temperature_2m_max": [33.0]}},
        lat=24.7,
        lon=46.7,
        source="test",
        model="best_match",
    )
    assert out["days"][0]["wind_max_ms"] is None, "ريحٌ يوميّةٌ مفقودةٌ تُقرأ هدوءاً"
    assert out["days"][0]["wind_max_kmh"] is None


def test_a_real_daily_zero_wind_stays_zero():
    """والاتّجاه الآخر: يومٌ **قِيس** بلا ريحٍ يبقى صفراً لا ``None``.

    بدونه يكون العلاجُ قلبَ العطل: هدوءٌ حقيقيٌّ يُقرأ غياباً فيُسقِط الجودةَ بلا سبب.
    """
    out = om.normalize_daily(
        {"daily": {"time": ["2026-07-10"], "wind_speed_10m_max": [0.0]}},
        lat=24.7,
        lon=46.7,
        source="test",
        model="best_match",
    )
    assert out["days"][0]["wind_max_ms"] == 0.0
    assert out["days"][0]["wind_max_kmh"] == 0.0
