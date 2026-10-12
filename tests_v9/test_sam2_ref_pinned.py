"""SAM2-REF-FLOATS-ON-MAIN-AND-WEIGHTS-UNVERIFIED-01 — ثوابتُ ساكنة رخيصة.

كان ``ARG SAM2_REF=main`` في ``services/sam2-inference/Dockerfile`` فرعاً عائماً: كلُّ بناءٍ
قد يجلب شيفرةً مختلفة من ``git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}``.
قرارُ المالك (2026-09-30): يُثبَّت على SHA التزامٍ كامل، ويُنبَّه إلى تقادمه بـworkflow
أسبوعيّ **غير حاجب**.

يقرأ الملفّات نصّاً فقط — لا شبكة ولا Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "services/sam2-inference/Dockerfile"
FRESHNESS = ROOT / ".github/workflows/sam2-ref-freshness.yml"

_ARG_RE = re.compile(r"(?m)^ARG\s+SAM2_REF=(\S*)\s*$")


def _sam2_ref_default() -> str:
    matches = _ARG_RE.findall(DOCKERFILE.read_text(encoding="utf-8"))
    assert len(matches) == 1, f"expected exactly one 'ARG SAM2_REF=' line, found {matches!r}"
    return matches[0]


def _freshness_triggers() -> dict:
    doc = yaml.safe_load(FRESHNESS.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare key ``on`` as boolean True.
    triggers = doc.get("on", doc.get(True))
    assert isinstance(triggers, dict), f"workflow triggers must be a mapping, got {triggers!r}"
    return triggers


def test_sam2_ref_default_is_a_full_commit_sha_not_a_branch() -> None:
    ref = _sam2_ref_default()
    assert re.fullmatch(r"[0-9a-f]{40}", ref), (
        f"SAM2_REF default must be a full 40-hex commit SHA, got {ref!r} "
        "(a branch or tag floats: every build may install different code)"
    )


def test_sam2_install_uses_the_pinned_ref() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}" in text


def test_freshness_workflow_exists_and_is_scheduled() -> None:
    assert FRESHNESS.is_file(), f"missing {FRESHNESS.relative_to(ROOT)}"
    triggers = _freshness_triggers()
    schedule = triggers.get("schedule")
    assert isinstance(schedule, list) and schedule and all("cron" in s for s in schedule)
    assert "workflow_dispatch" in triggers


def test_freshness_workflow_is_non_blocking() -> None:
    triggers = _freshness_triggers()
    for forbidden in ("pull_request", "pull_request_target", "push", "merge_group"):
        assert forbidden not in triggers, (
            f"sam2-ref-freshness must never gate merges; found trigger {forbidden!r}"
        )


def test_freshness_workflow_permissions_are_minimal() -> None:
    doc = yaml.safe_load(FRESHNESS.read_text(encoding="utf-8"))
    assert doc.get("permissions") == {"contents": "read"}
    for name, job in (doc.get("jobs") or {}).items():
        perms = job.get("permissions", {})
        assert set(perms) <= {"contents", "issues"}, f"job {name}: unexpected permissions {perms}"
        assert perms.get("contents", "read") == "read", f"job {name}: contents must stay read"
