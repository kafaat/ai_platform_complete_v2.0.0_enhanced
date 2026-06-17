#!/usr/bin/env python3
"""scripts/mutation_probe.py — قياس قوّة الاختبارات بالطفرات (Mutation Testing، خفيف).

النوع 4 من هرم التحقّق: «هل يوجد اختبار قادر على إثبات خاصّيّة؟» — لا «هل يوجد اختبار؟».
يُطبّق مُشغِّلات طفرة قانونيّة على وحدة هدف (قلب المنطق الزراعيّ النقيّ)، ويُشغّل **اختباراتها
الفعليّة** على كلّ طافِر؛ إن لم يفشل أيّ اختبار ⇒ الطافِر «ناجٍ» = ثغرة في قوّة الاختبارات.

المُشغِّلات (الأكثر كشفاً لعيوب الحدود/المنطق):
  • مقارنات: > ↔ >=,  < ↔ <=,  == ↔ !=
  • حسابيّة: + ↔ -,  * ↔ /
  • منطقيّة: and ↔ or
  • ثوابت منطقيّة: True ↔ False (بالهويّة is — لا تُطفَّر الأعداد 0/1 تفادياً للضجيج)

الاستعمال: python scripts/mutation_probe.py <module.py> -- <pytest args...>
يُرجِع رمز 1 إن نجا طافِر (لِبوّابة CI على وحدات حرجة).
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

_CMP = {
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


def _count_targets(src: str) -> int:
    """عدد المواقع القابلة للطفرة (مقارنة-عامل واحد، عامل ثنائيّ، منطقيّ، ثابت منطقيّ)."""
    n = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Compare):
            n += sum(1 for op in node.ops if type(op) in _CMP)
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            n += 1
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            n += 1
        elif isinstance(node, ast.Constant) and (node.value is True or node.value is False):
            n += 1
    return n


class _MutateNth(ast.NodeTransformer):
    """يُطفِّر الموقعَ رقم target فقط (مُرقَّم بترتيب الزيارة)؛ يسجّل الوصف."""

    def __init__(self, target: int):
        self.target = target
        self.i = -1
        self.desc = ""

    def _hit(self) -> bool:
        self.i += 1
        return self.i == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        for k, op in enumerate(node.ops):
            if type(op) in _CMP and self._hit():
                old = type(op)
                node.ops[k] = _CMP[old]()
                self.desc = f"L{node.lineno}: cmp {old.__name__}→{type(node.ops[k]).__name__}"
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in _BIN and self._hit():
            old = type(node.op)
            node.op = _BIN[old]()
            self.desc = f"L{node.lineno}: bin {old.__name__}→{type(node.op).__name__}"
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if type(node.op) in _BOOL and self._hit():
            old = type(node.op)
            node.op = _BOOL[old]()
            self.desc = f"L{node.lineno}: bool {old.__name__}→{type(node.op).__name__}"
        return node

    def visit_Constant(self, node):
        if (node.value is True or node.value is False) and self._hit():
            old = node.value
            node.value = not node.value
            self.desc = f"L{node.lineno}: const {old}→{node.value}"
        return node


def _mutants(src: str):
    """يُولِّد (وصف, مصدر مُطفَّر) — طفرة واحدة لكلّ موقع قابل."""
    for t in range(_count_targets(src)):
        tree = ast.parse(src)
        mut = _MutateNth(t)
        tree = mut.visit(tree)
        if mut.desc:
            yield mut.desc, ast.unparse(ast.fix_missing_locations(tree))


def run(module: str, pytest_args: list[str]) -> int:
    path = pathlib.Path(module)
    original = path.read_text(encoding="utf-8")
    mutants = list(_mutants(original))
    killed = survived = 0
    survivors = []
    try:
        for desc, msrc in mutants:
            path.write_text(msrc, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, "-m", "pytest", *pytest_args, "-q", "-x", "--no-header"],
                capture_output=True,
                cwd=pathlib.Path(__file__).resolve().parent.parent,
            )
            if r.returncode != 0:
                killed += 1
            else:
                survived += 1
                survivors.append(desc)
    finally:
        path.write_text(original, encoding="utf-8")

    total = killed + survived
    score = (killed / total * 100) if total else 100.0
    print(f"طفرات: {total} | قُتِلت: {killed} | نجت: {survived} | الدرجة: {score:.0f}%")
    if survivors:
        print("الطافِرون الناجون (ثغرات في الاختبارات):")
        for s in survivors:
            print("  " + s)
        return 1
    print("✓ كلّ الطفرات قُتِلت — الاختبارات قويّة على هذه الوحدة")
    return 0


if __name__ == "__main__":
    if "--" not in sys.argv:
        print("الاستعمال: mutation_probe.py <module.py> -- <pytest args...>")
        sys.exit(2)
    cut = sys.argv.index("--")
    mod = sys.argv[1]
    sys.exit(run(mod, sys.argv[cut + 1 :]))
