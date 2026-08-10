#!/usr/bin/env python3
"""حارس تغطية مفتاح الإيقاف لمواضع الإطلاق الفيزيائيّ (كشف بموضع الاستدعاء لا بالنصّ).

`physical_effect_boundary_guard` يرصد **ملفّاً** يبلغ الوسيط، لا **دالّةً** تُطلِق أمراً
دون فحص المفتاح. فمسار التعويض `_compensate` يستدعي المُساعِد `send_mqtt_command` بلا
`is_actuation_halted` (عيب COMPENSATION-BYPASSES-KILLSWITCH-01) — ومرّ لأنّ الحارس السابق
يفحص النصّ (`mqtt.publish(`) لا موضع الاستدعاء.

هذا الحارس يسدّ ذلك العمى: يجمع كلّ **استدعاء** لـ`send_mqtt_command` في كود الإنتاج،
ويتحقّق أنّ الدالّة الحاوية تستشير `is_actuation_halted`. أيّ موضع إطلاق **جديد** بلا
تغطية ⇒ CI يسقط. والعيب المجمَّد الحاليّ (`_compensate`) مُسجَّل صراحةً كـ**دَين معلَن**
مربوط بمعرّف فجوته وببوّابة GATE-01 — فلا يكسر CI ولا يُفرَض إصلاحه المجمَّد.

**إنفاذ عكسيّ:** حين تهبط رقعة M-01 (بعد فتح GATE-01) وتصير الدالّة مُغطّاة، يصير
الاستثناء بائتاً ⇒ الحارس يسقط ويُطالِب بنزعه. فلا يبقى ترخيصٌ ميّت يُخفي انحداراً لاحقاً.

الفحص على الكود المُنفَّذ عبر AST: تُجرَّد docstrings/التعليقات ضمنيّاً (نبحث عن عُقَد
`ast.Call`، لا نصّ)، فلا إيجابيّة كاذبة من توثيقٍ يذكر الرمز.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# المُساعِد الذي ينشر الأمر الفيزيائيّ فعلاً — الاستدعاء (لا التعريف) هو ما يُحرَس.
EMITTER = "send_mqtt_command"
# المفتاح الذي يجب أن تستشيره الدالّة الحاوية قبل الإطلاق.
KILLSWITCH = "is_actuation_halted"

# مواضع إطلاق مكشوفة معروفة ومجمَّدة خلف GATE-01 — دَين معلَن، لا تغطية صامتة.
# المفتاح (rel_path, function_name) ⇒ معرّف الفجوة. يُنزَع فور هبوط الرقعة (إنفاذ عكسيّ).
FROZEN_EXCEPTIONS: dict[tuple[str, str], str] = {
    (
        "services/actuator-service/actuator_runtime.py",
        "_compensate",
    ): "COMPENSATION-BYPASSES-KILLSWITCH-01",
}

_SKIP_DIR_PARTS = {"__pycache__", ".venv", "node_modules", "site-packages", ".git"}


def _callee_name(node: ast.Call) -> str | None:
    """اسم المُستدعى: `send_mqtt_command(...)` أو `x.send_mqtt_command(...)`."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _calls_name(scope: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Call) and _callee_name(n) == name for n in ast.walk(scope))


def _enclosing_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def analyze(sources: dict[str, str], exceptions: dict[tuple[str, str], str]):
    """منطق نقيّ قابل للاختبار بمعطياتٍ مُركَّبة (لا يقرأ القرص).

    يُرجِع (uncovered_unregistered, stale_exceptions):
      - uncovered_unregistered: [(rel, func)] مواضع إطلاق بلا مفتاح وغير مُسجَّلة.
      - stale_exceptions: [(rel, func)] استثناءات مُسجَّلة صارت مُغطّاة ⇒ تُنزَع.
    """
    uncovered_unregistered: list[tuple[str, str]] = []
    covered_exception_funcs: set[tuple[str, str]] = set()

    for rel, code in sorted(sources.items()):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for fn in _enclosing_functions(tree):
            # هل تُطلِق هذه الدالّة أمراً عبر المُساعِد؟ (استدعاء لا تعريف)
            emits = any(
                isinstance(n, ast.Call)
                and _callee_name(n) == EMITTER
                and fn.name != EMITTER  # تعريف المُساعِد نفسه ليس موضع إطلاق
                for n in ast.walk(fn)
            )
            if not emits:
                continue
            covered = _calls_name(fn, KILLSWITCH)
            key = (rel, fn.name)
            if covered:
                if key in exceptions:
                    covered_exception_funcs.add(key)
                continue
            # غير مُغطّاة:
            if key not in exceptions:
                uncovered_unregistered.append(key)

    stale = sorted(covered_exception_funcs)
    return sorted(uncovered_unregistered), stale


def _production_sources() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted((ROOT / "services").rglob("*.py")):
        parts = set(path.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        rel = path.relative_to(ROOT).as_posix()
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{rel}":
            continue
        try:
            out[rel] = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return out


def check() -> list[str]:
    uncovered, stale = analyze(_production_sources(), FROZEN_EXCEPTIONS)
    errors: list[str] = []
    for rel, fn in uncovered:
        errors.append(
            f"إطلاق فيزيائيّ بلا مفتاح إيقاف: {rel}::{fn}() يستدعي {EMITTER} دون "
            f"{KILLSWITCH} في نطاقها — أضِف الفحص، أو سجّله دَيناً معلَناً بمعرّف فجوة "
            "في FROZEN_EXCEPTIONS إن كان مجمَّداً خلف بوّابة."
        )
    for rel, fn in stale:
        gap = FROZEN_EXCEPTIONS.get((rel, fn), "?")
        errors.append(
            f"استثناء مجمَّد بائت: {rel}::{fn}() صار يستشير {KILLSWITCH} — انزع إدخال "
            f"{gap} من FROZEN_EXCEPTIONS؛ الترخيص الميّت يُخفي انحداراً لاحقاً."
        )
    return errors


def main() -> int:
    # لا يُعلَن علم `--check`: التحقّق يجري عبر الاختبار (يستدعي check())، لا خطوة
    # `--check` في workflow — فإعلانه يُوهِم مكنسة verify_all_generated بمولّد غير موصول.
    parser = argparse.ArgumentParser(description="حارس تغطية مفتاح الإيقاف (الافتراضيّ: افحص)")
    parser.add_argument("--list", action="store_true", help="اعرض مواضع الإطلاق المرصودة")
    args = parser.parse_args()

    if args.list:
        uncovered, stale = analyze(_production_sources(), FROZEN_EXCEPTIONS)
        for rel, fn in uncovered:
            print(f"uncovered  {rel}::{fn}")
        for (rel, fn), gap in sorted(FROZEN_EXCEPTIONS.items()):
            print(f"frozen-debt {rel}::{fn}  [{gap}]")
        for rel, fn in stale:
            print(f"stale-exc  {rel}::{fn}")
        return 0

    errors = check()
    if errors:
        print("actuation_killswitch_coverage_guard_failed")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    n = len(FROZEN_EXCEPTIONS)
    print(f"actuation_killswitch_coverage_guard_ok (دَين مجمَّد معلَن: {n})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
