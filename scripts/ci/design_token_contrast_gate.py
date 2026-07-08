#!/usr/bin/env python3
"""بوّابة تباين توكِنات التصميم (WCAG 2.1) — مُكيَّفة لساهول (مُلهَمة من قواعد impeccable).

تقرأ ألوان العلامة من ``frontend/src/components/ds/tokens.ts`` وتحسب نسبة التباين
(relative luminance) لأزواج «نصّ على سطح» الموثّقة. **سقّاطة صادقة:**

  • **حاجب (gate):** أزواج النصّ الأساسيّ على الأسطح يجب أن تحقّق WCAG AA (≥ 4.5:1).
    أخضر اليوم (ink على cream/card/card2 ≈ 15–16:1) — يمنع الانحدار لو أُظلِم سطح أو فُتِّح نصّ.
  • **إرشاديّ (لا يحجب):** أزواج ثانويّة/CTA (muted/faint/أبيض-على-تعبئة) تُطبَع بحكمها
    ونيّة استخدامها — تكشف نقاط الضعف المعروفة بلا كسر CI ولا تغيير هويّة بقرار أحاديّ.

منطق صرف حتميّ (لا شبكة/DOM). تُشغَّل ضمن وظيفة *Repository Structural Lint*.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "frontend" / "src" / "components" / "ds" / "tokens.ts"

# أزواج النصّ الأساسيّ (حاجبة): يجب ≥ AA-normal. المفتاح: (نصّ, سطح).
CRITICAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("ink", "cream"),
    ("ink", "card"),
    ("ink", "card2"),
    ("brown", "card"),
)
_AA_NORMAL = 4.5
_AA_LARGE = 3.0

# أزواج إرشاديّة: (نصّ, سطح, أدنى مقبول, نيّة الاستخدام). لا تحجب.
ADVISORY_PAIRS: tuple[tuple[str, str, float, str], ...] = (
    ("muted", "card", _AA_NORMAL, "نصّ ثانويّ — للملاحظات/large فقط إن < 4.5"),
    ("muted", "cream", _AA_NORMAL, "نصّ ثانويّ على خلفية الصفحة"),
    ("faint", "card", _AA_LARGE, "تلميحات خافتة — large فقط؛ تجنّبه لنصّ صغير"),
    ("white", "gold", _AA_NORMAL, "نصّ أبيض على CTA ذهبيّ — الأفضل نصّ داكن (ink) أو goldSoft"),
    ("white", "green", _AA_NORMAL, "نصّ أبيض على أخضر — استخدم greenDark لنصّ أبيض"),
    ("white", "greenDark", _AA_NORMAL, "وسم نجاح بنصّ أبيض"),
    ("white", "danger", _AA_NORMAL, "وسم خطر بنصّ أبيض"),
    ("white", "info", _AA_NORMAL, "وسم معلومة بنصّ أبيض — large فقط إن < 4.5"),
)


def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def parse_tokens(text: str) -> dict[str, str]:
    """يستخرج ``name -> #RRGGBB`` من ``export const T = {...}``. غير-الألوان تُتجاهَل."""
    out: dict[str, str] = {}
    for m in re.finditer(r"(\w+)\s*:\s*'(#[0-9A-Fa-f]{6})'", text):
        out[m.group(1)] = m.group(2).upper()
    # white ليس توكِناً معلَناً — نضيفه صراحةً (لون نصّ overlay شائع).
    out.setdefault("white", "#FFFFFF")
    return out


def run() -> int:
    if not TOKENS.exists():
        print(f"design-token-contrast-gate: SKIP — tokens غير موجود ({TOKENS})")
        return 0
    tokens = parse_tokens(TOKENS.read_text(encoding="utf-8"))

    failures: list[str] = []
    print("design-token-contrast-gate: أزواج النصّ على الأسطح (WCAG 2.1)")
    print(f"  {'الزوج':28} {'النسبة':>7}  الحاجب(≥4.5)")
    for fg, bg in CRITICAL_PAIRS:
        if fg not in tokens or bg not in tokens:
            failures.append(f"توكِن مفقود: {fg}/{bg}")
            continue
        r = contrast_ratio(tokens[fg], tokens[bg])
        ok = r >= _AA_NORMAL
        print(f"  {fg + ' على ' + bg:28} {r:>7}   {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"{fg} على {bg}: {r} < {_AA_NORMAL} (نصّ أساسيّ دون AA)")

    print("\n  إرشاديّ (لا يحجب — نقاط ضعف معروفة، راجع docs/design/contrast_audit.md):")
    for fg, bg, floor, note in ADVISORY_PAIRS:
        if fg not in tokens or bg not in tokens:
            continue
        r = contrast_ratio(tokens[fg], tokens[bg])
        mark = "✅" if r >= floor else "⚠️"
        print(f"    {mark} {fg + ' على ' + bg:24} {r:>6} (≥{floor}) — {note}")

    if failures:
        print("\ndesign-token-contrast-gate: FAIL — نصّ أساسيّ دون WCAG AA:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print(f"\ndesign-token-contrast-gate: PASS — {len(CRITICAL_PAIRS)} زوج نصّ أساسيّ ≥ AA (سقّاطة).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
