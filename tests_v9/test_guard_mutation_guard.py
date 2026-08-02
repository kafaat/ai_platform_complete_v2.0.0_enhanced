"""لا حارس بلا عطلٍ مزروع — GUARDS-WITHOUT-A-PLANTED-DEFECT-01.

هذا الملفّ يزرع أعطالاً في حرّاسٍ **صناعيّين** يُبنَون في `tmp_path` ويُشغَّل عليهم
pytest حقيقيّ. والبديل — قراءة السجلّ والتأكّد من امتلائه — كان سيقيس **حالة
السجلّ** لا **قاعدة الحارس**، وهو عمى التكذيب الذي تكرّر ثلاث مرّات في هذه الجلسة
وهو تحديداً ما وُجِدت هذه الآليّة لتمنعه.

والحالتان الحرجتان هنا ليستا «هل يحمرّ»:

* **أخضر تحت عطلٍ مزروع** ⇒ إخفاق. الحارس لا يحرس تلك القاعدة، أو اختباره يقرأ
  مصنوعةً مُولَّدة سلفاً بدل أن يمرّ بالقاعدة.
* **أحمر بغير الاختبار المُسمّى** ⇒ إخفاق أيضاً. «سقط شيء ما» يمرّ على طفرةٍ كسرت
  الاستيراد لا القاعدة، وهي أرخص طريقة لادّعاء تغطية غير موجودة.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "guard_mutation_guard", ROOT / "scripts/ci/guard_mutation_guard.py"
)
gmg = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(gmg)

REAL = json.loads(
    (ROOT / "docs/architecture/guard_mutation_registry.json").read_text(encoding="utf-8")
)


def _debt(reg: dict) -> set[str]:
    return {k for k in reg["unmutated_debt"] if not k.startswith("$")}


# --------------------------------------------------- السجلّ الحقيقيّ على الشجرة


def test_real_registry_passes_the_static_check() -> None:
    assert gmg.check(REAL) == []


def test_every_guard_on_disk_is_accounted_for() -> None:
    assert gmg.guard_inventory() == set(REAL["mutated"]) | _debt(REAL)


def test_the_ceiling_is_tight_against_the_debt() -> None:
    """سقفٌ فيه فسحة يسمح بحارسٍ جديد بلا مواصفة — وهو ما تمنعه الآليّة."""
    assert len(_debt(REAL)) == REAL["unmutated_debt_ceiling"]


def test_this_guard_specifies_itself() -> None:
    """آليّة تُعفي نفسها من قاعدتها تُبلِّغ تغطيةً لا تملكها — وهي أوّل من يجب أن يخضع."""
    assert "guard_mutation_guard.py" in REAL["mutated"]
    assert "guard_mutation_guard.py" not in _debt(REAL)


def test_every_mutation_names_a_test_and_a_reason() -> None:
    for name, spec in REAL["mutated"].items():
        assert spec["mutations"], name
        src = (ROOT / spec["test"]).read_text(encoding="utf-8")
        for m in spec["mutations"]:
            assert m["why"], name
            assert m["find"] != m["replace"], name
            assert f"def {m['expect']}(" in src, f"{name}: {m['expect']}"


def test_a_bare_prefix_is_not_an_expected_test(tmp_path: Path) -> None:
    """`"test_"` تطابق أيّ سقوط، فتُعيد الشرط إلى «سقط شيء ما».

    وقعتُ في هذه بالضبط: أوّل مواصفتين كتبتهما لـ`brain_state_transition_guard`
    حملتا `expect: "test_"` ومرّتا خضراوين — آليّةٌ تُثبِت التغطية بشرطٍ يُحقّقه
    أيّ انهيار، وهو نفس عطل «حارس يُبلِّغ نتيجةً عن سؤال لم يطرحه».
    """
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_"))
    failures = gmg.check(reg, ci, tmp_path)
    assert any("لا يسمّي اختباراً" in f for f in failures)


# --------------------------------------------------------- حارس صناعيّ للزرع

_GUARD_SRC = '''\
"""حارس صناعيّ: يرفض القيم السالبة."""


def check(values):
    bad = [v for v in values if v < 0]
    if bad:
        return [f"سالب: {bad}"]
    return []
'''

_TEST_SRC = """\
import importlib.util
from pathlib import Path

_S = importlib.util.spec_from_file_location(
    "fake_guard", Path(__file__).resolve().parents[1] / "scripts/ci/fake_guard.py"
)
g = importlib.util.module_from_spec(_S)
_S.loader.exec_module(g)


def test_negative_is_rejected():
    assert g.check([1, -2]) != []


def test_clean_input_passes():
    assert g.check([1, 2]) == []
