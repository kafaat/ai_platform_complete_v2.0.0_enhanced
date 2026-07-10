#!/usr/bin/env python3
"""Guard: vapour-pressure / ET0 formulas live only in the Weather Engine (WS-C.1b boundary).

قرار المستخدم: بعد توحيد VPD/ET0 على البدائيّات المشتركة، يُمنع أيّ **تنفيذ جديد** لصيغة
ضغط البخار المشبع (Tetens/FAO-56 Eq.11) أو نواة Penman-Monteith/Hargreaves خارج محرّك
الطقس — فلا تنتشر الصيغة وتنجرف بصمت. الحارس يمنع الانتشار الآن؛ **الإغلاق الكامل** لـ
C.1b (تفويض المنصّة + shadow + حذف الإرث) خطوات تالية.

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

_ROOT = Path(__file__).resolve().parents[2]
_ALLOWLIST = _ROOT / "docs" / "architecture" / "weather_engine_formula_allowlist.json"

_WEATHER_ENGINE_PREFIX = "services/weather-service/"
_SVP_MARKERS = ("0.6108", "17.27")


def _load_allowlist() -> tuple[str, set[str]]:
    cfg = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
    canonical = cfg["canonical"]
    legacy = {e["path"] for e in cfg.get("temporary_legacy_allowlist", [])}
    return canonical, legacy


def _has_svp_fingerprint(text: str) -> bool:
    return all(m in text for m in _SVP_MARKERS)


def _defines_et0_formula(text: str) -> bool:
    """AST: تعريف دالّة تُطبِّق صيغة ET0/SVP (بالاسم) — أمتن من Regex."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name.lower()
            if name == "_svp" or "penman_monteith" in name or name.startswith("hargreaves"):
                return True
    return False


def scan() -> tuple[list[str], bool]:
    canonical, legacy = _load_allowlist()
    allowed = {canonical, *legacy}
    violations: list[str] = []
    canonical_ok = False
    for p in _ROOT.rglob("*.py"):
        rel = str(p.relative_to(_ROOT))
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
        hit = _has_svp_fingerprint(text) or _defines_et0_formula(text)
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
            "weather-engine-formula-guard: SVP/ET0 formula outside the Weather Engine and not on "
            "the temporary allowlist (add ET0 via weather-service; do NOT re-implement):\n  "
            + "\n  ".join(sorted(violations)),
            file=sys.stderr,
        )
        return 1
    _, legacy = _load_allowlist()
    print(
        f"weather_engine_formula_guard_ok (canonical + {len(legacy)} temporary-legacy allowlisted)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
