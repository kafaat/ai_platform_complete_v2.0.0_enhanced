"""اختبارٌ يحسب شرطاً ثمّ يسجّله في قائمةٍ إن صحّ — ولا يقول شيئاً إن كذب.

``UNENFORCED-REPORT-LIST-TEST-01``.

**العطلُ المقيس الذي أوجب هذا الحارس**، لا مثالٌ مُتخيَّل: ``test_erp_provider_switch``
في ``tests_v9/test_roadmap_phase23.py`` كان يقول::

    p2 = erp_provider.get_erp_provider()
    if p2.name == "erpnext":
        r.append(("✓", "تبديل: erpnext → ERPNextProvider"))

فلمّا صار الجسرُ يشترط ``ERPNEXT_URL`` صريحاً مع الاعتمادين، هبطت الحالةُ إلى
``NullProvider`` — و**لم يحمرّ شيء**. الفرعُ لم يُنفَّذ، والقائمةُ لم تنمُ، والدالّةُ
مرّت خضراء. أي أنّ الخاصّيّةَ التي يحمل الاختبارُ اسمَها صارت غيرَ مفروضة، وخضرتُه
شهادةٌ على لا شيء. وأسوأُ من ذلك: حالةُ «بلا مفاتيح ⇒ none» بقيت خضراء **للسبب
الخطأ** — كانت تمرّ ولو حُذِف فحصُ المفاتيح كلُّه، لأنّ العنوانَ كان غائباً أيضاً.

والصنفُ هو نفسُه الذي يطارده هذا المستودع: **حارسٌ كفّ عن الحجب بلا أن يحمرّ**.

**والقاعدة المفروضة هنا راتشِت لا حائط:** المقيسُ عند الكتابة 192 دالّةً في 13 ملفّاً —
دَينٌ قائمٌ لا يُغلَق في رقعةٍ واحدة. فيُجمَّد بأعداده، **ويتقلّص ولا ينمو**: ملفٌّ جديد
يسقط، وزيادةٌ في ملفٍّ قائم تسقط، و**نقصانٌ لا يُحدَّث معه الأساس يسقط أيضاً** — وإلّا
بات الرقمُ يصف كوناً زال، وهو بعينه ما يمنعه ``test_mutation_sweep_headroom``.

**وحدُّ صدقٍ في التسمية:** لا يُدَّعى أنّ هذه الدوالّ «لا يمكن أن تفشل» — قد يرمي
استدعاءٌ داخلها فتحمرّ. المُدَّعى أضيق وأدقّ: **الخاصّيّةُ التي تسمّيها غيرُ مفروضة**،
لأنّ كذبَ الشرط لا يُنتِج إلّا صمتاً.

يُشغَّل في ``capability-governance.yml`` مع بقيّة حرّاس ``tests/architecture/``
(``ARCH-TESTS-UNLISTED-IN-CI-01``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("tests_v9", "tests", "services")

#: الأساسُ المُجمَّد — مقيسٌ على `2649dcf9`+ بعد إصلاح `test_erp_provider_switch`.
#: كلُّ مدخلٍ دَينٌ مُعلَن، والقيمةُ سقفٌ لذلك الملفّ. **تُخفَّض عند الإصلاح ولا تُرفَع.**
FROZEN_DEBT: dict[str, int] = {
    "tests_v9/test_roadmap_phase23.py": 129,
    "tests_v9/test_roadmap_phase1.py": 15,
    "tests_v9/test_wired_endpoints.py": 9,
    "tests_v9/test_trueup_endpoint.py": 6,
    "tests_v9/test_chaos_resilience.py": 5,
    "tests_v9/test_geospatial.py": 5,
    "tests_v9/test_event_replay.py": 4,
    "tests_v9/test_v10_modules.py": 4,
    "tests_v9/test_v12_modules.py": 4,
    "tests_v9/test_confidence_failures.py": 3,
    "tests_v9/test_qualification_suite.py": 3,
    "tests_v9/test_v13_refinements.py": 3,
    "tests_v9/test_mobile_backend_contract.py": 2,
}


def _enforces_something(node: ast.AST) -> bool:
    """هل في الدالّة ما يستطيع أن يُحمِّرها عند كذب الخاصّيّة؟"""
    for inner in ast.walk(node):
        if isinstance(inner, (ast.Assert, ast.Raise)):
            return True
        if isinstance(inner, ast.Call):
            attribute_chain: list[str] = []
            target = inner.func
            while isinstance(target, ast.Attribute):
                attribute_chain.append(target.attr)
                target = target.value
            if not attribute_chain:
                continue
            dotted = ".".join(reversed(attribute_chain))
            if dotted in {"pytest.raises", "pytest.warns", "pytest.fail"}:
                return True
            if attribute_chain[-1].startswith("assert"):
                return True
    return False


def _records_only_when_true(node: ast.AST) -> bool:
    """`if <شرط>: <قائمة>.append(...)` — الكذبُ يُنتِج صمتاً لا نتيجة."""
    return any(
        isinstance(branch, ast.If)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "append"
            for call in ast.walk(branch)
        )
        for branch in ast.walk(node)
    )


def measure_unenforced_tests() -> dict[str, int]:
    """يُشتقّ الجردُ من الشجرة — لا قائمةَ مسارٍ مكتوبةٍ بيدٍ تبيت."""
    counts: dict[str, int] = {}
    for search_root in SEARCH_ROOTS:
        for path in sorted((ROOT / search_root).rglob("test_*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # ملفٌّ تالفٌ شأنُ حارسٍ آخر، لا هذا
                continue
            relative = path.relative_to(ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("test_"):
                    continue
                if _records_only_when_true(node) and not _enforces_something(node):
                    counts[relative] = counts.get(relative, 0) + 1
    return counts


def test_no_new_file_records_a_property_without_enforcing_it():
    measured = measure_unenforced_tests()
    newcomers = sorted(set(measured) - set(FROZEN_DEBT))
    assert not newcomers, (
        "ملفّاتٌ جديدة تحمل اختباراتٍ تُسجّل الخاصّيّة عند صحّتها وتصمت عند كذبها:\n  "
        + "\n  ".join(f"{name} ({measured[name]})" for name in newcomers)
        + "\nالعلاجُ تأكيدٌ صريح، لا إضافةُ الملفّ إلى الأساس."
    )


def test_the_declared_debt_never_grows_inside_a_file():
    measured = measure_unenforced_tests()
    grew = {
        name: (FROZEN_DEBT[name], measured[name])
        for name in FROZEN_DEBT
        if measured.get(name, 0) > FROZEN_DEBT[name]
    }
    assert not grew, "دَينٌ نما داخل ملفٍّ مُعلَن (الأساس ⇐ المقيس):\n  " + "\n  ".join(
        f"{name}: {before} ⇐ {after}" for name, (before, after) in grew.items()
    )


def test_the_baseline_is_lowered_in_the_same_commit_that_repairs_a_test():
    """راتشِتٌ يشدّ: أساسٌ أعلى من المقيس يصف كوناً زال، فيُقرأ هامشاً وهو وهم."""
    measured = measure_unenforced_tests()
    stale = {
        name: (declared, measured.get(name, 0))
        for name, declared in FROZEN_DEBT.items()
        if measured.get(name, 0) < declared
    }
    assert not stale, (
        "أُصلِحت اختباراتٌ ولم يُخفَّض الأساس معها (المُعلَن ⇐ المقيس):\n  "
        + "\n  ".join(
            f"{name}: {declared} ⇐ {actual}" for name, (declared, actual) in stale.items()
        )
        + "\nاخفِض الرقمَ في الالتزام نفسِه، أو احذف المدخلَ إن بلغ صفراً."
    )


def test_the_detector_separates_an_enforced_property_from_a_recorded_one():
    """أرضيّةُ صدقٍ للكاشف: يجب أن يُميّز فعلاً، لا أن يُصنّف كلَّ شيءٍ ديناً."""
    recorded = ast.parse(
        "def test_x():\n    report = []\n    if compute() == 'ok':\n        report.append('✓')\n"
    ).body[0]
    enforced = ast.parse(
        "def test_x():\n"
        "    report = []\n"
        "    value = compute()\n"
        "    assert value == 'ok'\n"
        "    if value == 'ok':\n"
        "        report.append('✓')\n"
    ).body[0]
    assert _records_only_when_true(recorded) and not _enforces_something(recorded)
    assert _records_only_when_true(enforced) and _enforces_something(enforced)


def test_the_repaired_erp_switch_is_no_longer_counted_as_debt():
    """العطلُ الذي أوجب الحارس يبقى مقيساً بعد إصلاحه، لا موصوفاً في نصٍّ فقط."""
    source = (ROOT / "tests_v9/test_roadmap_phase23.py").read_text(encoding="utf-8")
    switch = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "test_erp_provider_switch"
    )
    assert _enforces_something(switch), "عاد شاهدُ تبديل المزوّد إلى التسجيل بلا تأكيد"
