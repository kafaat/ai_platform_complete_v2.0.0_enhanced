#!/usr/bin/env python3
"""scripts/defect_signature_scan.py — ماسح بصمات العيوب (Defect Signatures).

يُفعِّل منهجيّة كشف العيوب بالأنماط (لا بقراءة كلّ ملفّ) كأداة قابلة لإعادة التشغيل +
بوّابة CI. يفحص البصمات الأكثر دلالةً على عيوب حقيقيّة، **بلا إيجابيّات كاذبة** (يفرّق
الـsignature الخطير عن النمط المشروع):

  1. except عريض صامت: `except Exception:` أو `except:` يتبعه مباشرةً pass/return None/
     continue **دون تعليق تبرير** على سطر except ⇒ يبتلع كلّ خطأ بصمت (يخفي عيوباً).
     (except الضيّق مثل OSError/ValueError/ImportError مشروع ⇒ لا يُبلَّغ.)
  2. except عارٍ بلا نوع: `except:` ⇒ يبتلع حتى SystemExit/KeyboardInterrupt.
  3. وهم التغطية: `assert True` / `assert 1 == 1` في الاختبارات ⇒ اختبار لا يثبت شيئاً.

يُرجِع رمز خروج 1 إن وُجدت بصمات (للبوّابة). الاستثناءات المشروعة تُوثَّق بتعليق
(`# noqa: BLE001 — السبب`) فتُستثنى — يحوّل الانضباط إلى فرض.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = ("services", "bots", "agents")

_BROAD_EXCEPT = re.compile(r"^\s*except(\s+Exception(\s+as\s+\w+)?)?\s*:\s*$")
_BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*$")
_SWALLOW_NEXT = {"pass", "return none", "return", "continue"}
_TRIVIAL_ASSERT = re.compile(r"^\s*assert\s+(True|1\s*==\s*1|1)\s*(#.*)?$")


def _is_test(path: pathlib.Path) -> bool:
    return path.name.startswith("test_") or "tests" in path.parts


def scan() -> list[str]:
    findings: list[str] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            lines = path.read_text(encoding="utf-8").splitlines()
            rel = path.relative_to(ROOT)
            for i, line in enumerate(lines):
                # 1/2: except عريض/عارٍ صامت بلا تبرير
                bare = _BARE_EXCEPT.match(line)
                broad = _BROAD_EXCEPT.match(line)
                if (bare or broad) and "#" not in line and not _is_test(path):
                    nxt = lines[i + 1].strip().lower() if i + 1 < len(lines) else ""
                    if nxt in _SWALLOW_NEXT:
                        kind = "bare-except" if bare else "broad-except-swallow"
                        findings.append(
                            f"{rel}:{i + 1}: {kind} يبتلع بصمت بلا تبرير "
                            f"(ضيّق النوع أو أضِف '# noqa: BLE001 — السبب')"
                        )
                # 3: وهم التغطية في الاختبارات
                if _is_test(path) and _TRIVIAL_ASSERT.match(line):
                    findings.append(f"{rel}:{i + 1}: assert تافه (وهم تغطية) — اختبر سلوكاً فعليّاً")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("✗ بصمات عيوب مكتشَفة:")
        for f in findings:
            print("  " + f)
        return 1
    print("✓ لا بصمات عيوب خطيرة")
    return 0


if __name__ == "__main__":
    sys.exit(main())
