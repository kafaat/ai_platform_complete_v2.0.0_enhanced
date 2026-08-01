#!/usr/bin/env python3
"""يفرض عقد الاستثناءات المتوقَّعة — EXPECTED-CONTROL-FLOW-EXCEPTION.

موضعان يطابقان نمط «المعالِج الصامت» (``except …:`` يليه ``pass``) بينما الاستثناء
فيهما **إشارة تحكّم مقصودة**: إلغاء مهمّة، وانقضاء فترة استطلاع. إخراجهما من عدّاد
الدَّين صحيح، لكن حذف سطر من أساسٍ كان سيجعله رخصةً — يكفي أن يتوسّع الالتقاط لاحقاً
إلى ``Exception``، أو يُحذف اختبار الإثبات، فيعود الابتلاع الصامت باسم مُبرَّأ.

فالتصنيف مشروط بدليل **يُفحَص آليّاً** لكلّ موضع:

  ١) ``contextlib.suppress`` بنوع مُسمّى ضيّق — لا ``pass`` عارٍ.
  ٢) لا ``Exception``/``BaseException`` في الكتم.
  ٣) تعليق عقديّ يحمل اسم التصنيف في المصدر.
  ٤) **ملفّ اختبار الإثبات موجود** — وهذا ما لا يستطيع الاختبار نفسه فرضه: ملفّ
     محذوف لا يُشغَّل، فلا يفشل. لذلك يعيش هذا الفحص في سكربت CI مستقلّ، وحذفه
     يستلزم تعديل ``ci.yml`` صراحةً — تغيير مرئيّ في المراجعة لا سقوط صامت.

وإنفاذ عكسيّ: إدخال في العقد بلا موضع حيّ مطابق يُسقِط الفحص كذلك.

    python scripts/ci/expected_control_flow_guard.py --check
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "expected_control_flow_exceptions.json"
_BROAD = {"Exception", "BaseException"}
_MARKER = "EXPECTED-CONTROL-FLOW-EXCEPTION"


def _function(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _suppressed(fn: ast.AST) -> set[str]:
    """أسماء الاستثناءات المُمرَّرة إلى ``contextlib.suppress`` داخل الدالّة."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if attr != "suppress":
                continue
            for arg in call.args:
                names.add(arg.attr if isinstance(arg, ast.Attribute) else getattr(arg, "id", ""))
    return names


def _bare_pass_handlers(fn: ast.AST) -> list[str]:
    """معالِجات ``except …: pass`` متبقّية داخل الدالّة — التصنيف لا يسمح بها."""
    out: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            kind = ast.unparse(node.type) if node.type else "bare except"
            out.append(kind)
    return out


def check() -> list[str]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    errors: list[str] = []
    for site in contract["sites"]:
        rel, fname = site["path"], site["function"]
        exc = site["exception"].rsplit(".", 1)[-1]
        path = ROOT / rel
        if not path.exists():
            errors.append(f"موضع في العقد بلا ملفّ حيّ: {rel} — أزِل الإدخال أو أعِد الملفّ.")
            continue
        fn = _function(ast.parse(path.read_text(encoding="utf-8")), fname)
        if fn is None:
            errors.append(f"{rel}: الدالّة {fname} غير موجودة — العقد بائت.")
            continue

        suppressed = _suppressed(fn)
        if exc not in suppressed:
            errors.append(
                f"{rel}::{fname} لا يكتم {exc} عبر contextlib.suppress — "
                "التصنيف يشترط نوعاً ضيّقاً مُسمّى لا pass عارياً."
            )
        broad = suppressed & _BROAD
        if broad:
            errors.append(
                f"{rel}::{fname} يكتم {sorted(broad)} — الكتم العريض يُعيد العيب الصامت "
                "تحت اسم مُبرَّأ."
            )
        stray = _bare_pass_handlers(fn)
        if stray:
            errors.append(f"{rel}::{fname} ما زال يحمل except…: pass لـ{stray}")
        if _MARKER not in path.read_text(encoding="utf-8"):
            errors.append(f"{rel}: تعليق التصنيف ({_MARKER}) مفقود من المصدر.")

        evidence = ROOT / site["evidence_test"]
        if not evidence.exists():
            errors.append(
                f"{rel}: اختبار الإثبات مفقود ({site['evidence_test']}) — "
                "التصنيف بلا دليل سلوكيّ يسقط."
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="افحص (الافتراضيّ)")
    parser.parse_args()
    errors = check()
    if errors:
        print("expected_control_flow_guard_failed")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print("expected_control_flow_guard_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
