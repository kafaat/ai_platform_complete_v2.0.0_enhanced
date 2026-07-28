"""ذكر معرّف فجوة في رسالة التزام ادّعاءٌ — والحارس يفرض صدقه.

`BRAIN-CLAIM-UNVERIFIED-01`: رسالة #683 أعلنت تسجيل أربع فجوات ووصلت اثنتان. لا شيء في
المستودع كان يتحقّق من ذلك، فالادّعاء مرّ. هذه الاختبارات تُثبت أنّ الحارس يلتقطه.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/ci/brain_commit_claim_guard.py"

pytestmark = pytest.mark.unit


def _run(base: str, head: str = "HEAD") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), "--base", base, "--head", head],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_guard_passes_on_the_current_branch():
    result = _run("origin/main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "brain commit claim guard: PASS" in result.stdout


def test_it_catches_the_real_historical_miss():
    """#683 أعلن أربع فجوات؛ اثنتان لم تصلا كعناوين أقسام.

    ليس مثالاً مصطنعاً — هذا الالتزام مدموج في main، وهو سبب وجود الحارس.
    """
    result = _run("4eded7a", "121ab09")
    assert result.returncode == 1, "الحارس لم يلتقط الفشل الذي وُجد لأجله"
    assert "UNIT-DORMANCY-WAKE-02" in result.stdout


def test_a_registered_id_is_accepted(tmp_path: Path):
    """وإلّا منع التوثيق بدل أن يفرضه: معرّف مسجَّل يجب أن يمرّ."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    known = mod.registry_ids()
    assert "IMAGERY-BLANK-THUMBNAIL-01" in known
    assert "BRAIN-CLAIM-UNVERIFIED-01" in known
    assert "CI-RLS-SUPERUSER-ROLE-01" not in known, "المعرّف المكرّر عاد"


def test_registry_ids_come_from_headings_not_prose():
    """ذكر معرّف داخل فقرة لا يُنشئ فجوة — العنوان وحده يفعل."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    registry = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    for gid in mod.registry_ids():
        assert any(line.startswith("## ") and gid in line for line in registry.splitlines()), (
            f"{gid} لم يأتِ من عنوان قسم"
        )
