#!/usr/bin/env python3
"""أهدافُ الكتابة المولَّدة — `CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01`.

**المعيارُ «يكتبه مولّد»، لا «يُذكَر في مولّد».** والفرقُ مقيس، لا لفظيّ: مسحُ
الذكر النصّيّ يعطي مئتين وتسعة عشر مساراً، ومنها
`docs/architecture/guard_mutation_registry.json` — وثيقةُ سياسةٍ **بخطّ اليد**
يقرؤها المحرّك ولا يكتبها. وتصنيفُها «مولَّدة» يعني في حلّ التعارض «خُذ جانب
main ثمّ أعِد التوليد»، أي **إتلاف طفراتٍ مكتوبة**. فالاشتقاق النصّيّ كان
سيُنتِج عطلاً أسوأ من الوقوف الذي جاء ليُصلحه.

**والاشتقاق ساكن — وهذا تصحيحٌ لتصميمٍ أوّل عندي.** بدأتُ بقياسٍ ديناميكيّ: شغّل
المكنسة وارصد ما تغيّر زمنُ كتابته. وكان يعمل، لكنّه ورث كلّ هشاشتها — خمسَ عشرة
دقيقة، ورفضٌ لأيّ ملفٍّ غير مُفهرَس، **وكسرٌ لنقطة الثبات نفسها**: أداةٌ تُعلن
`--generate` ولا تعرفها المكنسة تجعلها لا تستقرّ، فيصير القياس على شجرةٍ لا
تثبت. المقيس: المكنسة لم تبلغ الثبات في ثلاث دورات معه، وبلغته في **دورةٍ واحدة**
بعد إزالته.

فالاشتقاق هنا من **شجرة الصياغة**: مسارٌ ثابتٌ يُمرَّر إلى عمليّة كتابة. لا يُشغِّل
شيئاً، ويتمّ في جزءٍ من الثانية.

**وحدُّه مُعلَنٌ لا مُخفى:** مسارٌ يُبنى في وقت التشغيل (حلقة، أو اسمٌ من وسيط)
لا يُرى هنا. ولذلك تبقى `GENERATED_MARKERS` في المُصنِّف — البيان **يُضيف** ولا
يستبدل، والاتّجاه الخطر (ملفٌّ يتوقّف عن كونه مولَّداً) تحرسه قائمةُ منعٍ تعلوه.

    python scripts/ci/generated_write_targets.py --generate
    python scripts/ci/generated_write_targets.py --check
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "architecture" / "generated_write_targets.json"

#: أسماءُ عمليّات الكتابة. `read_text` ليست منها — وهو الفرق كلُّه.
WRITE_METHODS = {"write_text", "write_bytes"}


def _tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    ).stdout
    return {line for line in out.splitlines() if line.strip()}


def _literal_path(node: ast.AST, consts: dict[str, str]) -> str | None:
    """يُرجِع مساراً نسبيّاً إن أمكن اشتقاقه ساكناً، وإلّا ``None``.

    يفهم ثلاث صياغات قائمة في هذا المستودع:

      ``ROOT / "a/b.json"``      · ``Path("a/b.json")``      · ثابتٌ مُسمّى
    """
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if "/" in node.value else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
            right = current.right
            if isinstance(right, ast.Constant) and isinstance(right.value, str):
                parts.insert(0, right.value)
            else:
                return None
            current = current.left
        if isinstance(current, ast.Name) and current.id in {"ROOT", "REPO", "BASE"}:
            return "/".join(parts)
        return None
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Path" and node.args:
            return _literal_path(node.args[0], consts)
    return None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for statement in tree.body:
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign):
            targets, value = list(statement.targets), statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                resolved = _literal_path(value, consts)
                if resolved:
                    consts[target.id] = resolved
    return consts


def write_targets_of(source: str) -> set[str]:
    """المساراتُ التي **يكتبها** هذا المصدر — مشتقّةً من شجرة الصياغة."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    consts = _module_constants(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # ``X.write_text(...)``
        if isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS:
            resolved = _literal_path(func.value, consts)
            if resolved:
                found.add(resolved)
        # ``open(X, "w")`` — الوضعُ يُقرأ، فلا يُحسَب فتحُ القراءة كتابةً
        if isinstance(func, ast.Name) and func.id == "open" and node.args:
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = str(keyword.value.value)
            if any(flag in mode for flag in ("w", "a", "x")):
                resolved = _literal_path(node.args[0], consts)
                if resolved:
                    found.add(resolved)
        # ``X.open("w")``
        if isinstance(func, ast.Attribute) and func.attr == "open" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and any(
                flag in str(first.value) for flag in ("w", "a", "x")
            ):
                resolved = _literal_path(func.value, consts)
                if resolved:
                    found.add(resolved)
    return found


