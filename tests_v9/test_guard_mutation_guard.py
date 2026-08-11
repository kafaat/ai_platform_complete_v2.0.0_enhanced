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


def test_a_runner_that_never_ran_is_not_evidence(tmp_path: Path, monkeypatch) -> None:
    """خرجٌ بغير صفر يحتمل «سقطت اختبارات» و«لم يُشغَّل شيء»، والثاني ليس دليلاً.

    وقعت الحالة فعلاً: وُضِعت `--run` في وظيفة lint لا تُثبِّت pytest، فانهار
    المُشغِّل قبل جمع اختبار واحد وأُبلِغ عن ١٨ «حمرّ بغير الاختبار المُتوقَّع» —
    صحيحٌ حرفيّاً ويُرسِل قارئه إلى المكان الخطأ.
    """
    ci = _fake_repo(tmp_path)
    monkeypatch.setattr(gmg, "_run_tests", lambda *a, **k: (1, "No module named pytest\n"))
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    failures = gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert any("لم يُشغّل اختباراً" in f for f in failures)


@pytest.mark.parametrize(
    "out,expected",
    [
        ("1 failed, 2 passed in 0.3s", True),
        ("2 passed in 0.1s", True),
        ("no tests ran in 0.01s", True),
        # خطأ تجميع: pytest عمل وجمع وانهار الاستيراد ⇒ **دليل**، وشرط
        # `expect` هو من يقول إنّ الطفرة كسرت الاستيراد لا القاعدة.
        ("1 error in 0.12s", True),
        # وهذان لم يُشغَّل فيهما اختبار قطّ — لا انهيار ولا سلامة مُثبَتان.
        ("ERROR: file or directory not found: tests/nope.py", False),
        ("No module named pytest", False),
        ("", False),
    ],
)
def test_ran_at_all(out: str, expected: bool) -> None:
    assert gmg.ran_at_all(out) is expected


def test_the_guard_source_is_restored_after_every_mutation(tmp_path: Path) -> None:
    """الزرع يكتب في المصدر الحقيقيّ — واستعادته ليست تفصيلاً بل شرط سلامة."""
    ci = _fake_repo(tmp_path)
    before = (ci / "fake_guard.py").read_text(encoding="utf-8")
    reg = _reg(mutated=_spec("def check(values):", "def chekc(values):", "test_x"))
    gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert (ci / "fake_guard.py").read_text(encoding="utf-8") == before


def test_isolated_runner_never_plants_in_the_legal_checkout(tmp_path: Path, monkeypatch) -> None:
    """حتى أثناء الطفرة يبقى checkout الأصلي مطابقاً بايتياً؛ الزرع في المرآة فقط."""
    ci = _fake_repo(tmp_path)
    source = ci / "fake_guard.py"
    before = source.read_bytes()
    observed_roots: list[Path] = []

    def observe_plant(_test_file: str, run_root: Path) -> tuple[int, str]:
        observed_roots.append(run_root)
        assert run_root != tmp_path
        assert source.read_bytes() == before
        mirror_source = run_root / "scripts" / "ci" / "fake_guard.py"
        assert "v < -99" in mirror_source.read_text(encoding="utf-8")
        return (
            1,
            "FAILED tests/test_fake.py::test_negative_is_rejected\n1 failed in 0.01s",
        )

    monkeypatch.setattr(gmg, "_run_tests", observe_plant)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    assert gmg.run_mutations(reg, ci=ci, root=tmp_path, isolate=True) == []
    assert observed_roots
    assert source.read_bytes() == before


def test_real_root_defaults_to_an_isolated_workspace(tmp_path: Path, monkeypatch) -> None:
    """لا يحتاج مستدعي CLI إلى تذكّر راية العزل؛ ROOT القانونيّ يفرضها افتراضياً."""
    ci = _fake_repo(tmp_path)
    source = ci / "fake_guard.py"
    before = source.read_bytes()

    def observe_default(_test_file: str, run_root: Path) -> tuple[int, str]:
        assert run_root != tmp_path
        assert source.read_bytes() == before
        return (
            1,
            "FAILED tests/test_fake.py::test_negative_is_rejected\n1 failed in 0.01s",
        )

    monkeypatch.setattr(gmg, "ROOT", tmp_path)
    monkeypatch.setattr(gmg, "_run_tests", observe_default)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    assert gmg.run_mutations(reg, ci=ci, root=tmp_path) == []
    assert source.read_bytes() == before


