"""arabic_normalizer.py — تطبيع النصّ العربيّ قبل تحويله إلى كلام (وحدة نقيّة).
================================================================================
وحدة **بلا تبعيّات ثقيلة ولا fastapi** — منطق صرف قابل للاستيراد والاختبار وحدويّاً.
تُحضّر النصّ العربيّ لمحرّكات TTS (edge/piper/xtts) تحضيراً حتميّاً (deterministic):

  • تجريد التطويل (tatweel ـ U+0640) — علامة تمديد بصريّة لا تُنطَق.
  • توحيد الألف (أ إ آ → ا) كوضع **اختياريّ** (unify_alef) — يبقى وضع أمين (faithful)
    افتراضاً كي لا نغيّر الإملاء ما لم يُطلَب صراحةً.
  • تطبيع الأرقام هندي↔لاتينيّ (٠-٩ ↔ 0-9) حسب علم digits.
  • تمرير الحركات (التشكيل) كما هي (basic diacritics passthrough) — لا تُحذَف.
  • توسيع وحدات/رموز شائعة إلى نطقها العربيّ (%، °C، mm، ha …) — مجموعة صغيرة
    موثّقة لا شاملة.
  • طيّ المسافات المتكرّرة إلى مسافة واحدة.

كلّ الخيارات معطّلة/آمنة بحيث تكون العمليّة حتميّة وقابلة للاختبار بالكامل. لا تُستدعى
تلقائيّاً في مسار التركيب الافتراضيّ (يبقى edge أمينَ-البايت) — تُفعَّل بطلب صريح.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── جداول التطبيع ────────────────────────────────────────────────────────────
_TATWEEL = "ـ"  # ـ علامة التطويل

# الألف بأشكالها المهموزة/الممدودة → ألف مجرّدة (وضع اختياريّ).
_ALEF_VARIANTS = {
    "أ": "ا",  # أ ألف همزة علوية
    "إ": "ا",  # إ ألف همزة سفلية
    "آ": "ا",  # آ ألف مدّة
}

# الأرقام العربيّة-الهنديّة ٠..٩ = U+0660..U+0669.
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"
_TO_ASCII = {ord(a): b for a, b in zip(_ARABIC_DIGITS, _ASCII_DIGITS, strict=True)}
_TO_ARABIC = {ord(b): a for a, b in zip(_ARABIC_DIGITS, _ASCII_DIGITS, strict=True)}

# مجموعة صغيرة موثّقة من الوحدات/الرموز → نطقها العربيّ. الترتيب مهمّ: الأطول أوّلاً
# (°C قبل °) كي لا يلتهم البديل الأقصر جزءاً من الأطول. الوحدات الحرفيّة تُطابَق
# بحدود لا-حرفيّة (يسبقها رقم أو فراغ، لا حرفٌ لاتينيّ/عربيّ) تفادياً لمطابقة داخل كلمة.
_SYMBOL_MAP = (
    ("°C", " درجة مئويّة "),
    ("°F", " درجة فهرنهايت "),
    ("°", " درجة "),
    ("%", " بالمئة "),
)
# وحدات حرفيّة (تُطابَق طرفيّاً بلا التصاق بحروف أخرى).
_UNIT_MAP = (
    ("mm", "مليمتر"),
    ("cm", "سنتيمتر"),
    ("km", "كيلومتر"),
    ("kg", "كيلوغرام"),
    ("ha", "هكتار"),
)
# حدّ لا-حرفيّ: ليس حرفاً لاتينيّاً ولا عربيّاً (يسمح بالرقم والفراغ وبداية/نهاية النصّ).
_LETTER = "A-Za-z؀-ۿ"


@dataclass(frozen=True)
class ArabicTextNormalizer:
    """مطبّع نصّ عربيّ حتميّ قابل للضبط. كلّ خيار مستقلّ وموثّق.

    الوسائط:
      strip_tatweel:      يجرّد التطويل (ـ). افتراضاً True (لا يغيّر النطق).
      unify_alef:         يوحّد أإآ→ا. افتراضاً False (وضع أمين للإملاء).
      digits:             "keep" | "ascii" | "arabic" — اتّجاه تطبيع الأرقام.
      expand_symbols:     يوسّع %، °C، mm … إلى نطقها العربيّ. افتراضاً True.
      collapse_whitespace:يطوي المسافات إلى واحدة ويقلّم الأطراف. افتراضاً True.
    """

    strip_tatweel: bool = True
    unify_alef: bool = False
    digits: str = "keep"
    expand_symbols: bool = True
    collapse_whitespace: bool = True

    def __post_init__(self) -> None:
        if self.digits not in {"keep", "ascii", "arabic"}:
            raise ValueError("digits يجب أن تكون 'keep' أو 'ascii' أو 'arabic'")

    def normalize(self, text: str) -> str:
        """يُرجِع النصّ مُطبَّعاً حسب الخيارات (حتميّ — لا عشوائيّة ولا حالة خارجيّة)."""
        if not text:
            return text
        out = text
        if self.strip_tatweel:
            out = out.replace(_TATWEEL, "")
        if self.unify_alef:
            for src, dst in _ALEF_VARIANTS.items():
                out = out.replace(src, dst)
        if self.expand_symbols:
            out = self._expand_symbols(out)
        out = self._normalize_digits(out)
        if self.collapse_whitespace:
            out = re.sub(r"\s+", " ", out).strip()
        return out

    # ── داخليّ ───────────────────────────────────────────────────────────────
    def _expand_symbols(self, text: str) -> str:
        out = text
        for sym, spoken in _SYMBOL_MAP:
            out = out.replace(sym, spoken)
        for unit, spoken in _UNIT_MAP:
            # لا يسبقها/يتبعها حرف (لكن يجوز رقم): «5mm» و«5 mm» تُطابَقان، «hammer» لا.
            pattern = rf"(?<![{_LETTER}]){re.escape(unit)}(?![{_LETTER}])"
            out = re.sub(pattern, f" {spoken} ", out)
        return out

    def _normalize_digits(self, text: str) -> str:
        if self.digits == "ascii":
            return text.translate(_TO_ASCII)
        if self.digits == "arabic":
            return text.translate(_TO_ARABIC)
        return text
