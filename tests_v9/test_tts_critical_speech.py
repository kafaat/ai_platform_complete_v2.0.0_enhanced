"""Bounded critical numeric speech: no network or synthetic safety assertion."""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "tts-service"))
from critical_speech import CriticalSpeechError, prepare_critical_speech  # noqa: E402


def render(value, **extra):
    slots = {"quantity": value, "unit": "ml", **extra}
    return prepare_critical_speech("المقدار {quantity} {unit}", slots)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.75", "صفر فاصلة سبعة ثم خمسة"),
        ("75", "خمسة وسبعون"),
        ("2.5", "اثنان فاصلة خمسة"),
        ("25", "خمسة وعشرون"),
        ("٠٫٧٥", "صفر فاصلة سبعة ثم خمسة"),
        ("۲٫۵", "اثنان فاصلة خمسة"),
    ],
)
def test_fractional_quantity_preserves_zero_and_decimal(raw, expected):
    assert render(raw) == "المقدار " + expected + " مليلتر"


def test_fractional_trailing_zero_is_not_silently_lost():
    assert "خمسة ثم صفر" in render("0.50")


@pytest.mark.parametrize(
    "value",
    [
        "0,75",
        "0،75",
        "1-2",
        "1/2",
        "NaN",
        "Infinity",
        "1e3",
        "-1",
        "+1",
        "01",
        " 1",
        "0",
        "1000000000",
        "1.1234567",
        0.75,
        True,
    ],
)
def test_ambiguous_unbounded_and_nonstring_quantities_rejected(value):
    with pytest.raises(CriticalSpeechError):
        render(value)


@pytest.mark.parametrize(
    "text",
    [
        "استخدم 0.75 مل",
        "Use 2.5 ml",
        "أضف ٧٥ غرام",
        "استخدم 1 ملعقة",
        "جرعة المنتج ٢",
        "PHI is 7 days",
        "PHI\n14 يوم",
        "فترة ما قبل الحصاد:\n14 يوم",
        "جرعة المنتج:\n٢",
    ],
)
def test_obvious_freeform_critical_number_requires_slots(text):
    with pytest.raises(CriticalSpeechError):
        prepare_critical_speech(text)


@pytest.mark.parametrize(
    "text",
    ["درجة الحرارة 25 مئوية", "المطر 12 مم", "الرياح 20 km/h", "توقع المطر غداً", "الحقل رقم 75"],
)
def test_general_weather_and_reference_numbers_remain_compatible(text):
    assert prepare_critical_speech(text) == text


@pytest.mark.parametrize(
    "template,slots",
    [
        ("المقدار {quantity} {unit}", {"quantity": "1", "unit": "spoon"}),
        ("المقدار {quantity} {unit}", {"quantity": "1", "unit": "ml", "verified": "true"}),
        ("المقدار {quantity} {unit}", {"quantity": "1", "unit": "ml", "basis_quantity": "10"}),
        (
            "المقدار {quantity} {unit}",
            {"quantity": "1", "unit": "ml", "basis_quantity": "10", "basis_unit": "l"},
        ),
        ("المقدار {quantity} لتر", {"quantity": "1", "unit": "ml"}),
        ("المقدار {quantity} {unit} ثم 25 مل", {"quantity": "1", "unit": "ml"}),
        ("المقدار {quantity} {unit} لكل لتر", {"quantity": "1", "unit": "ml"}),
        ("المقدار {quantity} {quantity} {unit}", {"quantity": "1", "unit": "ml"}),
        ("المقدار {quantity!r} {unit}", {"quantity": "1", "unit": "ml"}),
        ("المقدار {quantity:.0f} {unit}", {"quantity": "1", "unit": "ml"}),
    ],
)
def test_missing_extra_inconsistent_and_self_asserted_fields_rejected(template, slots):
    with pytest.raises(CriticalSpeechError):
        prepare_critical_speech(template, slots)


def test_basis_and_supplied_time_fields_render_without_invention():
    text = "المقدار {quantity} {unit} لكل {basis_quantity} {basis_unit}، الفاصل {interval_days} أيام، انتظار الحصاد {phi_days} أيام"
    slots = {
        "quantity": "0.75",
        "unit": "ml",
        "basis_quantity": "10",
        "basis_unit": "l",
        "interval_days": "7",
        "phi_days": "0",
    }
    spoken = prepare_critical_speech(text, slots)
    assert (
        spoken
        == "المقدار صفر فاصلة سبعة ثم خمسة مليلتر لكل عشرة لتر، الفاصل سبعة أيام، انتظار الحصاد صفر أيام"
    )


@pytest.mark.parametrize(
    "key,value", [("interval_days", "0"), ("interval_days", "2.5"), ("phi_days", "2.0")]
)
def test_day_counts_require_nonnegative_whole_strings(key, value):
    with pytest.raises(CriticalSpeechError):
        prepare_critical_speech(
            "المقدار {quantity} {unit}، المدة {" + key + "} أيام",
            {"quantity": "1", "unit": "ml", key: value},
        )


# S12: محارف غير مرئية وتطويل وأشكال أرقام بديلة لا تعبر بجرعة حرة من البوابة.
@pytest.mark.parametrize(
    "variant,text",
    [
        ("tatweel_in_unit", "استخدم 0.75 مـل"),
        ("tatweel_in_label", "جـرعة المنتج ٢"),
        ("zwsp_after_number", "استخدم 0.75\u200b مل"),
        ("zwsp_before_unit", "استخدم 0.75 \u200bمل"),
        ("zwj_in_unit", "Use 2.5 m\u200dl"),
        ("zwnj_in_unit", "Use 2.5 m\u200cl"),
        ("rlm_between_number_unit", "استخدم ٧٥\u200fمل"),
        ("lrm_in_label", "PH\u200eI is 7 days"),
        ("word_joiner", "Use 2.5 \u2060ml"),
        ("bom", "Use 2.5\ufeff ml"),
        ("bidi_embedding", "استخدم \u202b0.75\u202c مل"),
        ("bidi_isolate", "استخدم \u20660.75\u2069 مل"),
        ("arabic_letter_mark", "جر\u061cعة المنتج 2"),
        ("harakat_in_unit", "استخدم 25 م\u0650ل"),
        ("fullwidth_digit", "Use \uff12 ml"),
        ("superscript_digit", "استخدم \u2077 مل"),
        ("bengali_digit", "Use \u09ed ml"),
        ("eastern_arabic_indic_control", "أضف ۷۵ غرام"),
    ],
)
def test_invisible_and_variant_characters_do_not_bypass_dose_gate(variant, text):
    with pytest.raises(CriticalSpeechError):
        prepare_critical_speech(text)


@pytest.mark.parametrize(
    "template",
    [
        "المقدار {quantity} {unit} لكل لـتر",
        "المقدار {quantity} {unit} لكل ل\u200bتر",
        "المقدار {quantity} {unit} ثم \uff12",
    ],
)
def test_template_literals_are_checked_on_normalized_view(template):
    with pytest.raises(CriticalSpeechError):
        prepare_critical_speech(template, {"quantity": "1", "unit": "ml"})


def test_passing_text_is_spoken_as_original_not_normalized_view():
    text = "توقع المطر غـدا \u200fمساء"
    assert prepare_critical_speech(text) == text
