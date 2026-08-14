#!/usr/bin/env python3
"""Guard: vapour-pressure / ET0 formulas live only in the Weather Engine (WS-C.1b boundary).

قرار المستخدم: بعد توحيد VPD/ET0 على البدائيّات المشتركة، يُمنع أيّ **تنفيذ جديد** لصيغة
ضغط البخار المشبع (Tetens/FAO-56 Eq.11) أو نواة Penman-Monteith/Hargreaves خارج محرّك
الطقس — فلا تنتشر الصيغة وتنجرف بصمت. **الإغلاق الكامل تحقّق (Zero-Legacy LOCKED):** كلّ
نوى ET0 في المنصّة رُحِّلت لاستهلاك منتج المحرّك، و``temporary_legacy_allowlist`` فُرِّغت
وأُقفِلت — إعادة إضافة أيّ مدخل إرثيّ = فشل CI بالتصميم (الرَّاتشِت النهائيّ).

يمزج فحصاً نصّيّاً للبصمة الرياضيّة مع فحص AST لتعريفات الدوالّ (لا Regex فقط):
  • بصمة SVP النصّيّة: ملفّ يحوي كلا الثابتين ``0.6108`` و``17.27``.
  • AST: تعريف دالّة ``_svp`` / يحوي ``penman_monteith`` / ``hargreaves`` في الاسم.

المسموح: القانونيّ (``services/weather-service/*``) + **allowlist مؤقّتة موثَّقة**
(``docs/architecture/weather_engine_formula_allowlist.json``: path/owner/expires/purpose).
أيّ ملفّ آخر (عدا الاختبارات) ⇒ CI أحمر. تُحذف مدخلات الـallowlist عند ترحيل المستهلكين
(حينها يصير وجود الصيغة في الملفّ القديم فشلاً — هذا الرَّاتشِت المقصود).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST = _ROOT / "docs" / "architecture" / "weather_engine_formula_allowlist.json"

_WEATHER_ENGINE_PREFIX = "services/weather-service/"
_SVP_MARKERS = ("0.6108", "17.27")
# بصمة Hargreaves-Samani الرياضيّة (WS-C.1b): المعامل 0.0023 + إزاحة الحرارة 17.8 معاً
# = تنفيذ Hargreaves مضمّن (سطريّ) بصرف النظر عن اسم الدالّة — يمسك الانجراف الذي
# يفلت من مطابقة الاسم (مثل نواة ET0 مضمّنة داخل خادم MCP).
_HARGREAVES_MARKERS = ("0.0023", "17.8")
# نوى GDD اليوميّة (WS-C.1c): تعريف دالّة بأحد هذه الأسماء = نواة حساب GDD مستقلّة.
# السياسة (عتبات/جداول محاصيل بلا دالّة نواة) لا تُكتشَف — مسموحة داخل Season.
_GDD_KERNEL_NAMES = ("gdd_daily", "daily_gdd", "gdd_day")


def _load_allowlist() -> tuple[str, set[str]]:
    cfg = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
    canonical = cfg["canonical"]
    legacy = {e["path"] for e in cfg.get("temporary_legacy_allowlist", [])}
    return canonical, legacy


def _has_svp_fingerprint(text: str) -> bool:
    return all(m in text for m in _SVP_MARKERS)


def _has_hargreaves_fingerprint(text: str) -> bool:
    return all(m in text for m in _HARGREAVES_MARKERS)


def _defines_weather_formula(text: str) -> bool:
    """AST: تعريف دالّة تُطبِّق صيغة ضغط بخار/ET0/GDD (بالاسم) — أمتن من Regex.

    يكشف نواة الحساب لا السياسة: ``_svp``/``penman_monteith``/``hargreaves`` (C.1a/b) و
    ``gdd_daily``/``daily_gdd``/``gdd_day`` (C.1c). جداول العتبات/سياسة المحصول (بلا
    دالّة نواة) لا تُكتشَف — مسموحة داخل Season.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name.lower()
            # ``hargreaves`` كسلسلة فرعيّة (لا startswith) ⇒ يمسك الأغلفة المفوِّضة أيضاً
            # (``_hargreaves_et0``/``et0_hargreaves``) فلا يفلت مسار ET0 من الرصد.
            if name == "_svp" or "penman_monteith" in name or "hargreaves" in name:
                return True
            if name in _GDD_KERNEL_NAMES:
                return True
    return False


def scan() -> tuple[list[str], bool]:
    canonical, legacy = _load_allowlist()
    allowed = {canonical, *legacy}
    violations: list[str] = []
    canonical_ok = False
    for p in _ROOT.rglob("*.py"):
        rel = p.relative_to(_ROOT).as_posix()
        if "__pycache__" in rel or "/tests/" in rel or Path(rel).name.startswith("test_"):
            continue
        if not rel.startswith(("services/", "bots/", "agents/")):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # محرّك الطقس مسموح دائماً (المالك القانونيّ للصيغة).
        if rel.startswith(_WEATHER_ENGINE_PREFIX):
            if rel == canonical and _has_svp_fingerprint(text):
                canonical_ok = True
            continue
        hit = (
            _has_svp_fingerprint(text)
            or _has_hargreaves_fingerprint(text)
            or _defines_weather_formula(text)
        )
        if hit and rel not in allowed:
            violations.append(rel)
    return violations, canonical_ok


def main() -> int:
    violations, canonical_ok = scan()
    if not canonical_ok:
        print(
            "weather-engine-formula-guard: canonical vapor_pressure.py lost the SVP fingerprint",
            file=sys.stderr,
        )
        return 1
    if violations:
        print(
            "weather-engine-formula-guard: SVP/ET0/GDD kernel outside the Weather Engine and not "
            "on the temporary allowlist (add it via services/weather-service; do NOT re-implement "
            "— crop base/cutoff/stage policy belongs in Season, the daily kernel in the engine):"
            "\n  " + "\n  ".join(sorted(violations)),
            file=sys.stderr,
        )
        return 1
    _, legacy = _load_allowlist()
    # WS-C.1c Zero-Legacy LOCK: بعد ترحيل كلّ نوى ET0 للمحرّك وإفراغ allowlist، يُقفَل بابها.
    # أيّ إعادة إضافة مدخل إرثيّ = فشل (لا نواة صيغة جديدة خارج المحرّك، ولا استثناء «مؤقّت»).
    if legacy:
        print(
            "weather-engine-formula-guard: Zero-Legacy is LOCKED — the temporary allowlist must "
            "stay empty. A new legacy SVP/ET0/GDD kernel outside the Weather Engine is not "
            f"permitted (offending entries: {sorted(legacy)}). Implement it in "
            "services/weather-service and consume the product; do NOT re-add an allowlist entry.",
            file=sys.stderr,
        )
        return 1
    assert len(legacy) == 0, "Zero-Legacy invariant violated (temporary_legacy_allowlist non-empty)"
    print("weather_engine_formula_guard_ok (canonical + 0 temporary-legacy — Zero-Legacy LOCKED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