"""


def _fake_repo(tmp_path: Path, guard_src: str = _GUARD_SRC, test_src: str = _TEST_SRC):
    ci = tmp_path / "scripts" / "ci"
    ci.mkdir(parents=True)
    (ci / "fake_guard.py").write_text(guard_src, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_fake.py").write_text(test_src, encoding="utf-8")
    return ci


def _reg(**over) -> dict:
    base = {"mutated": {}, "unmutated_debt": {}, "unmutated_debt_ceiling": 0}
    base.update(over)
    return base


def _spec(find: str, replace: str, expect: str) -> dict:
    return {
        "fake_guard.py": {
            "test": "tests/test_fake.py",
            "mutations": [{"why": "زرع", "find": find, "replace": replace, "expect": expect}],
        }
    }


# ------------------------------------------------------------ الفحص الثابت


def test_a_new_guard_without_a_mutation_spec_is_blocked(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    failures = gmg.check(_reg(), ci, tmp_path)
    assert any("بلا مواصفة طفرة" in f and "fake_guard.py" in f for f in failures)


def test_a_stale_mutation_string_is_blocked(tmp_path: Path) -> None:
    """مواصفة سلسلتها لم تعد في المصدر تُبلِّغ تغطيةً لا تملكها."""
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("سلسلة لا وجود لها", "x", "test_negative_is_rejected"))
    failures = gmg.check(reg, ci, tmp_path)
    assert any("مواصفة بائتة" in f for f in failures)


def test_an_ambiguous_mutation_string_is_blocked(tmp_path: Path) -> None:
    """سلسلة متكرّرة تجعل موضع الزرع غير محدَّد — فالطفرة تصف عطلاً آخر."""
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("values", "x", "test_negative_is_rejected"))
    failures = gmg.check(reg, ci, tmp_path)
    assert any("تتكرّر" in f for f in failures)


def test_a_missing_test_file_is_blocked(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    reg["mutated"]["fake_guard.py"]["test"] = "tests/nope.py"
    failures = gmg.check(reg, ci, tmp_path)
    assert any("ملفّ الاختبار المُعلَن غير موجود" in f for f in failures)


def test_an_entry_for_a_missing_guard_is_blocked(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(
        mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"),
        unmutated_debt={"vanished_guard.py": "سبب"},
        unmutated_debt_ceiling=1,
    )
    failures = gmg.check(reg, ci, tmp_path)
    assert any("مدخل لحارس غير موجود" in f for f in failures)


def test_debt_growth_is_blocked_by_the_ceiling(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(unmutated_debt={"fake_guard.py": "سبب"}, unmutated_debt_ceiling=0)
    failures = gmg.check(reg, ci, tmp_path)
    assert any("والسقف" in f for f in failures)


def test_a_guard_cannot_be_both_specified_and_in_debt(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(
        mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"),
        unmutated_debt={"fake_guard.py": "سبب"},
        unmutated_debt_ceiling=1,
    )
    failures = gmg.check(reg, ci, tmp_path)
    assert any("مُواصَف ومُعلَن ديناً معاً" in f for f in failures)


# ------------------------------------------------------- الزرع الفعليّ (بطيء)


def test_a_planted_defect_that_turns_the_suite_red_is_proof(tmp_path: Path) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    assert gmg.run_mutations(reg, ci=ci, root=tmp_path) == []


def test_a_green_suite_under_a_planted_defect_is_a_failure(tmp_path: Path) -> None:
    """القاعدة موجودة والاختبار لا يمرّ بها — وهي حالة الحرّاس الثلاثة العُمي."""
    ci = _fake_repo(
        tmp_path,
        test_src=("def test_negative_is_rejected():\n    assert True  # لا يستدعي الحارس إطلاقاً\n"),
    )
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    failures = gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert any("العطل مزروع والاختبار **أخضر**" in f for f in failures)


def test_red_by_the_wrong_test_is_not_proof(tmp_path: Path) -> None:
    """طفرةٌ تكسر الاستيراد تُحمِّر كلّ شيء — و«سقط شيء ما» ليس دليل تغطية."""
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("def check(values):", "def chekc(values):", "test_no_such_name"))
    failures = gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert any("حمرّ بغير الاختبار المُتوقَّع" in f for f in failures)


def test_the_guard_source_is_restored_after_every_mutation(tmp_path: Path) -> None:
    """الزرع يكتب في المصدر الحقيقيّ — واستعادته ليست تفصيلاً بل شرط سلامة."""
    ci = _fake_repo(tmp_path)
    before = (ci / "fake_guard.py").read_text(encoding="utf-8")
    reg = _reg(mutated=_spec("def check(values):", "def chekc(values):", "test_x"))
    gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert (ci / "fake_guard.py").read_text(encoding="utf-8") == before
