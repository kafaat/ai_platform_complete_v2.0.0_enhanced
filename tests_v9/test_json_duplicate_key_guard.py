"""``MUT-REGISTRY-DUPLICATE-KEY-SHADOWS-A-BLOCK-01`` — شواهد الحارس.

الخاصّيّة المحروسة ليست «الوثيقة تُحلَّل» بل «ما يُحمَّل هو ما كُتِب». ومفتاحٌ مكرَّر
يكسر الثانية بينما يُرضي الأولى تماماً.

**ولا اختبارَ مشروطاً بوجود SHA في التاريخ هنا عمداً.** العطلُ الأصليّ عاش على
``a1f5da7f``، ويغري ذلك باختبارٍ يقرأ ذلك الالتزام — لكنّ استنساخ CI بعمق ١ لا يبلغه،
فيتحوّل ``skipif`` إلى صمتٍ لا تكذيب، ويُصنّفه ``guard_mutation_guard`` عندئذٍ
``STABLE_WRONG_TEST``. فشكلُ العطل مُثبَّتٌ هنا حرفيّاً بدل الإشارة إليه.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/json_duplicate_key_guard.py"

pytestmark = pytest.mark.unit


def _load():
    spec = importlib.util.spec_from_file_location("_json_duplicate_key_guard", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """مستودعٌ مؤقّتٌ حقيقيّ — الجردُ يأتي من git، فلا يُحاكى."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=60)
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, timeout=60)
    return tmp_path


# ── ١) شكلُ العطل الحقيقيّ، مُثبَّتاً لا مُشاراً إليه ────────────────────────


def test_a_duplicate_inside_behavioural_is_detected():
    """الحادثةُ الأصليّة بعينها: كتلتان لملفٍّ واحد تحت ``behavioural``."""
    text = """{
      "behavioural": {
        ".github/workflows/ci.yml": {"mutations": [{"expect": "first"}]},
        "docs/architecture/rag_authority_convergence.json": {"mutations": []},
        ".github/workflows/ci.yml": {"mutations": [{"expect": "second"}]}
      }
    }"""
    found = guard.duplicate_keys(text)
    assert found == [("$.behavioural", ".github/workflows/ci.yml", 2)]


def test_the_last_value_really_does_shadow_the_first():
    """الخاصّيّةُ المحروسة سلوكيّة: المُحمَّل يخالف المكتوب، والوثيقةُ صحيحةٌ نحويّاً."""
    text = """{
      "behavioural": {
        "a.py": {"mutations": ["kept-nothing"]},
        "a.py": {"mutations": []}
      }
    }"""
    loaded = json.loads(text)
    # المحلّلُ الافتراضيّ يقبلها، ويطرح الكتلةَ الأولى بلا كلمة.
    assert loaded["behavioural"]["a.py"] == {"mutations": []}
    assert len(loaded["behavioural"]) == 1
    # وهذا بالضبط ما يراه الحارس ولا يراه أيُّ مستهلك.
    assert guard.duplicate_keys(text) == [("$.behavioural", "a.py", 2)]


def test_a_duplicate_at_the_document_root_is_detected():
    assert guard.duplicate_keys('{"schema": "v1", "schema": "v2"}') == [("$", "schema", 2)]


def test_a_duplicate_nested_inside_a_list_is_detected():
    """المشيُ يعبر القوائم — تكرارٌ داخل عنصرِ مصفوفةٍ تكرارٌ أيضاً."""
    text = '{"mutations": [{"ok": 1}, {"expect": "a", "expect": "b"}]}'
    assert guard.duplicate_keys(text) == [("$.mutations[1]", "expect", 2)]


def test_the_repeat_count_is_reported_not_just_the_fact():
    text = '{"k": 1, "k": 2, "k": 3}'
    assert guard.duplicate_keys(text) == [("$", "k", 3)]


def test_every_duplicate_is_reported_not_only_the_first():
    text = '{"a": 1, "a": 2, "b": 3, "b": 4}'
    assert guard.duplicate_keys(text) == [("$", "a", 2), ("$", "b", 2)]


# ── ٢) الكشفُ عند المحلّل، لا بمسحٍ معجميّ ─────────────────────────────────


