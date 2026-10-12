"""Bounded numeric/template consistency for Arabic critical quantity speech.

This is NOT agronomic validation, human review, ASR verification or a semantic
classifier. Only obvious numeral + dose-unit free text is detected; quantities
written as words and arbitrary units need upstream structured advice validation.
Critical slots render server-side from a template; no caller-supplied pronunciation
or 'verified' assertion is accepted. Bounds below limit representation complexity,
not safe doses. Preserve the rendered text through subsequent normalization.
"""

from __future__ import annotations

import re
from decimal import Decimal
from string import Formatter

_DIGITS = ("صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة")
_TEENS = (
    "عشرة",
    "أحد عشر",
    "اثنا عشر",
    "ثلاثة عشر",
    "أربعة عشر",
    "خمسة عشر",
    "ستة عشر",
    "سبعة عشر",
    "ثمانية عشر",
    "تسعة عشر",
)
_TENS = ("", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون")
_HUNDREDS = (
    "",
    "مائة",
    "مائتان",
    "ثلاثمائة",
    "أربعمائة",
    "خمسمائة",
    "ستمائة",
    "سبعمائة",
    "ثمانمائة",
    "تسعمائة",
)
_TRANSLATE_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_UNITS = {"ml": "مليلتر", "g": "غرام", "kg": "كيلوغرام", "l": "لتر"}
_BASIS_UNITS = {"l": "لتر", "m2": "متر مربع", "ha": "هكتار"}
# Include restricted household aliases in detection, but never convert them.
_UNIT_PATTERN = r"(?:ml|mL|kg|g|l|L|liters?|milliliters?|grams?|مل|مليلتر|لتر|غرام|جرام|كغ|كيلوغرام|ملعقة|ملاعق|teaspoons?|tablespoons?)"
_LITERAL_UNIT = re.compile(rf"(?<!\w){_UNIT_PATTERN}(?!\w)", re.IGNORECASE)
_CRITICAL_NUMBER = re.compile(
    rf"[0-9٠-٩۰-۹][0-9٠-٩۰-۹.,،٫\-–/\s]*{_UNIT_PATTERN}(?!\w)", re.IGNORECASE
)
_DOSE_LABEL_NUMBER = re.compile(
    r"(?:جرعة|فترة\s+ما\s+قبل\s+الحصاد|\bPHI\b|\bdose\b).*?[0-9٠-٩۰-۹]",
    re.IGNORECASE | re.DOTALL,
)
_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?\Z")
_KEYS = {"quantity", "unit", "basis_quantity", "basis_unit", "interval_days", "phi_days"}


class CriticalSpeechError(ValueError):
    """Input cannot satisfy the bounded structured speech contract."""


def _integer_words(value: int) -> str:
    if value < 10:
        return _DIGITS[value]
    if value < 20:
        return _TEENS[value - 10]
    if value < 100:
        tens, remainder = divmod(value, 10)
        return (_DIGITS[remainder] + " و" if remainder else "") + _TENS[tens]
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        return _HUNDREDS[hundreds] + (" و" + _integer_words(remainder) if remainder else "")
    divisor, singular, dual, plural = (
        (1000, "ألف", "ألفان", "آلاف")
        if value < 1000000
        else (1000000, "مليون", "مليونان", "ملايين")
    )
    group, remainder = divmod(value, divisor)
    leading = (
        singular
        if group == 1
        else dual
        if group == 2
        else _integer_words(group) + " " + (plural if group < 11 else singular)
    )
    return leading + (" و" + _integer_words(remainder) if remainder else "")


def _number_words(raw: str, *, allow_zero: bool = False, whole: bool = False) -> str:
    if not isinstance(raw, str) or len(raw) > 32:
        raise CriticalSpeechError("critical quantities must be bounded numeric strings")
    normalized = raw.translate(_TRANSLATE_DIGITS)
    if not _NUMBER.fullmatch(normalized):
        raise CriticalSpeechError(
            "use unambiguous decimal strings; commas, signs and ranges are unsupported"
        )
    number = Decimal(normalized)
    if number > Decimal("999999999") or number < 0 or (number == 0 and not allow_zero):
        raise CriticalSpeechError("critical quantity is outside representation bounds")
    if whole and "." in normalized:
        raise CriticalSpeechError("day counts must be whole numbers")
    integer, separator, fraction = normalized.partition(".")
    result = _integer_words(int(integer))
    if separator:
        # Deliberately preserve every fractional digit, including trailing zeroes.
        result += " فاصلة " + " ثم ".join(_DIGITS[int(digit)] for digit in fraction)
    return result


def prepare_critical_speech(text: str, slots: dict[str, str] | None = None) -> str:
    """Return speech text or reject obvious unsupported critical numeric speech.

    With slots, text must be a placeholder template: every supplied field exactly
    once, quantity/unit required, basis value/unit paired. No literal numbers or
    recognized dose units are allowed outside placeholders. General weather text
    without dose quantities is passed through unchanged. Never certifies a dose.
    """
    if not isinstance(text, str):
        raise CriticalSpeechError("speech text must be a string")
    if slots is None:
        if _CRITICAL_NUMBER.search(text) or _DOSE_LABEL_NUMBER.search(text):
            raise CriticalSpeechError("critical numeric speech requires structured quantity slots")
        return text
    if (
        not isinstance(slots, dict)
        or not {"quantity", "unit"} <= slots.keys()
        or slots.keys() - _KEYS
    ):
        raise CriticalSpeechError("critical slots require quantity/unit and only supported fields")
    if any(not isinstance(value, str) for value in slots.values()):
        raise CriticalSpeechError("critical slots must contain strings")
    if ("basis_quantity" in slots) != ("basis_unit" in slots):
        raise CriticalSpeechError("dose basis quantity and unit must be supplied together")
    if slots["unit"] not in _UNITS or (
        "basis_unit" in slots and slots["basis_unit"] not in _BASIS_UNITS
    ):
        raise CriticalSpeechError("unsupported critical quantity unit")
    try:
        parsed = list(Formatter().parse(text))
    except ValueError as exc:
        raise CriticalSpeechError("invalid critical speech template") from exc
    fields = [field for _, field, _, _ in parsed if field is not None]
    if len(fields) != len(slots) or set(fields) != set(slots):
        raise CriticalSpeechError("template must bind every supplied critical slot exactly once")
    if any(spec or conversion for _, _, spec, conversion in parsed):
        raise CriticalSpeechError("template formatting and conversions are unsupported")
    literal = "".join(part for part, _, _, _ in parsed)
    if re.search(r"[0-9٠-٩۰-۹]", literal) or _LITERAL_UNIT.search(literal):
        raise CriticalSpeechError("critical numbers and dose units must come from slots only")
    rendered = {"quantity": _number_words(slots["quantity"]), "unit": _UNITS[slots["unit"]]}
    if "basis_quantity" in slots:
        rendered["basis_quantity"] = _number_words(slots["basis_quantity"])
        rendered["basis_unit"] = _BASIS_UNITS[slots["basis_unit"]]
    for key in ("interval_days", "phi_days"):
        if key in slots:
            rendered[key] = _number_words(slots[key], allow_zero=key == "phi_days", whole=True)
    return text.format_map(rendered)
