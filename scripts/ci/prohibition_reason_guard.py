#!/usr/bin/env python3
"""مَنعٌ بلا سببٍ مُعلَن — `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`.

**الحادثة التي أوجبت هذا الجرد، لا فرضيّة.** كان
`tests_v9/test_imagery_timeline_endpoint_v31_4.py` يؤكّد وجود `timedelta(days=months`
نصّاً في المصدر. والشهر ليس ٣١ يوماً: عند `months=24` يُرجِع الحدّ اليوميّ
`2024-07-21` بينما التقويميّ `2024-08-04` — **أربعةَ عشرَ يوماً** من المشاهد تدخل
النافذة بصمت. فلمّا صُحِّح الحساب **سقط الحارس**، وأسقط *Unit Tests* مرّتين على
#780. أي أنّ الحارس كان يحمي العطل، والإصلاح الصحيح بدا انحداراً.

والعلاج المُنزَل هناك لم يكن حذف التأكيد بل قلبه إلى **مَنعٍ يُسمّي سببه**:

    assert "timedelta(days=months" not in b, "الشهر ليس ٣١ يوماً — لا تُعِد الحدّ اليوميّ"

**وهذا الحارس يُعمِّم النصف القابل للحسم من ذلك العلاج.** المَنع الذي لا يُسمّي سببه
عطلٌ مؤجَّل من وجهين، كلاهما مقيس في هذا المستودع:

  ① **حين يُطلِق** يقول «كسرتَ شيئاً» وهو يعني «نمنع هذا عمداً». والقارئ الذي لا
     يعرف السبب يُرضي النصّ — أو يحذف المَنع. وحذفُ مَنعٍ لا أحد يعرف سببه هو
     كيف يعود العطل الأصليّ.
  ② **وحين لا يُطلِق** لا يُميّزه شيء عن مَنعٍ بطل سببه. فيُقرأ حراسةً قائمة وهو
     أثرٌ لقرارٍ انتهى.

**النطاق ضيّق عمداً وقابل للحسم:** مَنعٌ (`assert "…" not in x`) على **نصّ مصدر**
— أي متغيّر أُسنِد من قارئ ملفّ في الاختبار نفسه، مُشتقٌّ بالبنية لا بالاسم. ما
يُمنَع في جسم استجابة أو حمولة JSON خارج النطاق: هناك التأكيد **هو** العقد، وسببه
في اسم الاختبار.

**وما لا يفعله هذا الحارس — والحدّ مُعلَن لأنّه يُغري:** لا يحكم على التأكيدات
**الموجبة** على نصّ المصدر. مسحُها أعطى **٢٨٩** تأكيداً موجباً يثبّت جزءَ نداء
(`\\w\\(`) — وهو صنف الحادثة بعينه — لكنّ معيار الفجوة («هل يبقى التأكيد صحيحاً
بعد إعادة صياغة صحيحة؟») **غير قابل للحسم آليّاً**، ومُصنِّفٌ استدلاليّ يُنتِج
قائمةً تُقرأ ديناً وهي ليست إلّا ما طابق نمطاً. تُنشَر الأرقام في الجرد ولا تُحرَس.

الأساس **مجموعة مُجمَّدة لا عدداً** — درس `assertion_presence_guard`: بالعدد وحده
يُصلَح مَنعٌ ويُدخَل آخر بلا أثر. ولا يحمل أسباباً مُختلَقة: **مَعدودٌ لا محكومٌ
عليه**، وسدادُه بكتابة السبب الحقيقيّ لا بنسخ عبارة.

    python scripts/ci/prohibition_reason_guard.py --check
    python scripts/ci/prohibition_reason_guard.py --generate
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
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

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "architecture" / "source_text_assertion_inventory.json"

# قارئات الملفّات. المتغيّر يحمل «نصّ مصدر» إن أُسنِد من إحداها — بالبنية لا بالاسم،
# فاسم المتغيّر (`src` · `b` · `text` · `SRC`) اصطلاحٌ لا عقد.
_READERS = ("read_text", "read", "getsource")


def _test_files() -> list[str]:
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout
    return sorted(
        rel
        for rel in out.split("\0")
        if rel.endswith(".py") and (rel.startswith(("tests_v9/", "tests/")) or "/tests/" in rel)
    )


def _source_text_vars(tree: ast.AST) -> set[str]:
    """المتغيّرات المُسنَدة من قارئ ملفّ في هذا الملفّ."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if called in _READERS:
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _prohibition(node: ast.Assert) -> tuple[str, str] | None:
    """(النصّ الممنوع، اسم الحاوية) إن كان التأكيد مَنعاً، وإلّا ``None``.

    الصيغتان معاً: ``"x" not in y`` و``not ("x" in y)`` — الثانية أندر ولا تُستثنى،
    فحارسٌ يرى صيغةً واحدة يُلتَفّ عليه بإعادة صياغة لا تُغيّر شيئاً.
    """
    test = node.test
    negated = False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        test, negated = test.operand, True
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return None
    op = test.ops[0]
    if isinstance(op, ast.NotIn):
        negated = not negated
    elif not isinstance(op, ast.In):
        return None
    if not negated:
        return None
    left, right = test.left, test.comparators[0]
    if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
        return None
    if not isinstance(right, ast.Name):
        return None
    return left.value, right.id


