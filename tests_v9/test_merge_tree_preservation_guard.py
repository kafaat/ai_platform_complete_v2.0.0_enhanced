from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "merge_tree_preservation_guard", ROOT / "scripts/ci/merge_tree_preservation_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)


def _ev(*ids: str, pad: str = "") -> str:
    return "\n".join(f"### {item} — witness\nbody" for item in ids) + pad


def test_evidence_id_cannot_disappear_even_if_candidate_is_larger() -> None:
    base = _ev("E-2026-09-21-06", "E-2026-09-21-07")
    candidate = _ev("E-2026-09-21-06", pad="\n" + "padding\n" * 100)
    problems = guard.judge(base, candidate, "## GAP-ONE-01\n", "## GAP-ONE-01\n")
    assert "MISSING_EVIDENCE_IDS:E-2026-09-21-07" in problems
    assert not any(p.startswith("EVIDENCE_LOG_SHRANK") for p in problems)


def test_operational_evidence_log_may_not_shrink() -> None:
    problems = guard.judge(
        _ev("E-2026-09-21-06", pad="\nlong historical body"),
        _ev("E-2026-09-21-06"),
        "## GAP-ONE-01\n",
        "## GAP-ONE-01\n",
    )
    assert any(p.startswith("EVIDENCE_LOG_SHRANK") for p in problems)


def test_existing_gap_identity_cannot_disappear() -> None:
    problems = guard.judge(
        _ev("E-2026-09-21-06"),
        _ev("E-2026-09-21-06", pad="\nnew evidence"),
        "## GAP-ONE-01\n## GAP-TWO-02\n",
        "## GAP-ONE-01\n",
    )
    assert "MISSING_GAP_IDS:GAP-TWO-02" in problems


def test_gap_annotations_may_change_when_identity_survives() -> None:
    assert guard.judge(
        _ev("E-2026-09-21-06"),
        _ev("E-2026-09-21-06", pad="\nappend"),
        "## GAP-ONE-01\n- **الحالة:** open\n",
        "## GAP-ONE-01\n- **الحالة:** fixed — witness\n",
    ) == []


def test_new_evidence_and_gap_identities_are_legal() -> None:
    assert guard.judge(
        _ev("E-2026-09-21-06"),
        _ev("E-2026-09-21-06", "E-2026-09-22-01"),
        "## GAP-ONE-01\n",
        "## GAP-ONE-01\n## GAP-TWO-02\n",
    ) == []


def test_gap_parser_ignores_fenced_examples_but_reads_canonical_table_ids() -> None:
    text = """```md
## FAKE-GAP-01
```
| ID | status |
|---|---|
| REAL-GAP-01 | open |
"""
    assert guard.gap_identities(text) == {"REAL-GAP-01"}
