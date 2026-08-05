"""An append-only journal may not shrink — proven on the incident that created this guard.

``BRAIN-APPEND-ONLY-TRUNCATION-GUARD-01``. ``sahool-brain/log.md`` went from 1,383,368
bytes to zero in ``cb6598fe`` and sat empty on ``main`` for about five hours with every
gate green. A guard that cannot fail on its own incident guards nothing, so the first
test below runs against those two real commits.

The two properties that matter, and both were measured before being chosen:

* **Shrink blocks, prefix loss only reports.** Over 202 commit-parent pairs in this
  repository, "must not shrink" fired once — on the incident. A byte-prefix rule would
  have fired 141 times, because ``registry.md`` carries status edits that CLAUDE.md
  mandates and ``hot.md`` is a snapshot rewritten by design. A guard that fires on normal
  work teaches its reader to bypass it.
* **Every parent, not a base.** The truncation survived because one parent held the file
  and the other did not. Comparing a merge against *a* base passes; comparing against
  *each* parent catches it.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/brain_append_only_guard.py"
RESOLVER = ROOT / "scripts/ci/resolve_merge_conflicts.py"

# The incident, by SHA. Both are on main's history and are not going away.
BEFORE_TRUNCATION = "32efdc90"
TRUNCATION = "cb6598fe"
REPAIR = "ddf8716f"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load(GUARD, "_brain_append_only_guard")


def _have(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


# ── the incident ───────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not _have(TRUNCATION), reason="shallow clone: the incident commits are not present"
)
def test_the_guard_fails_on_the_truncation_that_created_it(guard):
    blocking, _, pairs = guard.check_range(BEFORE_TRUNCATION, TRUNCATION)
    assert pairs, "no commit-parent pair examined — the check would be vacuous"
    codes = {f.code for f in blocking}
    assert "JOURNAL_SHRANK" in codes, f"the incident must block; got {codes}"
    hit = next(f for f in blocking if f.code == "JOURNAL_SHRANK")
    assert hit.path == "sahool-brain/log.md"
    assert "1,383,368" in hit.detail, hit.detail


@pytest.mark.skipif(not _have(REPAIR), reason="shallow clone: the repair commit is absent")
def test_the_guard_passes_on_the_commit_that_repaired_it(guard):
    """Without this, every assertion above also holds for a guard that always fails."""
    blocking, _, pairs = guard.check_range(TRUNCATION, REPAIR)
    assert pairs
    assert not blocking, "\n".join(str(f) for f in blocking)


# ── merge awareness, on a synthetic merge that reproduces the shape ────────


def _merge_repo(tmp_path: Path, *, take_empty_side: bool) -> Path:
    """A repo whose merge has one parent holding the journal and one that emptied it."""
    root = tmp_path / "probe"
    (root / "sahool-brain").mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    journal = root / "sahool-brain/log.md"
    git("init", "-q", "-b", "main", ".")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    journal.write_text("line 1\nline 2\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")

    git("checkout", "-qb", "branch")
    with journal.open("a", encoding="utf-8") as handle:
        handle.write("line 3 appended by the branch\n")
    git("add", "-A")
    git("commit", "-qm", "branch appends")

    git("checkout", "-q", "main")
    journal.write_text(
        "" if take_empty_side else "line 1\nline 2\nmain also appends\n",
        encoding="utf-8",
    )
    git("add", "-A")
    git("commit", "-qm", "main writes")

    subprocess.run(["git", "merge", "branch", "--no-edit", "-q"], cwd=root, capture_output=True)
    if take_empty_side:
        journal.write_text("", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "merge resolved to the empty side", "--no-verify")
    return root


def test_a_merge_that_takes_the_empty_side_is_caught(guard, tmp_path):
    """The incident's exact shape: legal against one parent, a loss against the other."""
    root = _merge_repo(tmp_path, take_empty_side=True)
    blocking, _, pairs = guard.check_range(None, "HEAD", files=("sahool-brain/log.md",), root=root)
    assert pairs >= 1
    assert [f.code for f in blocking] == ["JOURNAL_SHRANK"], (
        "a merge resolved to the empty side must block"
    )


def test_a_merge_that_keeps_both_sides_passes(guard, tmp_path):
    root = _merge_repo(tmp_path, take_empty_side=False)
    blocking, _, _ = guard.check_range(None, "HEAD", files=("sahool-brain/log.md",), root=root)
    assert not blocking, "\n".join(str(f) for f in blocking)


