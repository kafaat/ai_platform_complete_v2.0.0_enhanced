"""قائمة اختبارات CI اليدويّة تُقارَن بمحتوى المجلّد، لا بذاكرة من كتبها.

``ARCH-TESTS-UNLISTED-IN-CI-01``. ``pytest.ini`` يحصر ``testpaths`` في ``tests_v9``،
فكلّ ما تحت ``tests/`` يُشغَّل بقائمة مسارات صريحة في الـworkflows. قائمة يدويّة تبيت
بصمت — والقياس يوم 2026-07-28 قال **١٧ من ٥٤** خارجها، منها حرّاس بُنيت في اليوم
نفسه، ومنها اختبار كان ``hot.md`` يدّعي أنّه **يفرض** ثلاثيّة عدّ المسارات.

هذه الاختبارات لا تفحص القائمة سطراً سطراً (هشّ) بل **الشرط الذي يجعلها كاملة**.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_GUARD = ROOT / "scripts" / "ci" / "arch_test_ci_coverage_guard.py"
_BASELINE = ROOT / "docs" / "architecture" / "arch_test_ci_coverage_baseline.json"


def _load():
    spec = importlib.util.spec_from_file_location("arch_cov", _GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def test_no_architecture_test_sits_outside_ci():
    """الضمانة الجوهريّة — وهي ما كان غائباً تماماً."""
    unlisted = sorted(MOD.present() - MOD.referenced() - set(MOD.exempt()))
    assert not unlisted, (
        f"اختبارات لا يُشغّلها أيّ workflow — أدرِجها في capability-governance.yml: {unlisted}"
    )


def test_this_guard_is_itself_wired():
    """الفخّ الذي وقع فيه غيري مرّتين اليوم: حارس ضدّ العلّة يقع فيها.

    مكنسة المصنوعات (#691) لم تكن موصولة بأيّ workflow، وكذلك اختبارها. فلا معنى
    لحارس اكتمالٍ يمكن أن يكون هو نفسه خارج الاكتمال.
    """
    assert Path(__file__).name in MOD.referenced()


def test_a_workflow_naming_a_missing_file_is_caught():
    """اسم بائت في workflow يمرّ أخضر بلا تنفيذ شيء — طمأنينة كاذبة.

    ليس افتراضيّاً: أدرجتُ اسم هذا الملفّ في الـworkflow قبل كتابته، فالتقطه الحارس.
    """
    ghosts = sorted(MOD.referenced() - MOD.present())
    assert not ghosts, f"workflow يذكر ملفّات غير موجودة: {ghosts}"


def test_every_exemption_carries_a_gap_evidence_and_a_closing_condition():
    """«معفى» بلا سبب وشرط إغلاق ليس تسجيلاً بل إعفاءً صامتاً."""
    if not _BASELINE.exists():
        # حالة النجاح النهائيّة: لا اختبار معماريّ خارج CI، فلا أساس. حُذِف الملفّ
        # عند إغلاق آخر إعفاء (runtime_environment_preflight) — والقاعدة المكتوبة
        # فيه كانت «الأساس فارغ ⇒ احذف الملفّ بدل تركه هيكلاً».
        return
    data = json.loads(_BASELINE.read_text(encoding="utf-8"))
    for name, entry in data["exempt"].items():
        assert (ROOT / "tests" / "architecture" / name).exists(), f"إعفاء بائت: {name}"
        for field in ("gap", "failing", "evidence", "to_close"):
            assert entry.get(field), f"{name} ينقصه {field}"


def test_the_baseline_never_silently_grows():
    """ثلاثة مُقاسة على ``3b7f837c``. الزيادة إخفاءُ اختبارٍ لا تسجيلُه.

    اختبار جديد يُدرَج في workflow. لا يُضاف هنا إلّا إن كان **يفشل لسبب مُسجَّل**،
    وعندها يلزم قرار — لا تمريرة.
    """
    if not _BASELINE.exists():
        return  # صفر إعفاء — الحدّ الأدنى الذي لا يُتجاوَز نزولاً
    data = json.loads(_BASELINE.read_text(encoding="utf-8"))
    assert len(data["exempt"]) <= 1, (
        "أساس الإعفاء نما — يتقلّص ولا ينمو (السقف 1 بعد إغلاق preflight)."
    )


def test_exempted_files_are_not_also_listed():
    """إعفاء ملفّ مُدرَج تناقض: إمّا يعمل فلا يُعفى، أو يفشل فلا يُدرَج."""
    both = sorted(set(MOD.exempt()) & MOD.referenced())
    assert not both, f"مُعفى ومُدرَج معاً: {both}"
