#!/usr/bin/env python3
"""`UNDECLARED-CONTEXT-DEPENDENCY-01` — مُستهلِكٌ عبر الطبقة يُعلِن ما يطلبه.

**البابُ الذي يسدّه:** `canonical_consumer_bypass_guard` يحرس مَن يقرأ الحقل
**مباشرةً**. ومن يقرؤه **عبر المُحلِّل** خارج مداه تماماً — فيستطيع أن يطلب
مفتاحاً بـ`ctx.require("...")` بلا أن يُعلِنه في أيّ عقد، فتعود التبعيّة إلى
رأس كاتبها وهو ما بُنيت الطبقة لإخراجه منه.

**والقاعدة المفروضة:** كلّ سلسلةٍ تصل إلى `require`/`provenance` في مِلَفٍّ خارج
`shared/knowledge/` يجب أن تكون **مُسجَّلةً** و**مُعلَنةً في عقدٍ ما**. وطلبُ
مفتاحٍ غير مُسجَّل خطأٌ أوضح: يسأل عن شيءٍ لا مصدر حقيقةٍ له.

**ولماذا لا يُفرَض «العقد المُعلَن في المِلَفّ نفسه»:** المُنسِّق يستورد عقده من
`shared/knowledge/irrigation_context.py`، وهو الموضع الصحيح — العقد يُعلَن مرّةً
ويُستهلَك في مواضع. فاشتراطُ الإعلان **في مِلَفّ المستهلك** كان سيدفع إلى نسخ
العقود، وهو نقيض الغرض.

**ولا يُحتسَب ذِكرٌ في تعليق:** تُقرأ الوسائط من الاستدعاء بـ`ast`.

لا pytest ولا تبعيّات: يعمل مستقلّاً داخل وظيفة الحرّاس.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "knowledge_source_registry.json"
REGISTRY_SCHEMA = "sahool.knowledge_source_registry"
CONTRACT_DIR = ROOT / "shared" / "knowledge"
SCAN_DIRS = ("services", "shared", "agents", "bots")
RESOLVER_METHODS = {"require", "provenance"}


def load_keys(registry_path: Path) -> list[dict]:
    if not registry_path.is_file():
        raise SystemExit(f"✗ سجلّ مصادر الحقيقة غير موجود: {registry_path}")
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ سجلٌّ غير قابل للتحليل: {registry_path} — {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"✗ مخطَّطٌ غير متوقَّع في {registry_path}")
    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys:
        raise SystemExit(f"✗ سجلٌّ بلا مفاتيح: {registry_path}")
    return keys


def declared_keys(contract_dir: Path) -> set[str]:
    """المفاتيح المُعلَنة في أيّ `KnowledgeRequirement(key=...)`."""
    found: set[str] = set()
    if not contract_dir.is_dir():
        return found
    for path in sorted(contract_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "KnowledgeRequirement":
                continue
            for kw in node.keywords:
                if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        found.add(kw.value.value)
    return found


def requested_keys(tree: ast.AST) -> set[str]:
    """السلاسل المُمرَّرة إلى `.require(...)` / `.provenance(...)`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in RESOLVER_METHODS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
    return found


def scan_files(root: Path, scan_dirs: tuple[str, ...], contract_dir: Path) -> list[Path]:
    files: list[Path] = []
    for name in scan_dirs:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if contract_dir in path.parents or path.parent == contract_dir:
                continue
            if any(part in {"tests", "__pycache__"} for part in path.parts):
                continue
            if path.name.startswith("test_"):
                continue
            files.append(path)
    return files


def violations(
    registered: set[str], declared: set[str], files: list[Path], root: Path
) -> tuple[list[str], int]:
    problems: list[str] = []
    requests = 0
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        asked = requested_keys(tree)
        if not asked:
            continue
        rel = path.relative_to(root).as_posix()
        for key in sorted(asked):
            requests += 1
            if key not in registered:
                problems.append(f"✗ {rel}: يطلب «{key}» ولا مصدرَ حقيقةٍ مُسجَّلاً له")
            elif key not in declared:
                problems.append(
                    f"✗ {rel}: يطلب «{key}» بلا إعلانٍ في أيّ عقد — التبعيّة تعود إلى رأس كاتبها"
                )
    return problems, requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="undeclared context dependency guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--contracts", default=str(CONTRACT_DIR))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    root = Path(args.root)
    contract_dir = Path(args.contracts)
    registered = {
        entry["key"]
        for entry in load_keys(Path(args.registry))
        if isinstance(entry.get("key"), str)
    }
    declared = declared_keys(contract_dir)
    if not declared:
        # لا عقدَ مقروء ⇒ كلُّ طلبٍ سيبدو غير مُعلَن، أو — إن لم يكن ثمّة طلب —
        # يمرّ الحارس بلا أن يقيس شيئاً. الحالتان تكذبان.
        raise SystemExit(f"✗ لا مفاتيح مُعلَنة في العقود: {contract_dir}")

    files = scan_files(root, SCAN_DIRS, contract_dir)
    problems, requests = violations(registered, declared, files, root)

    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)

    print(
        f"undeclared_context_dependency_guard: PASS "
        f"({len(files)} مِلَفّاً · {requests} طلباً · {len(declared)} مفتاحاً مُعلَناً)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
