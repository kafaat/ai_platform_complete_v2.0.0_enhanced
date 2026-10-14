"""UNION-DUPLICATE-GUARD-RUNS-IN-A-NON-REQUIRED-CHECK-01.

`brain_duplicate_gap_identity_guard.py` هو الحارسُ الوحيد الذي يرى فجوةً واحدةً بحالتين
متناقضتين بعد دمج `merge=union` صامت. حارسٌ يحمرّ في وظيفةٍ غير مطلوبة لا يمنع الدمج،
فهذا الاختبار يُثبت أنّه يعمل في وظيفةٍ واحدةٍ على الأقلّ اسمُها في `required_contexts`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = "scripts/ci/brain_duplicate_gap_identity_guard.py"


def _required_contexts() -> set[str]:
    contract = ROOT / "docs" / "architecture" / "required_status_checks_contract.json"
    return set(json.loads(contract.read_text(encoding="utf-8"))["required_contexts"])


def _jobs_running(script: str) -> list[str]:
    names = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job_id, job in (doc.get("jobs") or {}).items():
            runs = " ".join(str(step.get("run", "")) for step in job.get("steps") or [])
            if script in runs:
                names.append(job.get("name", job_id))
    return names


def test_the_union_duplicate_guard_runs_in_a_required_check() -> None:
    jobs = _jobs_running(GUARD)
    assert jobs, f"{GUARD} لا يُشغّله أيّ workflow"
    required = sorted(set(jobs) & _required_contexts())
    assert required, f"{GUARD} يعمل في {jobs} وليس منها وظيفةٌ مطلوبة — يحمرّ ولا يمنع الدمج"