def survey() -> dict:
    """المسح كاملاً — يُنشر منه المحروس والمنشور بلا حراسة، ولا يُخلَط بينهما."""
    unreasoned: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals = {"source_text_assertions": 0, "positive_pinning_a_call": 0, "prohibitions": 0}

    for rel in _test_files():
        try:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        except (SyntaxError, ValueError):
            continue
        srcvars = _source_text_vars(tree)
        if not srcvars:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            hit = _prohibition(node)
            if hit is not None:
                needle, container = hit
                if container not in srcvars:
                    continue
                totals["source_text_assertions"] += 1
                totals["prohibitions"] += 1
                if node.msg is None:
                    unreasoned[rel][needle] += 1
                continue
            # موجب: يُعَدّ للنشر فقط.
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.In)
                and isinstance(test.left, ast.Constant)
                and isinstance(test.left.value, str)
                and isinstance(test.comparators[0], ast.Name)
                and test.comparators[0].id in srcvars
            ):
                totals["source_text_assertions"] += 1
                if _pins_a_call(test.left.value):
                    totals["positive_pinning_a_call"] += 1
    return {
        "totals": totals,
        "prohibitions_without_a_stated_reason": {
            rel: dict(sorted(needles.items())) for rel, needles in sorted(unreasoned.items())
        },
    }


def _pins_a_call(needle: str) -> bool:
    """هل يثبّت النصّ **نداءً بوسائطه**؟ — صنف الحادثة (`timedelta(days=months`).

    يُنشَر ولا يُحرَس: هذا استدلال، ومعيار الفجوة غير قابل للحسم آليّاً.
    """
    for i, ch in enumerate(needle):
        if ch == "(" and i and (needle[i - 1].isalnum() or needle[i - 1] == "_"):
            return True
    return False


def _flatten(mapping: dict) -> set[tuple[str, str, int]]:
    return {(rel, needle, n) for rel, needles in mapping.items() for needle, n in needles.items()}


def check() -> int:
    if not INVENTORY.exists():
        print(f"prohibition_reason_guard: FAIL — الجرد مفقود: {INVENTORY.relative_to(ROOT)}")
        return 1
    recorded = json.loads(INVENTORY.read_text(encoding="utf-8"))
    frozen = recorded["prohibitions_without_a_stated_reason"]
    found = survey()["prohibitions_without_a_stated_reason"]

    problems: list[str] = []
    for rel, needle, count in sorted(_flatten(found) - _flatten(frozen)):
        problems.append(
            f"مَنعٌ بلا سببٍ مُعلَن خارج الأساس: {rel} ⇒ {needle!r} (×{count})\n"
            f"      أضِف رسالة تقول **لماذا يُمنَع**: "
            f'assert {needle!r} not in <src>, "…السبب…"\n'
            f"      المَنع بلا سبب يُقرأ عند إطلاقه «كسرتَ شيئاً» وهو يعني «نمنع هذا عمداً»."
        )
    for rel, needle, count in sorted(_flatten(frozen) - _flatten(found)):
        problems.append(
            f"مدخل بائت في الأساس: {rel} ⇒ {needle!r} (×{count}) — "
            f"كُتِب سببه أو حُذِف. أعِد التوليد (الأساس يتقلّص)."
        )

    if problems:
        print("prohibition_reason_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(
            f"\n  إعادة التوليد بعد سداد حقيقيّ:\n    python {Path(__file__).relative_to(ROOT)} --generate"
        )
        return 1

    total = sum(n for needles in frozen.values() for n in needles.values())
    print(
        f"prohibition_reason_guard: PASS "
        f"({total} مَنعاً بلا سبب في الأساس المُجمَّد · {len(frozen)} ملفّاً)"
    )
    return 0


def generate() -> int:
    result = survey()
    head = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout.strip()
    payload = {
        "$comment": (
            "GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01 — المسح الأوّل لسطح التأكيدات "
            "الساكنة على نصّ المصدر. `prohibitions_without_a_stated_reason` **مَعدودة لا "
            "محكومٌ عليها**: لم يُثبَت أنّ أيّاً منها خاطئ، بل أنّ سببه غير مكتوب. "
            "الأساس يمنع النموّ، وسدادُه بكتابة السبب الحقيقيّ لا بنسخ عبارة. "
            "و`positive_pinning_a_call` **يُنشَر ولا يُحرَس**: معيار الفجوة (هل يبقى "
            "التأكيد صحيحاً بعد إعادة صياغة صحيحة؟) غير قابل للحسم آليّاً، ومُصنِّفٌ "
            "استدلاليّ يُنتِج قائمةً تُقرأ ديناً وهي ما طابق نمطاً."
        ),
        "gap": "GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01",
        "measured_on": head,
        "scope": (
            "assert على نصّ مصدر فقط — متغيّر أُسنِد من read_text/read/getsource في "
            "الاختبار نفسه، مُشتقٌّ بالبنية لا بالاسم. ما يُؤكَّد على جسم استجابة أو "
            "حمولة JSON خارج النطاق: هناك التأكيد هو العقد."
        ),
        **result,
    }
    INVENTORY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"كُتِب {INVENTORY.relative_to(ROOT)} — {payload['totals']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="بوّابة CI")
    parser.add_argument("--generate", action="store_true", help="يكتب الجرد")
    args = parser.parse_args()
    return generate() if args.generate else check()


if __name__ == "__main__":
    raise SystemExit(main())