def test_a_key_shaped_string_value_is_not_a_duplicate():
    """التكذيبُ الحاسم لتصميمٍ بديل.

    مسحٌ نصّيٌّ خام يرى ``"dup": 1`` داخل **قيمةٍ نصّيّة** مفتاحاً فيُدين وثيقةً
    سليمة. والكشفُ عند ``object_pairs_hook`` يرى ما رآه المحلّل وحده، فلا يقع فيها.
    """
    text = json.dumps({"note": '{"dup": 1, "dup": 2}', "dup": 7}, ensure_ascii=False)
    assert guard.duplicate_keys(text) == []
    # وأنّ الفخّ حاضرٌ فعلاً في النصّ — وإلّا كان الاختبار يحرس لا شيء.
    assert text.count('\\"dup\\"') == 2


def test_a_key_repeated_across_sibling_objects_is_not_a_duplicate():
    """نفسُ المفتاح في كائنين مختلفين شرعيٌّ تماماً — لا يُدان."""
    assert guard.duplicate_keys('{"a": {"k": 1}, "b": {"k": 2}}') == []


def test_a_clean_document_yields_nothing():
    assert guard.duplicate_keys('{"a": 1, "b": {"c": [1, 2, {"d": 3}]}}') == []


# ── ٣) يفشل مغلقاً ─────────────────────────────────────────────────────────


def test_invalid_json_fails_closed_with_a_named_reason(tmp_path):
    root = _repo(tmp_path, {"broken.json": "{not json"})
    problems, scanned = guard.findings(root)
    assert scanned == 1
    assert any("JSON غير صالح" in p for p in problems)


def test_a_tracked_file_missing_from_disk_fails_closed(tmp_path):
    root = _repo(tmp_path, {"gone.json": "{}"})
    (root / "gone.json").unlink()
    problems, _ = guard.findings(root)
    assert any("متعقَّبٌ ولا يُقرَأ" in p for p in problems)


def test_scanning_nothing_is_a_failure_not_a_pass(tmp_path):
    """«لم يُنظَر» ≠ «سليم» — حارسٌ مسح صفراً لا يُعلِن نجاحاً."""
    root = _repo(tmp_path, {"readme.md": "no json here"})
    problems, scanned = guard.findings(root)
    assert scanned == 0
    assert problems == ["لم يُمسَح أيُّ ملفّ JSON — «لم يُنظَر» ليس «سليم»"]


def test_an_unusable_inventory_source_fails_closed(tmp_path):
    """جردٌ متعذّر (لا مستودع git) يُبلَّغ سبباً، ولا يُقرَأ شجرةً نظيفة."""
    problems, scanned = guard.findings(tmp_path)
    assert scanned == 0
    assert any("تعذّر جردُ ملفّات JSON" in p for p in problems)


# ── ٤) العقدُ الحيّ على الشجرة الحاضرة ──────────────────────────────────────


def test_the_repository_tree_carries_no_duplicate_key():
    problems, scanned = guard.findings(ROOT)
    assert problems == [], problems
    assert scanned > 200, f"الجردُ انكمش إلى {scanned} — قِسْ قبل أن تُصدِّق الخضرة"


def test_the_mutation_registry_is_the_document_this_guard_was_built_for(tmp_path):
    """العطلُ وُجِد في سجلّ الطفرات، فيُثبَّت أنّه داخل نطاق المسح فعلاً."""
    files = guard.tracked_json_files(ROOT)
    assert ROOT / "docs/architecture/guard_mutation_registry.json" in files


def test_the_guard_exits_nonzero_when_it_finds_a_duplicate(tmp_path):
    """رمزُ الخروج هو ما تقرؤه CI — لا قيمةُ الإرجاع الداخليّة."""
    root = _repo(tmp_path, {"dup.json": '{"a": 1, "a": 2}'})
    assert guard.main(["--root", str(root)]) == 1


def test_the_guard_exits_zero_on_a_clean_tree(tmp_path):
    root = _repo(tmp_path, {"ok.json": '{"a": 1}'})
    assert guard.main(["--root", str(root)]) == 0
