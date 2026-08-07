"""حارس ``TESTS-UNMARKED-DESELECTED-01``: الأساس المُجمَّد يتقلّص ولا يُهادَن.

الحارس نفسه يعمل كخطوة صريحة في `ci.yml` (وظيفة *Unit Tests*)، فهذه الاختبارات لا
تُعيد فحص ما يفحصه — تحرس **دلالته**: أنّ القراءة تطابق ما ينتقيه pytest فعلاً، وأنّ
الأساس معرفة لا قائمة تجاهُل، وأنّه لا ينمو صامتاً.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "ci" / "test_marker_coverage_guard.py"
_BASELINE = ROOT / "docs" / "testing" / "unmarked_tests_baseline.json"

# سقف راتشِت لا هدف: يُخفَض بوسم ملفّ أو حذفه، ولا يُرفَع لتمرير بوّابة.
_MAX_UNMARKED = 9


def _load():
    spec = importlib.util.spec_from_file_location("test_marker_coverage_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["unmarked"]


def test_the_tree_matches_the_baseline():
    """الثابت: لا ملفّ بلا علامة خارج الأساس، ولا مدخل بائت فيه."""
    assert MOD.check() == 0


def test_the_baseline_never_silently_grows():
    assert len(_baseline()) <= _MAX_UNMARKED, f"نما الأساس: {sorted(_baseline())}"


def test_every_baseline_entry_carries_a_measured_reason():
    """«خامد معروف» بلا سبب ودليل يتحوّل إلى قائمة تجاهُل دائمة."""
    for path, entry in _baseline().items():
        assert entry.get("reason"), f"{path}: بلا reason"
        assert len(entry.get("evidence", "").strip()) >= 30, f"{path}: دليل أقصر من تفسير"
        assert (ROOT / path).is_file(), f"{path}: مدخل لملفّ غير موجود"


def test_entries_that_are_not_merely_deferred_name_a_closing_condition():
    """المؤجَّل يحتاج شرط إغلاق؛ ما يعمل بمسار صريح أو لا يجمع اختبارات لا يحتاجه."""
    exempt = {"runs_by_explicit_path", "not_a_pytest_module"}
    for path, entry in _baseline().items():
        if entry["reason"] in exempt:
            continue
        assert entry.get("to_close"), f"{path}: مؤجَّل بلا شرط إغلاق"


def test_the_reading_matches_the_baseline():
    unmarked = set(MOD.unmarked())
    assert unmarked == set(_baseline()), "القراءة تخالف الأساس"
    marked = [f for f in MOD.tracked_test_files() if f not in unmarked]
    assert len(marked) > 500, "انهيار الكشف: كلّ الملفّات تبدو بلا علامة"


# ─────────────────────────────────────────────────────────────────────────────
# مستودع اصطناعيّ: الحارس يقرأ `git ls-files`، فالحالات المزروعة تحتاج شجرةً
# مُتعقَّبة. لا يُكتَب شيء في الشجرة الحيّة — درسُ `probe_leak_guard` الذي تسرّب
# مِسباره فأنتج تشخيصاً خاطئاً كلّف جولة اعتماد كاملة.
# ─────────────────────────────────────────────────────────────────────────────


def _repo(tmp_path: Path, files: dict[str, str], markers=("unit", "integration")) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    block = "\n".join(f"    {name}: مُعلَنة" for name in markers)
    (tmp_path / "pytest.ini").write_text(f"[pytest]\nmarkers =\n{block}\n", encoding="utf-8")
    for rel, body in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _unmarked_in(monkeypatch, root: Path) -> set[str]:
    monkeypatch.setattr(MOD, "ROOT", root)
    monkeypatch.setattr(MOD, "PYTEST_INI", root / "pytest.ini")
    return set(MOD.unmarked())


def test_a_file_in_a_subdirectory_is_seen(tmp_path, monkeypatch):
    """الثقب الذي أسقط ملفّين حقيقيّين: النمط المسطّح لا يرى `tests_v9/<دليل>/`.

    ثمانية اختبارات في `tests_v9/runtime_activation/` كانت ميّتة في كلّ وظيفة،
    و**لم تكن قابلة للظهور في الأساس** — الحارس المبنيّ لهذا الصنف لا يراها.
    """
    root = _repo(
        tmp_path,
        {
            "tests_v9/test_flat.py": "import pytest\n\npytestmark = pytest.mark.unit\n",
            "tests_v9/nested/test_deep.py": "def test_x():\n    pass\n",
        },
    )
    assert _unmarked_in(monkeypatch, root) == {"tests_v9/nested/test_deep.py"}


def test_a_marker_that_pytest_ini_does_not_declare_is_not_a_marker(tmp_path, monkeypatch):
    """`pytestmark = pytest.mark.asyncio` كان يُقرأ «موسوماً» — وهو مُستبعَد من كلّ وظيفة.

    التعبير النمطيّ القديم يطابق `pytestmark` مجرّداً، فالاسم لا يُفحَص أصلاً.
    """
    root = _repo(
        tmp_path,
        {"tests_v9/test_async_only.py": "import pytest\n\npytestmark = pytest.mark.asyncio\n"},
    )
    assert _unmarked_in(monkeypatch, root) == {"tests_v9/test_async_only.py"}


def test_a_marker_named_only_in_prose_is_not_a_marker(tmp_path, monkeypatch):
    """حارسٌ يُطلِق على توثيق ما يمنعه يُعطَّل في أوّل يوم — وهنا العكس أخطر:

    ذِكر `pytest.mark.unit` في تعليق أو نصّ كان يُبيّض ملفّاً خامداً.
    """
    root = _repo(
        tmp_path,
        {
            "tests_v9/test_prose.py": (
                '"""مثال توضيحيّ: pytestmark = pytest.mark.unit."""\n\n'
                'NOTE = "استعمل pytest.mark.integration"\n\n'
                "def test_x():\n    pass\n"
            )
        },
    )
    assert _unmarked_in(monkeypatch, root) == {"tests_v9/test_prose.py"}


def test_a_class_level_marker_counts(tmp_path, monkeypatch):
    """ثمانية ملفّات في هذه الشجرة تَسِم على مستوى الصنف وحده.

    أوّل صياغة عندي أغفلت مُزخرِفات الأصناف فأعلنتها بلا علامة — ثمانية إنذارات
    كاذبة. أمسكه التصديق بـpytest أدناه، لا قراءتي.
    """
    root = _repo(
        tmp_path,
        {
            "tests_v9/test_klass.py": (
                "import pytest\n\n\n@pytest.mark.unit\nclass TestThing:\n"
                "    def test_x(self):\n        pass\n"
            )
        },
    )
    assert _unmarked_in(monkeypatch, root) == set()


def test_the_marker_names_actually_follow_pytest_ini(tmp_path, monkeypatch):
    """الاختبار السابق أكّد **قيمة** `registered_markers()` فمرّ بينما الأسماء مُصلَّبة
    في التعبير النمطيّ والدالّة زينة تُستعمل في سطر النجاح وحده.

    القياس الصحيح تفاضليّ: الملفّ ذاته يتبدّل حكمه بتبدّل `pytest.ini` وحده.
    """
    body = {"tests_v9/test_x.py": "import pytest\n\npytestmark = pytest.mark.smoke\n"}
    declared = _repo(tmp_path / "a", body, markers=("unit", "smoke"))
    absent = _repo(tmp_path / "b", body, markers=("unit",))
    assert _unmarked_in(monkeypatch, declared) == set(), "علامة مُعلَنة لم تُتَّبع"
    assert _unmarked_in(monkeypatch, absent) == {"tests_v9/test_x.py"}, (
        "اسم مُصلَّب لا يتبع pytest.ini"
    )


def test_the_guard_agrees_with_pytests_own_selection():
    """المُصدِّق: جواب الحارس الرخيص يُقارَن بجمع pytest الحقيقيّ تحت `-m`.

    بلا هذا يبقى «القراءة بالبنية» ادّعاءً. وهو ما أمسك خطأً حقيقيّاً أثناء بناء
    هذه الشريحة: إغفال مُزخرِفات الأصناف أعطى ١٩ بدل ١١.

    والعلاقة المُؤكَّدة دقيقة لا تقريبيّة: ما يستبعده pytest هو **بالضبط** اتّحاد ما
    يراه الحارس بلا علامة مع ما لا يجمع منه pytest شيئاً أصلاً (ملفّات ليست وحدات
    pytest، تتخطّى عند الاستيراد — صنف آخر لا يعالجه حارس العلامات). والصنفان
    يتقاطعان فعلاً، فصياغتي الأولى بالطرح كانت خاطئة وأسقطها هذا التأكيد.
    """
    markers = " or ".join(sorted(MOD.registered_markers()))

    def collected(*extra: str) -> set[str]:
        out = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                "tests_v9",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                *extra,
            ],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            check=False,
        ).stdout
        return {
            line.split("::")[0]
            for line in out.splitlines()
            if line.startswith("tests_v9/") and "::" in line
        }

    tracked = set(MOD.tracked_test_files())
    collectable = collected() & tracked

    # بيئة لا تجمع `tests_v9` تجعل المجموعتين فارغتين، فتصدُق العلاقة **فراغاً** ويمرّ
    # المُصدِّق بلا أن يقيس شيئاً — وهو الصنف الذي بُنيت هذه الشريحة كلّها ضدّه. وظيفة
    # `capability-governance` تُثبِّت pytest وحده، فالمُصدِّق يعمل في *Repository Tests*
    # حيث تُثبَّت `tests_v9/requirements-test.txt`. التخطّي مُعلَن، لا صامت.
    if len(collectable) < 500:
        pytest.skip(f"البيئة لا تجمع tests_v9 ({len(collectable)} ملفّاً فقط) — لا يُقاس هنا")

    selected = collected("-m", markers) & tracked
    deselected = tracked - selected
    guard_says = set(MOD.unmarked())

    assert guard_says <= deselected, (
        f"الحارس يعدّها بلا علامة بينما ينتقيها pytest: {sorted(guard_says - deselected)}"
    )
    uncollectable = tracked - collectable
    assert deselected == guard_says | uncollectable, (
        "ما يستبعده pytest ليس اتّحاد «بلا علامة» و«لا يجمع منه شيء»: "
        f"{sorted(deselected ^ (guard_says | uncollectable))}"
    )
