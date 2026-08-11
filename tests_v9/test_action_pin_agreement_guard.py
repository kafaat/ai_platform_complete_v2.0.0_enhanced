"""`ACTION-PIN-HALF-UPGRADED-01` — التثبيت يُرقّى كلّه أو لا يُرقّى.

**ولماذا هذا الحارس أصلاً:** `github_actions_policy_guard` يسأل سؤالاً واحداً —
«أمثبَّتٌ ببصمة كاملة؟» — وجوابُه «نعم» على شجرةٍ نصفُ مواضعها على البصمة القديمة.
فالبوّابة القائمة لا ترى صنف «نصف الترقية» أصلاً، وقد وقع مرّتين مقيستين: سبع
مراسٍ لا خمس في `#823`، وحزمةٌ تُبدّل ثلاثة من ثلاثة وعشرين في هذه الشريحة.

**والاختبارات على شجرةٍ مُركَّبة** (`tmp_path`) لا على `.github/workflows` الحيّة:
حارسٌ لا يُكذَّب إلّا بتحريك الشجرة الحقيقيّة يصير تكذيبُه معتمداً على حالتها
اليوم، فيمرّ خضراءَ صامتة يوم تتغيّر. والتشغيل على الشجرة الحيّة يبقى مساراً
ثانياً (اختبار واحد أدناه).

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "action_pin_agreement_guard.py"

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_SHA_C = "c" * 40


def _load():
    spec = importlib.util.spec_from_file_location("action_pin_agreement_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


@pytest.fixture
def clean_baseline(monkeypatch):
    """أساسٌ فارغ للأشجار المُركَّبة.

    **وهذه ليست زينة:** الأساس الحقيقيّ يحمل `actions/checkout` و`actions/setup-python`،
    وهما لا يردان في شجرةٍ مُركَّبة — فيُشعِل بندُ «المدخل البائت» في كلّ اختبارٍ
    لا يخصّه. أي أنّ الاختبار كان سيسقط لسببٍ غير سببه المُعلَن، وهو الصنف الذي
    يُطارده `guard_mutation_guard` بعينه.
    """
    monkeypatch.setattr(guard, "DIVERGENCE_BASELINE", {})
    return guard.DIVERGENCE_BASELINE


def _tree(tmp_path: Path, **files: str) -> Path:
    root = tmp_path / "workflows"
    root.mkdir(exist_ok=True)
    for name, body in files.items():
        (root / f"{name}.yml").write_text(body, encoding="utf-8")
    return root


def _uses(action: str, sha: str, tag: str | None = None) -> str:
    line = f"      - uses: {action}@{sha}"
    return f"{line} # {tag}\n" if tag else f"{line}\n"


def test_one_sha_per_action_passes(tmp_path, clean_baseline):
    root = _tree(
        tmp_path,
        a=_uses("acme/upload", _SHA_A, "v7.0.1"),
        b=_uses("acme/upload", _SHA_A, "v7.0.1"),
    )
    assert guard.violations(guard.pins(root)) == []


def test_a_half_upgrade_is_blocked(tmp_path, clean_baseline):
    """الصنف بعينه: ملفٌّ رُقّي وملفٌّ لم يُرقَّ، وكلاهما مثبَّتٌ ببصمة كاملة."""
    root = _tree(
        tmp_path,
        upgraded=_uses("acme/upload", _SHA_A, "v7.0.1"),
        forgotten=_uses("acme/upload", _SHA_B, "v4"),
    )
    problems = guard.violations(guard.pins(root))
    assert problems, "بصمتان لعملٍ واحد يجب أن تُحجَبا"
    assert "acme/upload" in problems[0]
    # الرسالة تسمّي البصمتين — رسالةٌ تقول «تباعد» تترك قارئها يبحث في ثلاثة عشر ملفّاً.
    assert _SHA_A in problems[0] and _SHA_B in problems[0]


def test_a_sha_carrying_two_different_tags_is_blocked(tmp_path, clean_baseline):
    """`@<بصمة v7> # v4` أسوأ من تعليقٍ غائب: يُقرأ وسماً ويُبنى عليه."""
    root = _tree(
        tmp_path,
        a=_uses("acme/upload", _SHA_A, "v7.0.1"),
        b=_uses("acme/upload", _SHA_A, "v4"),
    )
    problems = guard.violations(guard.pins(root))
    assert problems and "يكذب" in problems[0]


def test_a_missing_tag_comment_is_not_a_violation(tmp_path, clean_baseline):
    """التعليق اختياريّ؛ المُدان **تناقضُه** لا غيابُه — وإدانةُ الغياب تُنتِج ضجيجاً."""
    root = _tree(
        tmp_path,
        a=_uses("acme/upload", _SHA_A, "v7.0.1"),
        b=_uses("acme/upload", _SHA_A),
    )
    assert guard.violations(guard.pins(root)) == []


def test_a_baselined_action_may_diverge_up_to_its_recorded_count(tmp_path, clean_baseline):
    clean_baseline["acme/checkout"] = 2
    root = _tree(
        tmp_path,
        a=_uses("acme/checkout", _SHA_A),
        b=_uses("acme/checkout", _SHA_B),
    )
    assert guard.violations(guard.pins(root)) == []


def test_one_more_divergence_than_the_baseline_is_blocked(tmp_path, clean_baseline):
    """الأساس **بعدده** لا بوجوده: مُدرَجٌ بلا عدد يبتلع كلّ تباعدٍ لاحق."""
    clean_baseline["acme/checkout"] = 2
    root = _tree(
        tmp_path,
        a=_uses("acme/checkout", _SHA_A),
        b=_uses("acme/checkout", _SHA_B),
        c=_uses("acme/checkout", _SHA_C),
    )
    problems = guard.violations(guard.pins(root))
    assert problems and "3 بصمةً والمسموح 2" in problems[0]


def test_unifying_without_lowering_the_baseline_is_blocked(tmp_path, clean_baseline):
    """درسُ الراتشِت مرّتين قبله: أساسٌ يبقى بعد إصلاحٍ يبتلع عودة العطل صامتاً."""
    clean_baseline["acme/checkout"] = 2
    root = _tree(tmp_path, a=_uses("acme/checkout", _SHA_A))
    problems = guard.violations(guard.pins(root))
    assert problems and "اخفِض" in problems[0]


def test_a_stale_baseline_entry_is_blocked(tmp_path, clean_baseline):
    """مدخلٌ لعملٍ زال يُقرأ ديناً قائماً — وهو الصنف نفسه بوجهٍ آخر."""
    clean_baseline["acme/gone"] = 2
    root = _tree(tmp_path, a=_uses("acme/upload", _SHA_A))
    problems = guard.violations(guard.pins(root))
    assert any("بائت" in p for p in problems)


def test_every_baselined_action_carries_a_written_reason():
    """عددٌ بلا سبب يُنقَل بين الأجيال بلا معنى — وهو ما يجعل الأساس يتضخّم."""
    assert set(guard.DIVERGENCE_BASELINE) == set(guard.WHY)
    for action, why in guard.WHY.items():
        assert len(why) > 40, f"سببُ {action} أقصر من أن يكون سبباً"


def test_a_missing_workflows_directory_fails_closed(tmp_path):
    """«لم يُقَس» ليس «متّسق» — ومجلّدٌ غائب يُفشِل بدل أن يُقرأ صفراً."""
    with pytest.raises(SystemExit):
        guard.main(["--workflows", str(tmp_path / "nope")])


def test_the_live_tree_holds_exactly_one_upload_artifact_pin():
    """المسار الثاني: الشجرة الحيّة نفسها — وهو ما يجعل نصفَ ترقيةٍ يُحمِرّ في CI."""
    observed = guard.pins(_ROOT / ".github" / "workflows")
    shas = observed.get("actions/upload-artifact")
    assert shas is not None, "العمل غير موجود — تغيّرت الشجرة، راجع الحارس"
    assert len(shas) == 1, f"بصماتٌ متعدّدة لـupload-artifact: {sorted(shas)}"
    (tags,) = shas.values()
    assert tags == {"v7.0.1"}, f"وسمٌ غير متوقّع بجانب البصمة: {sorted(tags)}"


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0
