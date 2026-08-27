"""عيّنةٌ غائبة تُنتِج حكماً صادقاً، لا انهياراً — ولا نافذةً زائفة.

**العطلُ المقيس (P3):** `tile_data` يُرجِع دائماً المفتاح `"sample"`، وقيمتُه
`None` عند تدهور المزوّد بلا مخبّأ. و`operation_tile_data` يُمرّرها إلى
`operation_suitability` بلا حراسة. و`_num` يحمي من **قيمةٍ** فاسدة
(`except TypeError, ValueError`) لا من **عيّنةٍ** غائبة — فـ`None.get` كان يرفع
`AttributeError` غيرَ ملتقَط ⇒ **500** على نقطةٍ عامّة كلّما تعطّل المزوّد.

**ولمَ لم يُمسَك:** التشخيصُ الشائع أنّ `payload["sample"]` يرفع `KeyError`.
وهو **خاطئ** — المفتاح حاضرٌ دائماً. فحراسةُ المفتاح في موضع النداء ما كانت
لتُصلِح شيئاً؛ العلاجُ في `operation_suitability` نفسِها.

**والخاصّيّةُ التي تُحرَس هنا ليست «لا ينهار»** — بل أنّ الجوابَ يبلغ آليّةَ
الفشل المغلق القائمة فيُنتِج `score = 0.0` بأسبابه المسمّاة. فحارسٌ يُرجِع
درجةً صالحةً عن مُدخَلٍ غائب أخطرُ من انهيار: نافذةُ رشٍّ زائفةٌ تُقرأ إذناً.
"""

from __future__ import annotations

import pytest
from operations import operation_suitability

_COMPLETE = {
    "temperature_c": 25.0,
    "humidity_pct": 40.0,
    "wind_speed_10m_kmh": 5.0,
    "precipitation_mm": 0.0,
}


@pytest.mark.unit
@pytest.mark.parametrize("absent", [None, {}])
def test_an_absent_sample_fails_closed_instead_of_raising(absent) -> None:
    """`None` و`{}` كلاهما «لا قياس» — ولا يفترقان في الحكم."""
    out = operation_suitability(absent, "spraying")

    assert out["score"] == 0.0, "مُدخَلُ سلامةٍ غائب أنتج درجةً غيرَ صفريّة"
    assert out["status"] == "insufficient_data"


@pytest.mark.unit
def test_the_refusal_names_which_safety_input_was_missing() -> None:
    """«صفر» بلا سبب يُقرأ حكماً سالباً؛ والسببُ يفصله عن «مقيسٌ فسيّئ»."""
    out = operation_suitability(None, "spraying")

    assert out["limiting_factors"], "رفضٌ بلا عاملٍ مُسمًّى"
    assert any("missing" in str(f) for f in out["limiting_factors"])


@pytest.mark.unit
def test_a_complete_sample_still_scores_so_the_guard_is_not_a_blanket_refusal() -> None:
    """الطرفُ الآخر: لو رفض كلَّ شيءٍ لصار الإصلاحُ تعطيلاً للنقطة."""
    out = operation_suitability(_COMPLETE, "spraying")

    assert out["score"] > 0.0
    assert out["status"] != "insufficient_data"


@pytest.mark.unit
def test_every_supported_operation_survives_an_absent_sample() -> None:
    """الحراسةُ في المدخل الواحد، فتغطّي الأفعالَ كلَّها — يُقاس لا يُفترَض."""
    from operations import SUPPORTED_OPERATIONS

    for op in SUPPORTED_OPERATIONS:
        out = operation_suitability(None, op)
        assert out["score"] == 0.0, f"{op} أنتج درجةً غيرَ صفريّة عن عيّنةٍ غائبة"
