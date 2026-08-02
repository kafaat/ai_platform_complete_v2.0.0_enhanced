"""`DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` — الشطران L3 و L4.

**L3 (`.gitattributes`)** شبكة أمان لا حلّ دلاليّ، و**L4 (`rerere`)** إعداد محلّيّ لا
بوّابة. وهذا الملفّ يقيس ما يستطيع قياسه فيهما — لا أكثر:

  · L3: الأسطر الأربعة موجودة بالمسارات المقيسة، وليست glob عريضاً.
  · L4: السكربت idempotent فعليّاً، ويكتب `--local` لا `--global`.

**ما لا يُقاس هنا ويُقال صراحةً:** أنّ `merge=union` يعمل — ذاك مُثبَت في
`test_brain_duplicate_gap_identity_guard.py` بمستودع git مؤقّت حقيقيّ. وأنّ rerere
يُعيد تطبيق حلّ — يحتاج تعارضاً مكرّراً عبر جلستين، وهو خارج مدى فحص الوحدة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ATTRS = _ROOT / ".gitattributes"
_BOOTSTRAP = _ROOT / "scripts" / "dev" / "enable_rerere.sh"

# المسارات الأربعة المقيسة: 89 + 77 + 75 + 32 = ٢٧٣ من ٢٨١ لمسة على sahool-brain/.
_APPEND_ONLY = (
    "sahool-brain/gaps/registry.md",
    "sahool-brain/hot.md",
    "sahool-brain/log.md",
    "sahool-brain/decisions/ledger.md",
)


# ───────────────────────────── L3 ─────────────────────────────


def test_every_measured_append_only_file_has_a_union_merge_rule():
    text = _ATTRS.read_text(encoding="utf-8")
    rules = {
        m.group("path")
        for m in re.finditer(r"^(?P<path>\S+)\s+merge=union\s*$", text, re.MULTILINE)
    }
    missing = [p for p in _APPEND_ONLY if p not in rules]
    assert not missing, "ملفّات إلحاقيّة بلا شبكة union: " + " · ".join(missing)


def test_the_union_scope_is_the_four_measured_paths_not_a_wide_glob():
    """توسيع النطاق إلى `**/*.md` يُطبّق union على وثائق لم تُقَس حركتها.

    وunion على ملفّ **ليس** إلحاقيّاً يُنتج نصّاً مضموماً بلا معنى بدل تعارض يُقرأ —
    أي يستبدل فشلاً صاخباً بفساد صامت، وهو عكس المقصود.
    """
    text = _ATTRS.read_text(encoding="utf-8")
    union_paths = re.findall(r"^(\S+)\s+merge=union\s*$", text, re.MULTILINE)
    assert set(union_paths) == set(_APPEND_ONLY)
    assert not any("*" in p for p in union_paths), "لا أنماط عريضة في نطاق union"


def test_the_guard_covers_exactly_what_union_covers():
    """الشبكة والحارس على نفس النطاق — بقعةٌ يضمّها union ولا يفحصها الحارس ثغرة."""
    sys.path.insert(0, str(_ROOT / "scripts" / "ci"))
    from brain_duplicate_gap_identity_guard import DEFAULT_TARGETS

    assert set(DEFAULT_TARGETS) == set(_APPEND_ONLY)


def test_the_limits_are_written_where_the_rule_is():
    """حدّا L3 مكتوبان بجوار الأسطر لا في وثيقة بعيدة.

    قاعدةٌ تبدو حلّاً كاملاً وهي شبكة أمان تُنتج ثقةً في غير محلّها؛ ومن يقرأ
    `.gitattributes` لن يفتح رنبوكاً ليكتشف أنّ GitHub يتجاهلها.
    """
    text = _ATTRS.read_text(encoding="utf-8")
    assert "GitHub" in text, "حدّ GitHub غير مذكور عند القاعدة"
    assert "brain_duplicate_gap_identity_guard" in text, "الحارس المرافق غير مذكور"


# ───────────────────────────── L4 ─────────────────────────────


def _run_bootstrap(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_BOOTSTRAP)],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "HOME": str(repo),
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        timeout=120,
    )


@pytest.fixture()
def throwaway_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "."],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return repo


def test_the_bootstrap_is_idempotent(throwaway_repo):
    """شرط القبول: تشغيلان متتاليان ⇒ نجاح، ولا تغيّر في الإعداد.

    سكربت تهيئة يفشل في المرّة الثانية يُدرَّب مُشغّله على تجنّبه، فيبقى الإعداد
    غير مضبوط أصلاً.
    """
    first = _run_bootstrap(throwaway_repo)
    assert first.returncode == 0, first.stderr

    def snapshot() -> str:
        return (throwaway_repo / ".git" / "config").read_text(encoding="utf-8")

    after_first = snapshot()
    second = _run_bootstrap(throwaway_repo)
    assert second.returncode == 0, second.stderr
    assert snapshot() == after_first, "التشغيل الثاني غيّر الإعداد"


def test_the_bootstrap_enables_both_settings(throwaway_repo):
    _run_bootstrap(throwaway_repo)
    for key in ("rerere.enabled", "rerere.autoupdate"):
        value = subprocess.run(
            ["git", "config", "--local", "--bool", key],
            cwd=throwaway_repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        assert value == "true", f"{key} = {value!r}"


def test_it_writes_local_scope_only(throwaway_repo):
    """`--global` يُغيّر كلّ مستودعات المستخدم بقرارٍ اتُّخذ في مستودع واحد.

    الفحص على **الأسطر التنفيذيّة** لا على الملفّ كلّه: أوّل صياغة رفضت الملفّ لأنّ
    تعليقه يشرح *لماذا* لا نستعمل `--global` — أي عاقبت الشرح على ذكر ما يمنعه.
    وهو صنف الإيجابيّ الكاذب الذي أُصلِح مرّتين في هذه الجلسة.
    """
    code = [
        line.split("#", 1)[0].strip()
        for line in _BOOTSTRAP.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    body = "\n".join(code)
    assert "--global" not in body, "السكربت يكتب إعداداً عالميّاً"
    assert body.count("--local") >= 4, "الكتابة والتحقّق كلاهما محلّيّ"


def test_it_verifies_after_writing_not_before(throwaway_repo):
    """`git config` قد ينجح صامتاً؛ فالتحقّق بعد الكتابة لا قبلها."""
    src = _BOOTSTRAP.read_text(encoding="utf-8")
    write_at = src.index("git config --local rerere.enabled true")
    verify_at = src.index('test "$(git config --local --bool rerere.enabled)"')
    assert write_at < verify_at


def test_it_is_not_wired_as_a_ci_gate():
    """**حدّ مقصود.** CI يبدأ من نسخة نظيفة بلا `rr-cache`؛ فإفشاله على غياب rerere
    إبلاغٌ عن سؤال لم يُطرَح. يُقاس بأنّ السكربت غير مذكور في أيّ workflow.
    """
    workflows = _ROOT / ".github" / "workflows"
    citing = [
        path.name
        for path in sorted(workflows.glob("*.yml"))
        if "enable_rerere" in path.read_text(encoding="utf-8")
    ]
    assert not citing, "rerere صار بوّابة CI: " + " · ".join(citing)
