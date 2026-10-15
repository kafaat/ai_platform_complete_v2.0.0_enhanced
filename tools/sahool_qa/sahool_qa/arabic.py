"""Arabic text helpers: option letters, number/range formatting, digit
conversion and normalisation used for de-duplication and scoring."""
from __future__ import annotations

import math
import re

LETTERS = ["أ", "ب", "ج", "د", "هـ"]
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
          "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_TO_WESTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def nice_width(raw: float) -> float:
    """Round a raw bin width to 1, 2, 2.5 or 5 × 10^k."""
    if raw <= 0:
        return 1.0
    k = math.floor(math.log10(raw))
    base = raw / 10 ** k
    for m in (1, 2, 2.5, 5, 10):
        if base <= m * 1.0001:
            return m * 10 ** k
    return 10 ** (k + 1)


def decimals_for(width: float) -> int:
    for d in range(0, 5):
        if abs(round(width, d) - width) < 1e-9 and abs(width * 10 ** d - round(width * 10 ** d)) < 1e-9:
            return d
    return 4


def fmt(x: float, decimals: int = 0) -> str:
    if decimals == 0:
        return f"{int(round(x)):,}"
    return f"{x:,.{decimals}f}"


def fmt_range(lo: float, hi: float, unit: str, decimals: int) -> str:
    """'45-55 هكتار'. An ASCII hyphen with no spaces keeps the range in reading
    order inside right-to-left text (Unicode bidi rule W4); an en dash does not."""
    if unit == "%":
        return f"{fmt(lo, decimals)}-{fmt(hi, decimals)}%"
    return f"{fmt(lo, decimals)}-{fmt(hi, decimals)} {unit}".strip()


LRI, PDI = "\u2066", "\u2069"          # Unicode left-to-right isolate / pop isolate
_BIDI_CONTROLS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def ltr_isolate(s: str) -> str:
    """Wrap a coordinate list etc. so RTL renderers cannot reorder it."""
    return f"{LRI}{s}{PDI}"


_PROTECT = re.compile(r"«[^»]*»|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|[A-Za-z_][A-Za-z0-9_\-./]*")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def to_arabic_digits(s: str) -> str:
    """Render numbers with Arabic-Indic digits (٫ decimal, ٬ thousands).

    Left untouched so agents can still look values up: anything inside «»,
    ISO dates/timestamps, and tokens that start with a Latin letter or '_'
    (C1, SA-3, water_ec_W1, dS/m). Options that are identifiers (sample ids,
    field names) are skipped by the caller."""
    def conv(m):
        return m.group(0).replace(".", "٫").replace(",", "٬").translate(_AR_DIGITS)
    out, pos = [], 0
    for m in _PROTECT.finditer(s):
        out.append(_NUM.sub(conv, s[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_NUM.sub(conv, s[pos:]))
    return "".join(out)


def normalize(s: str) -> str:
    """Normalisation for matching: no diacritics/tatweel, unified alef/yaa/taa
    marbuta, Western digits and separators, collapsed whitespace."""
    s = _BIDI_CONTROLS.sub("", str(s)).translate(_TO_WESTERN).replace("٫", ".").replace("٬", ",")
    s = s.replace("–", "-").replace("—", "-") if re.search(r"\d[–]\d", s) else s
    s = _TASHKEEL.sub("", s)
    s = re.sub("[إأآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = s.replace("«", "").replace("»", "").replace("“", "").replace("”", "").replace('"', "")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def quote(name: str) -> str:
    return f"«{name}»"