def test_abrupt_isolated_runner_failure_cannot_contaminate_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    """انقطاع المُشغّل بعد الزرع لا يحتاج استعادةً في checkout: لم يُكتَب فيه أصلاً."""
    ci = _fake_repo(tmp_path)
    source = ci / "fake_guard.py"
    before = source.read_bytes()

    class AbruptRunnerStop(BaseException):
        pass

    def stop_after_plant(_test_file: str, run_root: Path) -> tuple[int, str]:
        mirror_source = run_root / "scripts" / "ci" / "fake_guard.py"
        assert "v < -99" in mirror_source.read_text(encoding="utf-8")
        assert source.read_bytes() == before
        raise AbruptRunnerStop

    monkeypatch.setattr(gmg, "_run_tests", stop_after_plant)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    with pytest.raises(AbruptRunnerStop):
        gmg.run_mutations(reg, ci=ci, root=tmp_path, isolate=True)
    assert source.read_bytes() == before


def test_the_wrong_test_branch_names_what_actually_failed(tmp_path: Path) -> None:
    """**فرعٌ يقول ما لم يسقط ولا يقول ما سقط لا يُشخَّص من سجلّه.**

    `GUARD-MUTATION-RUN-FLAKED-ONCE-UNREPRODUCED-01`: أخفق هذا الفرع مرّةً على
    `claim_base_guard.py[4]` ولم يتكرّر في ثلاثة تشغيلات تالية على الشجرة نفسها،
    فلم يبقَ من الحادثة إلّا نفيُ المتوقَّع. والحارس **بوّابة حاجبة**، وفحصٌ يخضرّ
    بإعادة التشغيل يُدرّب قارئه على إعادة التشغيل بدل القراءة — فيُطفَأ بلا تعديل سطر.

    **والقياس على `run_mutations` لا على `failing_tests`، لأنّ أوّل صياغة قاست
    الدالّة وحدها فبقيت خضراء تحت طفرتها**: الطفرة تنزع النداء من الفرع، والدالّة
    سليمة. أي أنّ اختبار التشخيص وقع في «قدرة موجودة لا تجري» — والمخرَج الجديد نفسه
    هو ما سمّى لي الاختبار الساقط فانكشف العطل في أوّل تشغيل.
    """
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("def check(values):", "def chekc(values):", "test_no_such_name"))
    failures = gmg.run_mutations(reg, ci=ci, root=tmp_path)

    assert any("حمرّ بغير الاختبار المُتوقَّع" in f for f in failures)

    # **التأكيد على سطر `الساقط فعلاً` وحده، لا على الرسالة كلّها.** أوّل صياغة بحثت
    # عن الاسم في الرسالة — وهي تحمل ذيل مخرَج pytest الخام الذي يحوي الاسم أصلاً،
    # فكان التأكيد يمرّ ولو نُزِع الاستخراج بالكامل. أمسكته الطفرة المزروعة.
    named = [
        line.split("الساقط فعلاً:", 1)[1].strip()
        for f in failures
        for line in f.splitlines()
        if "الساقط فعلاً:" in line
    ]
    # الطفرة هنا تكسر الاستيراد، فيسقط **الاختباران** الصناعيّان — والسطر يقول ذلك
    # صراحةً. وهو الفارق العمليّ: «سقط الملفّ كلّه» تُقرأ انهيار استيراد، و«سقط
    # اختبارٌ شقيق واحد» تُقرأ تداخلاً بين طفرتين متجاورتين. الأولى شخّصت حادثة
    # `claim_base_guard.py[4]` في أوّل تشغيل بعد هذا الإصلاح.
    assert named == ["test_clean_input_passes · test_negative_is_rejected"], named


def test_failing_tests_separates_a_named_failure_from_a_silent_runner() -> None:
    """قائمة فارغة **خبرٌ بذاته**: تفصل «سقط اختبار آخر» عن «لم يُسمِّ المُشغِّل شيئاً»."""
    out = (
        "=========================== short test summary info ===========================\n"
        "FAILED tests_v9/test_x.py::test_something_else_broke - AssertionError\n"
        "ERROR tests_v9/test_x.py::test_collection_blew_up\n"
        "========================= 1 failed, 2 passed in 0.10s =========================\n"
    )
    assert gmg.failing_tests(out) == ["test_collection_blew_up", "test_something_else_broke"]
    assert gmg.failing_tests("INTERNALERROR> ImportError: no module named x") == []


def test_mutation_runner_pins_deterministic_environment() -> None:
    source = (ROOT / "scripts/ci/guard_mutation_guard.py").read_text(encoding="utf-8")
    for contract in (
        '"PYTHONHASHSEED": "0"',
        '"PYTHONUTF8": "1"',
        '"LC_ALL": "C.UTF-8"',
        '"TZ": "UTC"',
        'TemporaryDirectory(prefix="sahool-guard-mutation-")',
    ):
        assert contract in source


