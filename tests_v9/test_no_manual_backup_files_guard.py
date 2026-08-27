"""`DEAD-FILES-TRACKED-AS-IF-THEY-WERE-SOURCE-01` — وشهودُ نطاقه الخمسة.

ملفّان باسم `main.before_p2` كانا متعقَّبَين في خدمتين (`weather-service` ·
`sam2-inference`) وحُذِفا في #948. والحذفُ يُغلِق الحادثة **ولا يمنع الصنف**: لم
يكن في الشجرة ما يرفض إيداعَ الثالث.

وهذا الملفّ يفرض `GUARD-SCOPE-COMPLETENESS` (دفتر القرارات 2026-08-20): لا يُقبَل
حارسٌ جديد إلّا بخمسة شهود — مصدرُ السطح، وما رآه، وما استبعده ولماذا، **وتساوي
المجموعات** لا العدّادات، وشاهدُ طفرة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_g_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_g_{name}"] = module
    spec.loader.exec_module(module)
    return module


guard = _load("no_manual_backup_files_guard")


# ── الشهود ①②③: المصدر وما رآه وما استبعده ──────────────────────────────────
def test_the_surface_is_derived_from_git_not_hand_written():
    witness = guard.discovery_witness()

    assert witness["universe_source"].startswith("git ls-files"), (
        "السطح يجب أن يُشتقّ من git لا من قائمةٍ في ملفّ — القائمة تبيت، والاشتقاق لا"
    )
    assert witness["discovered_count"] > 0, "سطحٌ فارغ يمرّ أخضر عن سؤالٍ لم يُطرَح"
    # لا استثناءَ في هذا الحارس بالقصد؛ ولو أُضيف يوماً فلكلٍّ سببُه المكتوب.
    for path, reason in witness["excluded_paths"].items():
        assert str(reason).strip(), f"استبعادٌ بلا سبب: {path}"


# ── الشاهد ④: تساوي المجموعات، لا عدّادات ────────────────────────────────────
def test_the_guard_sees_exactly_the_tracked_tree():
    """عدّادٌ متطابق يمرّ ولو كان الحارس يفحص ملفّاً ويغفل آخر بالعدد نفسه."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        check=True,
    ).stdout.splitlines()
    expected = {line for line in tracked if line}

    assert set(guard.tracked_files()) == expected


def test_the_tree_carries_no_manual_backup_today():
    offenders = guard.scan()
    assert offenders == [], (
        f"نسخٌ احتياطيّةٌ يدويّةٌ متعقَّبة — تُقرَأ مصدراً وتدخل الجرد والبصمات: {offenders}"
    )


# ── الشاهد ⑤: شاهدُ الطفرة — ما الذي يُحمِّر الحارسَ لو عُطِّل ────────────────
@pytest.mark.parametrize(
    "name",
    [
        "services/weather-service/main.before_p2",  # الحادثةُ الأصليّةُ بالاسم
        "services/sam2-inference/main.before_p2",
        "api/routers/weather.py.bak",
        "api/main.py.orig",
        "docs/plan.md.rej",
        "compose.yml.save",
        "services/auth/main.py~",
        "api/routers/fields.before-refactor.py",
    ],
)
def test_a_manual_backup_name_is_rejected(name):
    assert guard.is_manual_backup(name), f"لاحقةٌ معروفةٌ للنسخ اليدويّة تمرّ: {name}"


@pytest.mark.parametrize(
    "name",
    [
        "services/weather-service/main.py",
        "docs/architecture/ORIGINS.md",  # يحوي `ORIG` — والمطابقةُ ليست بحثاً حرّاً
        "scripts/ci/backup_restore_drill.sh",
        "docs/runbooks/before_push.md",  # `before_` بادئةً لا لاحقةً
        "services/api/original_design.py",
        "tools/rejects.py",
        "data/2026.save.json",  # `.save` ليست نهايةَ الاسم
    ],
)
def test_a_legitimate_name_is_not_flagged(name):
    assert not guard.is_manual_backup(name), f"إيجابيٌّ كاذب — الحارسُ الذي يُنذِر كذباً يُهمَل: {name}"


def test_a_directory_named_like_a_backup_does_not_condemn_its_files():
    """مجلّدٌ `archive.bak/` لا يُدين ما تحته — والمِرساةُ `$` هي ما يكفله.

    **وشاهدُ طفرةٍ نجا فأُسقِط بدل أن يُسجَّل:** كان في الحارس عزلٌ لاسم الملفّ
    (`rsplit("/", 1)[-1]`)، فسجّلتُ طفرةً تُسقِطه وتوقّعتُ احمرارَ هذا الاختبار.
    نجت الطفرة — لأنّ كلَّ بدائل النمط مرساةٌ بـ`$`، فالعزلُ لم يكن يمنع شيئاً.
    والصادقُ هو حذفُ الاحتياط لا تسجيلُ طفرةٍ تدّعي أنّه يحرس. والخاصّيّةُ نفسُها
    تبقى مفروضةً هنا — بآليّتها الحقيقيّة.
    """
    assert not guard.is_manual_backup("archive.bak/services/weather-service/main.py")
    assert guard.is_manual_backup("archive.bak/services/weather-service/main.py.bak")


def test_the_guard_exits_nonzero_when_it_finds_one(tmp_path, monkeypatch):
    """الحارسُ الذي يطبع الشكوى ويُنهي بصفرٍ لا يحجب شيئاً — فخُّ رمز الخروج مقيس."""
    monkeypatch.setattr(guard, "tracked_files", lambda: ["services/x/main.before_p2"])
    assert guard.scan() == ["services/x/main.before_p2"]
    assert guard.main() == 1

    monkeypatch.setattr(guard, "tracked_files", lambda: ["services/x/main.py"])
    assert guard.main() == 0
