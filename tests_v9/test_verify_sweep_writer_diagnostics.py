"""تكذيب تشخيص المكنسة — VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01.

كانت `verify_all_generated --fix` تقول «لم تثبت المصنوعات بعد الحدّ الأقصى للدورات»
وحدها. الرسالة تُقرأ **دورة تبعيّات**، فيذهب القارئ يبحث عن حلقة غير موجودة — بينما
السبب الفعليّ في الحادثة التي كشفتها أنّ ثلاثة كتّاب **لم يُستدعوا أصلاً**: غائبون عن
`_GENERATE_FLAG` رغم أنّ كلّاً منهم يُعلن علم كتابة في مصدره (`--apply`/`--write`).
فتمرّ الدورات الثلاث بلا تغيير، ويُبلَّغ عدم الثبات.

وكانت طباعة الصدق الموجودة أصلاً — «فُحِصت ولا تُولَّد آليّاً» — **غير قابلة للوصول
على مسار الفشل**: تقع بعد الحلقة، والفشل يعود `return 1` قبلها. أي أنّ المعلومة كانت
محسوبة ثمّ تُرمى في اللحظة التي تُحتاج فيها.

هذا الاختبار يقفل الأمرين: الخريطة تحمل الثلاثة بعلمهم الحقيقيّ، والكاشف يفرّق بين
«كاتب لم يُستدعَ» و«فحص بلا مولّد» — وهو التفريق الذي تقوم عليه رسالة التشخيص.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_all_generated", ROOT / "scripts/ci/verify_all_generated.py"
)
sweep = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(sweep)

# الثلاثة الذين انحرفوا فعليّاً وكانوا غائبين عن الخريطة.
_REGRESSION = {
    "capability_linker.py": "--apply",
    "health_readiness_schema_guard.py": "--write",
    "route_residual_classification_guard.py": "--write",
}


@pytest.mark.parametrize(("script", "flag"), sorted(_REGRESSION.items()))
def test_drifted_writers_are_in_the_map_with_their_real_flag(script: str, flag: str):
    """بعلمهم المُعلَن لا بعلم مُوحَّد — `--apply` ليست مرادفاً لـ`--generate`."""
    assert sweep._GENERATE_FLAG.get(script) == flag, (
        f"{script} يجب أن يُستدعى بـ{flag}؛ غيابه عن الخريطة يعني أنّه لا يُستدعى إطلاقاً "
        "فتُبلَّغ «لم تثبت» بلا سبب مفهوم."
    )


def test_detector_names_a_writer_that_declares_a_flag():
    """كاتب يُعلن علم كتابة ⇒ يُرصَد، فتقول الرسالة «أضِفه إلى الخريطة»."""
    assert sweep._declared_write_flags("scripts/ci/capability_linker.py") == ["--apply"]
    assert "--write" in sweep._declared_write_flags("scripts/ci/health_readiness_schema_guard.py")


def test_detector_stays_silent_for_a_check_only_guard():
    """فحص بلا مولّد ⇒ صفر علامات: انحرافه يدويّ بالتصميم، لا خلل في الأداة.

    بلا هذا التمييز تتحوّل رسالة التشخيص إلى اتّهام كلّ فحص بأنّه كاتب مفقود.
    """
    assert sweep._declared_write_flags("scripts/ci/assertion_presence_guard.py") == []


def test_detector_is_safe_on_a_missing_path():
    """مسار غير موجود ⇒ قائمة فارغة لا استثناء — التشخيص لا يُسقِط المكنسة نفسها."""
    assert sweep._declared_write_flags("scripts/ci/does_not_exist_at_all.py") == []


def test_every_mapped_writer_actually_declares_its_flag():
    """إنفاذ عكسيّ: إدخال في الخريطة بعلم لا يُعلنه السكربت ⇒ استدعاء فاشل صامت.

    العلم الفارغ مقصود (تشغيل عارٍ يكتب)، فيُستثنى صراحةً.
    """
    mismatched = []
    for script, flag in sweep._GENERATE_FLAG.items():
        if not flag:
            continue
        rel = next(
            (f"{d}/{script}" for d in sweep._SCRIPT_DIRS if (ROOT / d / script).exists()),
            None,
        )
        if rel is None:
            continue
        if flag not in sweep._declared_write_flags(rel):
            mismatched.append(f"{rel}: الخريطة تقول {flag} والمصدر لا يُعلنه")
    assert not mismatched, "علم في الخريطة لا يطابق مصدر السكربت:\n  " + "\n  ".join(mismatched)


# ─── SWEEP-SELF-CHECK-CANNOT-TELL-A-GUARD-WRITE-FROM-MY-OWN-COMMIT-01 ───
#
# فحصُ المِكنسة لذاتها كان يقارن ``git status --porcelain`` وحده بين طرفَي الفحص، فإيداعُ
# المُشغِّل أثناء التشغيل يُقرأ «حارس كتب أثناء الفحص» (الحادثة: ملفّا ``release/`` مُعدَّلان
# عند البدء، أُودِعا أثناء التشغيل، فاتُّهِم حارسٌ لم يكتب). والحجبُ صحيح؛ النسبةُ خاطئة.


def _git(repo: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "release.sha256").write_text("a\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.setattr(sweep, "ROOT", tmp_path)
    return tmp_path


def test_my_own_commit_during_the_sweep_is_not_blamed_on_a_guard(repo: Path) -> None:
    """إعادةُ إنتاج الحادثة بـgit حقيقيّ: ملفٌّ مُعدَّل عند البدء، يُودَع أثناء «الفحص»."""
    (repo / "release.sha256").write_text("b\n", encoding="utf-8")
    before, head_before = sweep.tree_state(), sweep.head_sha()
    _git(repo, "commit", "-q", "-am", "إيداعي أنا أثناء التشغيل")
    after, head_after = sweep.tree_state(), sweep.head_sha()

    report = "\n".join(sweep.tree_change_report(before, after, head_before, head_after))
    assert report, "الشجرة تغيّرت فعلاً — الحجبُ يجب أن يبقى"
    assert "`HEAD` تحرّكا" in report and head_before[:12] in report and head_after[:12] in report
    assert "حارس كتب أثناء الفحص" not in report, report


def test_a_guard_write_with_head_still_is_still_called_a_guard_write(repo: Path) -> None:
    """الطرفُ الآخر: ``HEAD`` ثابت والشجرة تغيّرت ⇒ حارسٌ كتب، والتفريقُ لا يُسكِته."""
    before, head_before = sweep.tree_state(), sweep.head_sha()
    (repo / "release.sha256").write_text("guard wrote this\n", encoding="utf-8")
    after, head_after = sweep.tree_state(), sweep.head_sha()

    report = "\n".join(sweep.tree_change_report(before, after, head_before, head_after))
    assert head_before == head_after
    assert "حارس كتب أثناء الفحص" in report and "release.sha256" in report


def test_a_head_move_with_an_unchanged_porcelain_still_blocks() -> None:
    """``checkout`` لفرعٍ نظيفٍ أثناء التشغيل: ``--porcelain`` فارغ في الطرفين والخطواتُ
    قرأت شجرتين. لا حكمَ واحدٌ يصفهما ⇒ يُحجَب ويُسمّى."""
    report = sweep.tree_change_report("", "", "a" * 40, "b" * 40)
    assert report and "`HEAD` تحرّكا" in "\n".join(report)


def test_a_quiescent_tree_reports_nothing() -> None:
    assert sweep.tree_change_report(" M x", " M x", "a" * 40, "a" * 40) == []


def test_main_blocks_and_names_my_commit_not_a_guard(repo: Path, monkeypatch, capsys) -> None:
    """الوصلُ في ``main()`` لا في الدالّة وحدها: إيداعٌ داخل ``check_all`` (كلُّ خطوةٍ ✓)
    ⇒ ``rc=1`` ورسالةُ «`HEAD` تحرّك» — لا اتّهامَ حارس. بلا هذا يمكن أن تبقى الدالّةُ
    صحيحةً و``main`` يمرّر ``HEAD`` واحداً للطرفين."""
    (repo / "release.sha256").write_text("b\n", encoding="utf-8")

    def commit_during_checks(_steps):
        _git(repo, "commit", "-q", "-am", "إيداعي أنا أثناء التشغيل")
        return []

    for name, value in {
        "discover": lambda: [],
        "unindexed_files": lambda: [],
        "classify_uncovered": lambda: [],
        "flag_map_problems": lambda _s: [],
        "load_known_drift": lambda: {},
        "check_all": commit_during_checks,
    }.items():
        monkeypatch.setattr(sweep, name, value)
    monkeypatch.setattr(sweep.sys, "argv", ["verify_all_generated.py", "--check"])

    assert sweep.main() == 1
    out = capsys.readouterr().out
    assert "`HEAD` تحرّكا" in out and "حارس كتب أثناء الفحص" not in out, out
