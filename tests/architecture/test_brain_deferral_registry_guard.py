"""الحارس الذي يحوّل قاعدة «لا فجوة بلا مصدر + حالة» من عُرف إلى إنفاذ.

`BRAIN-DEFERRAL-LEAK-01`: تُرك `hot.md` يمتصّ التأجيلات بلا ما يجبرها على الهجرة إلى
`gaps/registry.md`، فبقي بندان يتيمَين شهوراً. هذه الاختبارات تُثبت أنّ الحارس يلتقط
التسرّب فعلاً، لا أنّه يمرّ فقط على الشجرة الحاليّة.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/ci/brain_deferral_registry_guard.py"
HOT = ROOT / "sahool-brain" / "hot.md"

pytestmark = pytest.mark.unit


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GUARD)], capture_output=True, text=True, cwd=ROOT)


@pytest.fixture
def restore_hot():
    saved = HOT.read_text(encoding="utf-8")
    yield
    HOT.write_text(saved, encoding="utf-8")


def test_guard_passes_on_the_current_tree():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "brain deferral registry guard: PASS" in result.stdout


def test_a_new_deferral_without_a_gap_id_fails(restore_hot):
    """الانحدار الذي وُجد الحارس لأجله."""
    HOT.write_text(
        HOT.read_text(encoding="utf-8") + "\n> **مؤجَّل:** بند مستقل بلا معرّف.\n",
        encoding="utf-8",
    )
    result = _run()
    assert result.returncode == 1
    assert "تأجيل بلا معرّف مسجَّل" in result.stdout


def test_a_deferral_citing_an_unregistered_id_fails(restore_hot):
    """الادّعاء المعاكس: معرّف يبدو صحيحاً وليس في السجلّ."""
    HOT.write_text(
        HOT.read_text(encoding="utf-8") + "\n> **مؤجَّل:** انظر FAKE-GAP-ID-99.\n",
        encoding="utf-8",
    )
    assert _run().returncode == 1


def test_a_deferral_citing_a_registered_id_passes(restore_hot):
    """وإلّا كان الحارس يمنع التوثيق بدل أن يفرضه."""
    HOT.write_text(
        HOT.read_text(encoding="utf-8") + "\n> **مؤجَّل:** انظر IMAGERY-BLANK-THUMBNAIL-01.\n",
        encoding="utf-8",
    )
    assert _run().returncode == 0


def test_the_baseline_shrinks_and_never_grows():
    """الأساس امتياز مؤقّت لا رخصة دائمة: كلّ سطر يُحذف عند تسجيل فجوته."""
    import json

    baseline = json.loads(
        (ROOT / "docs/architecture/brain_deferral_baseline.json").read_text(encoding="utf-8")
    )
    assert baseline["gap"] == "BRAIN-DEFERRAL-LEAK-01"
    assert len(baseline["exempt_lines"]) <= 17, "الأساس نما — أُضيف تأجيل قديم بدل تسجيل فجوته"


def test_the_three_orphans_are_now_registered():
    """البنود التي كشفها التسرّب: لا يُقبل إغلاق الفجوة وهي غير مسجَّلة."""
    registry = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    headings = [ln for ln in registry.splitlines() if ln.startswith("## ")]
    for gap in (
        "IMAGERY-BLANK-THUMBNAIL-01",
        "UNIT-TEST-DORMANCY-01",
        "APP-ROUTES-EMPTY-01",
        "FIELD-STATE-PRODUCERS-MISSING-01",
    ):
        assert any(gap in h for h in headings), f"{gap} ليست عنوان قسم في السجلّ"
    assert "CI-RLS-SUPERUSER-ROLE-01" not in registry, (
        "معرّف مكرّر لـAUTH-E2E-UNDER-RESTRICTED-ROLE عاد إلى السجلّ"
    )