def test_inconsistent_wrong_test_repeats_are_classified_non_deterministic(
    tmp_path: Path, monkeypatch
) -> None:
    ci = _fake_repo(tmp_path)
    reg = _reg(mutated=_spec("v < 0", "v < -99", "test_negative_is_rejected"))
    outputs = iter(
        [
            (1, "FAILED tests/test_fake.py::test_clean_input_passes\n1 failed"),
            (1, "FAILED tests/test_fake.py::test_clean_input_passes\n1 failed"),
            (1, "FAILED tests/test_fake.py::test_negative_is_rejected\n1 failed"),
            (1, "FAILED tests/test_fake.py::test_clean_input_passes\n1 failed"),
        ]
    )
    monkeypatch.setattr(gmg, "_run_tests", lambda *a, **k: next(outputs))
    failures = gmg.run_mutations(reg, ci=ci, root=tmp_path)
    assert any("NON_DETERMINISTIC" in failure for failure in failures)


def test_sigterm_restoration_ledger_is_installed() -> None:
    source = (ROOT / "scripts/ci/guard_mutation_guard.py").read_text(encoding="utf-8")
    assert "_ACTIVE_RESTORES" in source
    assert "signal.SIGTERM" in source
    assert "atexit.register(_restore_active_sources)" in source


def test_repeats_that_all_say_expected_red_are_not_called_stable_wrong_test():
    """Measured on #795: three re-diagnoses said expected_red and the label said the
    opposite.

    stable measures whether the repeats agree **with each other**, not whether they
    agree with the first observation. When every repeat reproduces the expected red, the
    mutation works and the anomaly was the first observation alone — calling that
    STABLE_WRONG_TEST inverts what happened, and a wrong diagnosis costs more than none.

    It still blocks: a check that greens on re-run trains its reader to re-run instead of
    read. Only the name changes, so the incident is readable from its log.
    """
    source = Path("scripts/ci/guard_mutation_guard.py").read_text(encoding="utf-8")
    assert "FLAKY_FIRST_OBSERVATION" in source
    marker = source.index("repeat_kinds")
    window = source[marker : marker + 400]
    assert 'repeat_kinds == {"expected_red"}' in window
    assert "FLAKY_FIRST_OBSERVATION" in window
    # and the branch must come BEFORE the stable branch, or it can never be reached
    assert window.index("FLAKY_FIRST_OBSERVATION") < window.index("STABLE_WRONG_TEST")


def test_the_runner_blocks_bytecode_caching():
    """‏``.pyc`` يُبطَل بـ(mtime, size) لا بالمحتوى — وطفرتان متساويتا الطول تخدعانه.

    ``MUTATION-VERDICT-CONTRADICTS-ITS-OWN-DIAGNOSIS-01``، السبب الجذريّ **مُثبَت
    بإعادة إنتاج محكومة** (2026-08-05): ``claim_base_guard.py[3]`` و``[4]`` هما الزوج
    الوحيد المتساوي الطول بين ثمانٍ (٧١٨٨ لكلٍّ). بتثبيت ``mtime`` بين الكتابتَين تسقط
    الطفرة ``[4]`` على **اختبار ``[3]``** — توقيع الـCI حرفيّاً؛ ومع منع الـbytecode
    تسقط على اختبارها. ثلاث ملاحظات كانت تُسمّى «رقيعة» وهي سببٌ واحد قابل للقياس.
    """
    source = (ROOT / "scripts/ci/guard_mutation_guard.py").read_text(encoding="utf-8")
    assert '"PYTHONDONTWRITEBYTECODE": "1"' in source, (
        "بلا هذا تبيت بايتكود طفرةٍ سابقة وتُحاكَم طفرةٌ لاحقة بأثرها"
    )


def test_a_restore_that_did_not_restore_is_reported():
    """الحارس الذي يزرع ويستعيد يحتاج أن **يُثبت** استعادته، لا أن يفترضها.

    بلا هذا الفحص، أيّ تسرّبٍ بين طفرتين متتاليتين يظهر «عشوائيّةً» لا عطلاً — وهو ما
    كلّف ثلاث ملاحظات قبل عزل السبب. والمقارنة بالمحتوى لا بالحجم، لأنّ تساوي الطول هو
    بالضبط ما أخفى العطل.
    """
    source = (ROOT / "scripts/ci/guard_mutation_guard.py").read_text(encoding="utf-8")
    assert 'src.read_text(encoding="utf-8") != original' in source
    assert "الاستعادة لم تُعِد المصدر إلى أصله" in source
