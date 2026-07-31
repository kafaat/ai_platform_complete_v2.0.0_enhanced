"""حارس «الخضرة الزائفة» — TESTS-PASS-WITHOUT-ASSERTING-01.

دالّة ``test_*`` بلا تأكيد **وتُرجِع قيمة** لا يمكن أن تفشل: pytest يُهمِل القيمة
الراجعة ويكتفي بتحذير. قياس مباشر: ``tests_v9/test_roadmap_phase23.py`` يجمع ١٤٣
اختباراً، **واحد** فقط يحوي ``assert``؛ وتشغيل دوالّه وقراءة حمولاتها كشف علامتَي
``✗`` حقيقيّتين تحت خضرة تامّة. الحارس يُجمّد المجموعة الحاليّة ويمنع نموّها.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import assertion_presence_guard as guard  # noqa: E402

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "architecture" / "assertion_presence_baseline.json"


def _run_check() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/ci/assertion_presence_guard.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_baseline_matches_the_tree():
    """الأساس المُلتزَم يطابق المقيس — وإلّا فهو يصف شجرة أخرى."""
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert sorted(frozen["entries"]) == guard.collect()
    assert frozen["count"] == len(frozen["entries"])
    assert _run_check().returncode == 0


def test_detector_matches_the_pattern_and_not_valid_tests():
    """القاعدة قاطعة: بلا assert/raises **و** تُرجِع قيمة. غيرها لا يُرصَد."""
    import ast

    def _hit(src: str) -> bool:
        node = ast.parse(src).body[0]
        return guard._is_assertionless_returning_test(node)

    assert _hit("def test_bad():\n    return [('✗', 'boom')]\n")
    # تأكيد حقيقيّ ⇒ لا يُرصَد ولو أرجع قيمة.
    assert not _hit("def test_ok():\n    assert 1 == 1\n    return []\n")
    # pytest.raises تأكيد صحيح.
    assert not _hit(
        "def test_raises():\n    with pytest.raises(ValueError):\n        f()\n    return []\n"
    )
    # بلا تأكيد لكن بلا إرجاع ⇒ اختبار دخان مشروع، خارج النطاق عمداً.
    assert not _hit("def test_smoke():\n    build_app()\n")
    # ليست دالّة اختبار.
    assert not _hit("def helper():\n    return [1]\n")


def test_new_assertionless_test_is_rejected():
    """النموّ مرفوض: إدخال جديد يُسقِط CI بالاسم.

    مُكذَّب بالبناء: نُسقِط إدخالاً من الأساس (محاكاة دالّة حيّة غير مُجمَّدة)،
    ونؤكّد أنّ الفحص يفشل مسمّياً إيّاها، ثمّ نستعيد."""
    original = BASELINE.read_text(encoding="utf-8")
    data = json.loads(original)
    dropped = data["entries"][0]
    try:
        data["entries"] = [e for e in data["entries"] if e != dropped]
        data["count"] = len(data["entries"])
        BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = _run_check()
        assert result.returncode != 0, "إدخال خارج المجموعة المُجمَّدة يجب أن يُسقِط الفحص"
        assert dropped in result.stdout + result.stderr, "الفشل يجب أن يسمّي الدالّة"
    finally:
        BASELINE.write_text(original, encoding="utf-8")
    assert _run_check().returncode == 0, "الاستعادة يجب أن تُعيد الفحص أخضر"


def test_the_measured_example_is_still_recorded():
    """المثال الذي كشف العلّة يبقى موثَّقاً حتى يُصلَح (لا يختفي بصمت)."""
    frozen = set(json.loads(BASELINE.read_text(encoding="utf-8"))["entries"])
    phase23 = {e for e in frozen if e.startswith("tests_v9/test_roadmap_phase23.py::")}
    assert len(phase23) >= 140, (
        f"عدد دوالّ phase23 المرصودة انخفض إلى {len(phase23)} — إن أُصلِحت فحدّث الأساس"
    )