def measure() -> list[str]:
    tracked = _tracked()
    found: set[str] = set()
    for script in sorted((ROOT / "scripts").rglob("*.py")):
        try:
            found |= write_targets_of(script.read_text(encoding="utf-8"))
        except OSError:
            continue
    return sorted(path for path in found if path in tracked)


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    ).stdout.strip()


def targets() -> list[str]:
    if not MANIFEST.is_file():
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("targets", [])


def generate() -> int:
    found = measure()
    document = {
        "$comment": (
            "أهدافُ الكتابة المولَّدة — مشتقّةٌ من **شجرة الصياغة**: مسارٌ ثابت يُمرَّر "
            "إلى عمليّة كتابة. الذِّكرُ ليس كتابةً: وثيقةُ سياسةٍ بخطّ اليد تُذكَر في "
            "محرّكٍ يقرؤها ولا يكتبها، وتصنيفُها مولَّدةً يُتلِفها عند حلّ التعارض."
        ),
        "schema": "sahool.generated_write_targets",
        "version": 1,
        "adjudicated_on": "2026-08-21",
        "measured_by": "scripts/ci/generated_write_targets.py --generate",
        "measured_on": _head(),
        "criterion": "استدعاءُ كتابة (write_text · open بوضع w/a/x) بمسارٍ ثابتٍ مشتقّ من AST",
        "not_the_criterion": "ورودُ المسار نصّاً في سكربت — يشمل ما يُقرأ ولا يُكتَب",
        "honesty_limit": (
            "مسارٌ يُبنى في وقت التشغيل (حلقة، أو اسمٌ من وسيط) لا يُرى ساكناً. "
            "فالبيان **يُضيف** إلى علامات المُصنِّف ولا يستبدلها، وقائمةُ المنع تعلوه."
        ),
        "count": len(found),
        "targets": found,
    }
    MANIFEST.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"generated_write_targets: {len(found)} هدفاً مقيساً ساكناً")
    return 0


def check() -> int:
    problems: list[str] = []
    if not MANIFEST.is_file():
        print(f"generated_write_targets: FAIL — البيان غائب: {MANIFEST}")
        return 1
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for field in ("schema", "version", "measured_by", "measured_on", "criterion", "honesty_limit"):
        if not str(document.get(field, "")).strip():
            problems.append(f"بيانٌ بلا {field}")

    declared = document.get("targets", [])
    if not declared:
        problems.append("بيانٌ فارغ — يمرّ أخضر عن سؤالٍ لم يُطرَح")
    if document.get("count") != len(declared):
        problems.append(f"العدّاد يخالف المجموعة: {document.get('count')} ≠ {len(declared)}")

    # الاشتقاق رخيص، فيُعاد هنا فعلاً: `--check` يقيس ولا يصف.
    live = measure()
    if sorted(declared) != live:
        problems.append(
            f"البيان ينحرف عن الاشتقاق. لم يُعلَن: {sorted(set(live) - set(declared))[:6]} · "
            f"أُعلِن بلا اشتقاق: {sorted(set(declared) - set(live))[:6]}"
        )

    if problems:
        print("generated_write_targets: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print("\n  أعِد التوليد: python scripts/ci/generated_write_targets.py --generate")
        return 1

    print(f"generated_write_targets: PASS ({len(declared)} هدفاً · مُشتَقٌّ ساكناً ومُعاد التحقّق)")
    return 0


def main() -> int:
    """وضعٌ **واحد** مطلوبٌ صراحةً — لا افتراضيّ صامت ولا جمعٌ يُرجَّح أحدُ طرفيه.

    أوّل صياغةٍ عندي جعلت `--check` بلا أثر (الأداة تفحص بلا علمٍ أصلاً) وسمحت
    بتمرير العلمين معاً فيُؤخَذ `--generate` صامتاً — فأمرٌ يقول «افحص» كان
    **يكتب**. رفعتها مراجعةٌ خارجيّة وأصابت، واحتجّت بعُرف المستودع
    (`route_conflict_guard.py:145`) وهو الحجّة الأقوى: أداتان تُقرآن معاً
    بواجهتين مختلفتين تُنتِجان خطأ قارئ.

    وكلُّ موضعِ استدعاءٍ يمرّر علماً صريحاً (`ci.yml` و`preflight` بـ`--check`،
    و`_GENERATE_FLAG` بـ`--generate`) — فالإلزام لا يكسر شيئاً، مقيسٌ لا مفترَض.
    """
    parser = argparse.ArgumentParser(description="أهدافُ الكتابة المولَّدة")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true", help="اشتقّ واكتب البيان")
    mode.add_argument("--check", action="store_true", help="أعِد الاشتقاق وقارِنه بالبيان")
    args = parser.parse_args()
    return generate() if args.generate else check()


if __name__ == "__main__":
    raise SystemExit(main())
