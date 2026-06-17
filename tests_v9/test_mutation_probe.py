"""اختبار سلامة أداة الطفرات (scripts/mutation_probe) — وحدة سريعة (لا تشغّل المسح الكامل).

النوع 4 من هرم التحقّق: الأداة تُطفِّر الكود وتُشغّل اختباراته الفعليّة. هذا الاختبار يثبّت
أنّ مُولِّد الطفرات يعمل (يكتشف المواقع، يُولِّد طفرة واحدة صالحة لكلّ موقع، يحفظ الأصل)،
دون تكلفة المسح الكامل (الذي يُشغَّل عند الطلب على الوحدات الحرجة).
"""

from __future__ import annotations

import importlib.util
import os
import textwrap

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load():
    spec = importlib.util.spec_from_file_location(
        "mut_probe", os.path.join(ROOT, "scripts", "mutation_probe.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_SRC = textwrap.dedent("""
    def f(x):
        if x > 0 and x < 10:
            return x + 1
        return True
""")


def test_counts_mutatable_targets():
    m = _load()
    # > , < , and , + , True  ⇒ 5 مواقع
    assert m._count_targets(_SRC) == 5


def test_generates_one_valid_mutant_per_target():
    m = _load()
    muts = list(m._mutants(_SRC))
    assert len(muts) == 5, "عدد الطفرات ≠ عدد المواقع"
    for desc, msrc in muts:
        assert desc and ":" in desc  # وصف بسطر+نوع
        compile(msrc, "<mut>", "exec")  # كلّ طافِر مصدر صالح


def test_mutations_actually_differ():
    m = _load()
    descs = {d for d, _ in m._mutants(_SRC)}
    # تشمل أنواعاً مختلفة (مقارنة/حسابيّ/منطقيّ/ثابت)
    kinds = {d.split(": ")[1].split(" ")[0] for d in descs}
    assert {"cmp", "bin", "bool", "const"} <= kinds


def test_run_restores_original(tmp_path):
    """run يُعيد المصدر الأصليّ دائماً (لا يترك الملفّ مُطفَّراً)."""
    m = _load()
    f = tmp_path / "mod.py"
    f.write_text("def g():\n    return 1 > 0\n", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    # أمر اختبار وهميّ ينجح دائماً ⇒ كلّ الطفرات «تنجو» (لا يهمّنا هنا)، المهمّ الاستعادة
    m.run(str(f), ["--collect-only", "-q"])
    assert f.read_text(encoding="utf-8") == before, "لم يُستعَد المصدر الأصليّ"