def test_both_parents_are_examined_not_just_one(guard, tmp_path):
    """Checking a single base is what let the real truncation through."""
    root = _merge_repo(tmp_path, take_empty_side=True)
    _, _, pairs = guard.check_range(None, "HEAD", files=("sahool-brain/log.md",), root=root)
    assert pairs == 2, f"a merge commit has two parents; examined {pairs}"


# ── fail closed ────────────────────────────────────────────────────────────


def test_an_unresolvable_ref_fails_closed_rather_than_reporting_an_empty_range():
    """ "Nothing to compare against" must never be a pass — the whole gap is a silent zero."""
    result = subprocess.run(
        [sys.executable, str(GUARD), "--base", "no/such/ref"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no/such/ref" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_deleted_journal_blocks(guard, tmp_path):
    root = tmp_path / "del"
    (root / "sahool-brain").mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    journal = root / "sahool-brain/log.md"
    git("init", "-q", "-b", "main", ".")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    journal.write_text("a\nb\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    journal.unlink()
    git("add", "-A")
    git("commit", "-qm", "delete the journal")

    codes = {
        f.code
        for f in guard.check_range(None, "HEAD", files=("sahool-brain/log.md",), root=root)[0]
    }
    # A deletion trips both signals, and that is correct: the journal vanished between the
    # parent and the child (JOURNAL_DELETED) and it is not present at the head
    # (JOURNAL_ABSENT_AT_HEAD). Either alone is enough to block.
    assert "JOURNAL_DELETED" in codes
    assert codes <= {"JOURNAL_DELETED", "JOURNAL_ABSENT_AT_HEAD"}, codes


# ── the classification is imported, never restated ────────────────────────


def test_the_file_list_comes_from_the_existing_classifier(guard):
    """A second list is a second thing to keep in step; this repository has measured that."""
    resolver = _load(RESOLVER, "_resolve_probe")
    assert guard.append_only_files() == tuple(resolver.APPEND_ONLY)
    source = GUARD.read_text(encoding="utf-8")
    for path in resolver.APPEND_ONLY:
        assert f'"{path}"' not in source, (
            f"{path} is hardcoded in the guard; it must come from resolve_merge_conflicts"
        )


def test_prefix_loss_is_advisory_because_it_was_measured_to_be_normal(guard):
    """Blocking on prefix loss would have fired on 141 of 202 historical pairs.

    ``registry.md`` carries status edits that CLAUDE.md requires, and ``hot.md`` is a
    snapshot. Both legitimately rewrite earlier bytes while growing.
    """
    source = GUARD.read_text(encoding="utf-8")
    assert "PREFIX_NOT_PRESERVED" in source
    # The advisory code must not appear in the blocking list construction.
    blocking_section = source.split("def check_range", 1)[1]
    advisory_index = blocking_section.index("PREFIX_NOT_PRESERVED")
    assert "advisory.append" in blocking_section[advisory_index - 400 : advisory_index], (
        "prefix loss must be reported, not blocked"
    )


def test_the_guard_is_wired_into_the_workflow_that_runs_the_other_brain_guards():
    """A guard on disk that no job runs is the shape of the gap it was built to close."""
    workflow = (ROOT / ".github/workflows/no-report-only-change.yml").read_text(encoding="utf-8")
    runs = [line for line in workflow.splitlines() if line.strip().startswith("run:")]
    assert any("brain_append_only_guard.py" in line for line in runs), (
        "the guard must be invoked by a run: step, not merely mentioned"
    )


def test_a_missing_journal_at_head_blocks_even_with_nothing_to_compare(guard, tmp_path):
    """The guard's own silent zero, caught in the guard.

    Every pair is skipped when the journal is absent at the parent, so a tree that no
    longer has the journals would examine **zero pairs** and print ok. That is the same
    shape as the incident: nothing to compare read as nothing wrong. Found by running the
    guard on an empty range and noticing it reported ok on zero pairs.
    """
    root = tmp_path / "absent"
    root.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q", "-b", "main", ".")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (root / "unrelated.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "no journals here at all")

    blocking, _, pairs = guard.check_range(None, "HEAD", files=("sahool-brain/log.md",), root=root)
    assert pairs == 0, "the premise of this test is that no pair is comparable"
    assert [f.code for f in blocking] == ["JOURNAL_ABSENT_AT_HEAD"], (
        "zero comparable pairs must not read as a pass"
    )
