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
    # النطاقُ محصورٌ في الدفتر الذي وقعت عليه الحادثة: مدًى تاريخيٌّ من 2026-08 يسبق
    # إنشاءَ دفاترَ أُضيفت لاحقاً إلى القائمة، فيُبلِغ عنها `JOURNAL_ABSENT_AT_HEAD`
    # بحقّ — وهي مفارقةٌ زمنيّة لا انحدار. الحصرُ يُبقي الشاهدَ على سؤاله بعينه.
    blocking, _, pairs = guard.check_range(
        BEFORE_TRUNCATION, TRUNCATION, files=("sahool-brain/log.md",)
    )
    assert pairs, "no commit-parent pair examined — the check would be vacuous"
    codes = {f.code for f in blocking}
    assert "JOURNAL_SHRANK" in codes, f"the incident must block; got {codes}"
    hit = next(f for f in blocking if f.code == "JOURNAL_SHRANK")
    assert hit.path == "sahool-brain/log.md"
    assert "1,383,368" in hit.detail, hit.detail


@pytest.mark.skipif(not _have(REPAIR), reason="shallow clone: the repair commit is absent")
def test_the_guard_passes_on_the_commit_that_repaired_it(guard):
    """Without this, every assertion above also holds for a guard that always fails."""
    blocking, _, pairs = guard.check_range(TRUNCATION, REPAIR, files=("sahool-brain/log.md",))
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


def test_omitting_base_is_a_usage_error_not_a_green_measurement():
    """GUARD-RUN-WITHOUT-THE-ARGUMENTS-CI-PASSES-01: no range means no measurement.

    Before ``--base`` became mandatory the guard run bare compared HEAD with itself and
    printed ``_ok`` — green about a question never asked, while CI walked every
    parent pair. The omission must be an argparse usage error (exit 2, naming the flag),
    never a zero-pair success. Registered as a mutation so that dropping
    ``required=True`` turns this test red (Copilot on #1000).
    """
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--base" in result.stderr
    assert "Traceback" not in result.stderr
    assert "ok" not in result.stdout.lower()


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


def test_no_registered_mutation_names_a_test_that_can_be_skipped():
    """A mutation whose named test skips is silence, not falsification.

    Measured on #792: mutation [1] named
    ``test_the_guard_fails_on_the_truncation_that_created_it``, which is gated on the
    incident SHAs being present. CI checks out at depth 1, so that test **skipped**, and
    ``guard_mutation_guard`` correctly reported ``STABLE_WRONG_TEST`` — the defect was
    caught, but by a different test than the one registered. A registered falsification
    that cannot run where it matters proves nothing there.

    The history-anchored test stays: on a full clone it is the strongest evidence there
    is, and it declares its own skip reason rather than passing vacuously. What changes
    is which test the registry points at.

    Parsed with ``ast`` rather than by reading lines — the first version of this check was
    a line scanner and did not survive its own quoting.
    """
    import ast
    import json

    registry = json.loads(
        (ROOT / "docs/architecture/guard_mutation_registry.json").read_text(encoding="utf-8")
    )
    spec = registry["mutated"]["brain_append_only_guard.py"]
    tree = ast.parse((ROOT / spec["test"]).read_text(encoding="utf-8"))

    skippable = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any("skipif" in ast.unparse(decorator) for decorator in node.decorator_list)
    }
    assert skippable, "no skippable test in this file — the check would be vacuous"

    named = {mutation["expect"] for mutation in spec["mutations"]}
    assert not (named & skippable), (
        "these mutations name tests that can skip, so they falsify nothing where the skip "
        f"fires: {sorted(named & skippable)}"
    )

    # And every named test must exist, or the mutation names nothing at all.
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert named <= defined, f"mutations name absent tests: {sorted(named - defined)}"


# APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01: synthetic Git histories, no skips.
_REGISTRY = "sahool-brain/gaps/registry.md"
_HEADER = "# Registry\n\n| ID | state | evidence |\n| --- | --- | --- |\n"
_ROW_A = "| GAP-A | open | retained evidence A |\n"
_ROW_B = "| GAP-B | open | retained evidence B |\n"


def _dedup_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, encoding="utf-8"
    )
    return result.stdout.strip()


def _dedup_repo(tmp_path: Path, before: bytes, path: str = _REGISTRY) -> Path:
    root = tmp_path / "dedup-probe"
    target = root / path
    target.parent.mkdir(parents=True)
    _dedup_git(root, "init", "-q", "-b", "main", ".")
    _dedup_git(root, "config", "user.email", "guard-test@example.invalid")
    _dedup_git(root, "config", "user.name", "Guard Test")
    _dedup_git(root, "config", "commit.gpgsign", "false")
    target.write_bytes(before)
    _dedup_git(root, "add", "-A")
    _dedup_git(root, "commit", "-qm", "synthetic parent")
    return root


def _dedup_candidate(root: Path, after: bytes, path: str, *parents: str) -> str:
    """A candidate commit object, never moving HEAD to pretend it was the tested ref."""
    (root / path).write_bytes(after)
    _dedup_git(root, "add", path)
    tree = _dedup_git(root, "write-tree")
    parent_args = [item for parent in parents for item in ("-p", parent)]
    return _dedup_git(root, "commit-tree", tree, *parent_args, "-m", "candidate under test")


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("identity", ["GAP-A", "WAIVER-WX10.6-001"])
def test_lossless_row_deduplication_satisfies_both_real_guards(
    guard, tmp_path, monkeypatch, newline, identity
):
    row = _ROW_A.replace("GAP-A", identity)
    retained = _HEADER + row + _ROW_B + "\nOriginal prose remains.\n"
    before = (retained + row + row).replace("\n", newline).encode("utf-8")
    after = (retained + "\nRepair recorded.\n").replace("\n", newline).encode("utf-8")
    assert len(after) < len(before), "the old size guard must actually reject this edit"
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    duplicate = _load(
        ROOT / "scripts/ci/brain_duplicate_gap_identity_guard.py", "_duplicate_coexistence"
    )
    monkeypatch.setattr(duplicate, "ROOT", root)
    assert duplicate.check([root / _REGISTRY]), "the parent's duplicate must be detected"
    candidate = _dedup_candidate(root, after, _REGISTRY, parent)
    assert _dedup_git(root, "rev-parse", "HEAD") == parent
    assert candidate != parent, "a stale HEAD is not evidence for the candidate"
    assert guard.blob(candidate, _REGISTRY, root=root) == after
    blocking, advisory, pairs = guard.check_range(parent, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 1
    assert not blocking, "\n".join(str(f) for f in blocking)
    assert [f.code for f in advisory] == ["DUPLICATE_ROWS_DEDUPLICATED"]
    assert not duplicate.check([root / _REGISTRY]), "the SAME candidate must satisfy both guards"


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_lossless_row_deduplication_preserves_fenced_examples(guard, tmp_path, fence):
    examples = fence + "text\n" + _ROW_A + _ROW_A + fence + "\n"
    retained = (_HEADER + _ROW_A + examples + _ROW_B + "\nKeep this prose.\n").encode()
    before = retained + _ROW_A.encode()
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    candidate = _dedup_candidate(root, retained, _REGISTRY, parent)
    blocking, _, pairs = guard.check_range(parent, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 1 and not blocking
    assert guard.blob(candidate, _REGISTRY, root=root) == retained


@pytest.mark.parametrize(
    "before,after",
    [
        pytest.param(
            _HEADER + _ROW_A + _ROW_B + _ROW_A,
            _HEADER + _ROW_A,
            id="unique-row-deletion",
        ),
        pytest.param(
            _HEADER + _ROW_A + _ROW_A.replace("open", "closed"),
            _HEADER + _ROW_A,
            id="same-id-different-state",
        ),
        pytest.param(
            _HEADER + _ROW_A + _ROW_A.replace("evidence A", "evidence B"),
            _HEADER + _ROW_A,
            id="same-id-different-evidence",
        ),
        pytest.param(
            _HEADER + _ROW_A + _ROW_A.replace("| open |", "|  open |"),
            _HEADER + _ROW_A,
            id="same-id-different-whitespace",
        ),
        pytest.param(
            _HEADER + _ROW_A + "Keep original prose.\n" + _ROW_A,
            _HEADER + _ROW_A,
            id="non-row-prose-deletion",
        ),
        pytest.param(
            _HEADER + _ROW_A + _ROW_B + _ROW_A * 2,
            _HEADER + _ROW_A + "replacement filler\n",
            id="padding-does-not-fund-a-unique-row-deletion",
        ),
        pytest.param(
            _HEADER + _ROW_A * 2,
            _HEADER + _ROW_A.replace("open", "closed"),
            id="status-edit-is-not-deduplication",
        ),
        pytest.param(
            _HEADER + _ROW_A + _ROW_B + _ROW_A,
            _HEADER + _ROW_B + _ROW_A,
            id="reordered-retained-rows",
        ),
        pytest.param(_HEADER + _ROW_A * 2, _HEADER, id="all-copies-deleted"),
        pytest.param(
            _HEADER + _ROW_A * 3,
            _HEADER + _ROW_A * 2,
            id="remaining-or-reintroduced-duplicate",
        ),
        pytest.param(
            _HEADER + _ROW_A * 3,
            _HEADER + _ROW_A + _ROW_A.replace("open", "closed"),
            id="conflicting-duplicate-in-appended-suffix",
        ),
        pytest.param(
            _HEADER + "```text\n" + _ROW_A * 2 + "```\n",
            _HEADER + "```text\n" + _ROW_A + "```\n",
            id="fenced-example-not-an-active-duplicate",
        ),
        pytest.param(
            _HEADER
            + _ROW_A.replace("GAP-A", "WAIVER-WX10.6-001")
            + _ROW_A.replace("GAP-A", "WAIVER-WX10.7-001"),
            _HEADER + _ROW_A.replace("GAP-A", "WAIVER-WX10.6-001"),
            id="dotted-identities-are-distinct",
        ),
        pytest.param(
            _HEADER + "## GAP-A\nHistorical evidence.\n" * 2,
            _HEADER + "## GAP-A\nHistorical evidence.\n",
            id="historical-headings-are-not-table-rows",
        ),
        pytest.param(
            _HEADER + _ROW_A * 2 + "unterminated prose",
            _HEADER + _ROW_A + "unterminated prose altered",
            id="append-must-not-rewrite-unterminated-final-line",
        ),
        pytest.param(
            (_HEADER + _ROW_A * 2).encode() + b"\xff\n",
            (_HEADER + _ROW_A).encode() + b"\xff\n",
            id="invalid-utf8-fails-closed",
        ),
    ],
)
def test_lossless_row_deduplication_rejects_information_loss(guard, tmp_path, before, after):
    before = before.encode("utf-8") if isinstance(before, str) else before
    after = after.encode("utf-8") if isinstance(after, str) else after
    assert len(after) < len(before), "negative case must enter the shrink branch"
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    candidate = _dedup_candidate(root, after, _REGISTRY, parent)
    blocking, _, pairs = guard.check_range(parent, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 1
    assert [f.code for f in blocking] == ["JOURNAL_SHRANK"]


@pytest.mark.parametrize(
    "path",
    [
        "sahool-brain/log.md",
        "sahool-brain/hot.md",
        "sahool-brain/decisions/ledger.md",
        "other/gaps/registry.md",
    ],
)
def test_lossless_row_deduplication_does_not_exempt_other_files(guard, tmp_path, path):
    root = _dedup_repo(tmp_path, (_HEADER + _ROW_A * 2).encode(), path)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    candidate = _dedup_candidate(root, (_HEADER + _ROW_A).encode(), path, parent)
    blocking, _, pairs = guard.check_range(parent, candidate, files=(path,), root=root)
    assert pairs == 1
    assert [f.code for f in blocking] == ["JOURNAL_SHRANK"]


@pytest.mark.parametrize("lose_second_parent", [False, True])
def test_lossless_row_deduplication_checks_every_merge_parent(guard, tmp_path, lose_second_parent):
    root = _dedup_repo(tmp_path, (_HEADER + _ROW_A + _ROW_B).encode())
    ancestor = _dedup_git(root, "rev-parse", "HEAD")
    left_content = (_HEADER + _ROW_A * 3 + _ROW_B).encode()
    left = _dedup_candidate(root, left_content, _REGISTRY, ancestor)
    right_row = _ROW_B.replace("GAP-B", "GAP-C") if lose_second_parent else _ROW_B
    right_content = (_HEADER + _ROW_A * 2 + right_row).encode()
    right = _dedup_candidate(root, right_content, _REGISTRY, ancestor)
    after = (_HEADER + _ROW_A + _ROW_B).encode()
    candidate = _dedup_candidate(root, after, _REGISTRY, left, right)
    blocking, advisory, pairs = guard.check_range(None, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 2
    if lose_second_parent:
        assert [(f.code, f.parent) for f in blocking] == [("JOURNAL_SHRANK", right)]
        assert [f.parent for f in advisory] == [left]
    else:
        assert not blocking
        assert {f.parent for f in advisory} == {left, right}
        assert {f.code for f in advisory} == {"DUPLICATE_ROWS_DEDUPLICATED"}


def test_lossless_row_deduplication_does_not_hide_an_intermediate_shrink(guard, tmp_path):
    before = (_HEADER + _ROW_A * 2 + _ROW_B).encode()
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    lossy = _dedup_candidate(root, (_HEADER + _ROW_A).encode(), _REGISTRY, parent)
    repaired = _dedup_candidate(root, (_HEADER + _ROW_A + _ROW_B).encode(), _REGISTRY, lossy)
    blocking, _, pairs = guard.check_range(parent, repaired, files=(_REGISTRY,), root=root)
    assert pairs == 2
    assert [(f.code, f.commit) for f in blocking] == [("JOURNAL_SHRANK", lossy)]


def test_lossless_row_deduplication_preserves_an_unterminated_final_line(guard, tmp_path):
    before = (_HEADER + _ROW_A * 2 + "unchanged final prose").encode()
    after = (_HEADER + _ROW_A + "unchanged final prose").encode()
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    candidate = _dedup_candidate(root, after, _REGISTRY, parent)
    blocking, _, pairs = guard.check_range(parent, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 1 and not blocking


def test_lossless_row_deduplication_conflicts_require_preserved_audit_evidence(
    guard, tmp_path, monkeypatch
):
    """Different versions can be reconciled without shrinking or destroying either one."""
    closed = _ROW_A.replace("open", "closed")
    before = (_HEADER + _ROW_A + closed).encode()
    after = (
        _HEADER + closed + "\n## Resolution audit\n"
        "Operator selected the closed state; both original versions are retained below.\n"
        "```text\n" + _ROW_A + closed + "```\n"
    ).encode()
    assert len(after) > len(before)
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    candidate = _dedup_candidate(root, after, _REGISTRY, parent)
    blocking, advisory, pairs = guard.check_range(parent, candidate, files=(_REGISTRY,), root=root)
    assert pairs == 1 and not blocking
    assert [f.code for f in advisory] == ["PREFIX_NOT_PRESERVED"]
    duplicate = _load(
        ROOT / "scripts/ci/brain_duplicate_gap_identity_guard.py", "_duplicate_audit_probe"
    )
    monkeypatch.setattr(duplicate, "ROOT", root)
    assert not duplicate.check([root / _REGISTRY])
    assert _ROW_A.encode() in after and closed.encode() in after


# ── A-HISTORICAL-DIP-IS-NOT-REPAIRABLE-BY-A-LATER-COMMIT-01 ─────────────────────
#
# مقيسٌ على #1036 (2026-09-19): رأسُ الفرع كان **أكبرَ** من الأساس في السجلّات الأربعة
# كلِّها — أي أنّ المحتوى سليم — والحجبُ قائم، لأنّ حلَّ التعارض جرى على خطوتَين فأنزل
# التزامٌ وسيطٌ الملفَّين إلى مقاس `main` ثمّ استعادهما التزامٌ لاحق.
#
# والرسالةُ الثابتة كانت تصف علاجَ الرأس وحده. فقارئُها يُعيد البناء من كلا الوالدَين،
# ويبقى أحمر، ويستنتج أنّ الحارسَ معطوب — والحقيقةُ أنّ العلاجَ الصحيح إعادةُ تشكيلِ
# النافذة. صنفُ «رسالةٌ بلا علاج» في فرعه الثاني: علاجٌ حاضرٌ لكنّه لغير الحالة.


def test_a_historical_dip_says_that_a_later_commit_cannot_repair_it(guard, tmp_path):
    """الانخفاضُ الوسيطُ يُسمّى بموضعه، والعلاجُ المطبوع هو الذي يعمل عليه."""
    before = (_HEADER + _ROW_A + _ROW_B).encode()
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    dipped = _dedup_candidate(root, (_HEADER + _ROW_A).encode(), _REGISTRY, parent)
    restored = _dedup_candidate(
        root, (_HEADER + _ROW_A + _ROW_B + _ROW_A).encode(), _REGISTRY, dipped
    )

    blocking, _, _ = guard.check_range(parent, restored, files=(_REGISTRY,), root=root)
    assert [f.code for f in blocking] == ["JOURNAL_SHRANK"]

    remedy = guard.shrink_remedy(blocking, restored)
    assert "محفورٌ في التاريخ لا في الرأس" in remedy
    assert "أعِد تشكيلَ النافذة" in remedy
    assert dipped[:8] in remedy, "العلاجُ لا يسمّي الالتزامَ الذي يجب إعادةُ تشكيله"


def test_a_dip_at_the_head_keeps_the_tip_remedy_only(guard, tmp_path):
    """**الحدّ الذي يمنع الرسالةَ من أن تصير ديكوراً.**

    علاجُ التاريخ **مشتقٌّ** من كون الانخفاض في التزامٍ غيرِ الرأس. فإن طُبِع دائماً
    صار نصّاً ثابتاً يُطالب بنقض تاريخٍ لا داعي له في أكثر الحالات شيوعاً — دمجٌ
    يُكتب الآن وعلاجُه إعادةُ البناء من كلا الوالدَين، لا `--force-with-lease`.
    """
    before = (_HEADER + _ROW_A + _ROW_B).encode()
    root = _dedup_repo(tmp_path, before)
    parent = _dedup_git(root, "rev-parse", "HEAD")
    dipped = _dedup_candidate(root, (_HEADER + _ROW_A).encode(), _REGISTRY, parent)

    blocking, _, _ = guard.check_range(parent, dipped, files=(_REGISTRY,), root=root)
    remedy = guard.shrink_remedy(blocking, dipped)
    assert "كلا** الوالدَين" in remedy
    assert "محفورٌ في التاريخ" not in remedy
    assert "force-with-lease" not in remedy


# ── `AN-APPEND-ONLY-JOURNAL-OUTSIDE-THE-APPEND-ONLY-LIST-01` ────────────────
#
# قِيس 2026-09-21: رأسُ #1061 المدموج (`b067f92c`) حذف من
# `docs/evidence/operational_evidence_log.md` المدخلتين `E-2026-09-21-06` و
# `E-2026-09-21-07` (٣٦٣٧ بايت)، وكلُّ بوّابةٍ خضراء، فلزمت شريحةُ استرجاع (#1062).
# الحارسُ الذي وُجِد لهذا الصنف بعينه كان قائماً وأخضر — لأنّ الملفّ **خارج قائمته**.

_EVIDENCE_LOG = "docs/evidence/operational_evidence_log.md"


def test_an_append_only_journal_that_declares_itself_one_is_actually_guarded(guard):
    """**العطلُ مقيسٌ لا مفترَض** — والملفُّ يصف نفسه دفتراً إلحاقيّاً في سطره الثالث.

    حارسٌ قائمٌ وقائمتُه ناقصة يُقرَأ حمايةً ولا يحمي. ولأنّ القائمة مستورَدة (لا
    منسوخة)، إضافةُ المسار هنا تُفعّل الحارسَ و`resolve_merge_conflicts` معاً.
    """
    assert _EVIDENCE_LOG in guard.append_only_files(), (
        "سجلُّ الإثبات التشغيليّ خارج قائمة الدفاتر الإلحاقيّة — "
        "وهو ما سمح لـ`b067f92c` بحذف مدخلتين بكلّ بوّابةٍ خضراء (استُرجِعتا في #1062)"
    )
    header = (ROOT / _EVIDENCE_LOG).read_text(encoding="utf-8")[:600]
    # بلا تشكيل: النصّ يكتبها «إلحاقيٌّ» بتنوينٍ وشدّة، ومطابقةُ الصيغة المشكولة حرفيّاً
    # كانت تحمرّ على ملفٍّ يقول ما يجب أن يقوله بالضبط.
    assert "إلحاقي" in header, "الملفّ لم يعد يصف نفسه دفتراً إلحاقيّاً — راجع التصنيف"


def test_every_guarded_journal_exists_in_the_tree(guard):
    """مسارٌ في القائمة لا وجود له يُعدّ حراسةً وهو صفر — والقائمةُ تُقرأ ضماناً."""
    missing = [p for p in guard.append_only_files() if not (ROOT / p).is_file()]
    assert missing == [], f"مساراتٌ محروسةٌ لا وجودَ لها: {missing}"


def _rewind_repo(tmp_path: Path, journal_path: str) -> Path:
    """شكلُ **إعادة التأسيس** لا شكلُ التفريغ: فرعٌ أُسِّس قبل مدخلةٍ ثمّ أُخِذ جانبُه.

    هذا ما وقع فعلاً: `7a5cf0b3` بُني على `0606bb67` (قبل #1059)، فإعادةُ تأسيسٍ تأخذ
    نسخةَ الفرع تُعيد الماضي وتمحو ما لحقه — **بلا تعارضٍ يُظهِرها**. والفقدُ جزئيّ لا
    تفريغٌ إلى الصفر، فالشاهدُ القديم (الجانبُ الفارغ) لا يغطّيه.
    """
    root = tmp_path / "rewind"
    (root / journal_path).parent.mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    journal = root / journal_path
    git("init", "-q", "-b", "main", ".")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    journal.write_text("### E-01\n\n- أثرٌ أوّل\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")

    git("checkout", "-qb", "slice")
    old = journal.read_text(encoding="utf-8")
    git("checkout", "-q", "main")
    journal.write_text(old + "\n### E-02\n\n- أثرٌ ثانٍ كتبته شريحةٌ أخرى\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "another slice appends E-02")

    # إعادةُ التأسيس: الرأسُ الجديد يحمل نسخةَ الفرع القديمة فوق `main` الأحدث.
    git("checkout", "-q", "slice")
    git("merge", "main", "--no-edit", "-q")
    journal.write_text(old, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "re-founded: the slice's copy of the journal won", "--no-verify")
    return root


def test_a_refounding_that_rewinds_the_evidence_log_blocks(guard, tmp_path):
    """**تكذيبُ الحادثة بشكلها الحقيقيّ** — فقدٌ جزئيّ، لا تفريغٌ إلى الصفر."""
    root = _rewind_repo(tmp_path, _EVIDENCE_LOG)
    blocking, _, pairs = guard.check_range(None, "HEAD", files=(_EVIDENCE_LOG,), root=root)
    assert pairs >= 1, "لم يُفحَص أيُّ زوج — الفحصُ خاوٍ"
    assert "JOURNAL_SHRANK" in {f.code for f in blocking}, (
        "إعادةُ تأسيسٍ تُرجِع نسخةً أقدمَ من دفترٍ إلحاقيّ يجب أن تحجب"
    )


def test_a_refounding_that_keeps_both_entries_passes(guard, tmp_path):
    """الشاهدُ الإيجابيّ: العلاجُ المشروع يمرّ، وإلّا صارت بوّابةً لا تُغلَق بعملٍ صحيح."""
    root = _rewind_repo(tmp_path, _EVIDENCE_LOG)
    journal = root / _EVIDENCE_LOG
    journal.write_text(
        "### E-01\n\n- أثرٌ أوّل\n\n### E-02\n\n- أثرٌ ثانٍ كتبته شريحةٌ أخرى\n"
        "\n### E-03\n\n- أثرُ هذه الشريحة\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "keep both sides then append", "--no-verify"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    blocking, _, _ = guard.check_range(None, "HEAD", files=(_EVIDENCE_LOG,), root=root)
    assert not blocking, "\n".join(str(f) for f in blocking)


# ── `BRAIN-HOT-MD-UNBOUNDED-NO-ARCHIVE-PATH-01` ──────────────────────────────
#
# قِيس 2026-10-19 على `2a759d06`: `sahool-brain/hot.md` ٨٩٦٬٦٧٠ بايتاً يُقرأ في بداية كلّ
# جلسة (CLAUDE.md)، ونما ١٩٤٬٦٠٨ بايتاً في ثلاثين يوماً. والحارسُ أعلاه يحجب كلَّ تقلّص،
# فلم يكن للّقطة طريقُ ضغطٍ قطّ. قاعدةُ الاحتفاظ (UWRP Professional v4.3): سقفُ حجمٍ ثمّ
# أرشفةٌ معتمدة، لا محوٌ صامت. فالاستثناءُ ضيّق: تقلّصُ `hot.md` يُقبَل **فقط** إن ظهرت كلُّ
# كتلةٍ محذوفة حرفيّاً وبترتيبها في ملفٍّ تحت `sahool-brain/archive/` أُضيف أو أُلحِق به في
# الالتزام نفسه؛ والأرشيفُ نفسُه إلحاقيٌّ صارم؛ والسقفُ راتشِت لا يرتفع.
#
# كلُّ تاريخٍ هنا اصطناعيّ (كائنات git بلا HEAD متحرّك)، فلا اختبارَ يُتخطّى في استنساخٍ ضحل.

_HOT = "sahool-brain/hot.md"
_ARCHIVE = "sahool-brain/archive/hot_2026-07-01_2026-07-03.md"
_TOP = "> **2026-10-19 — newest entry stays in the snapshot**\n\n"
_OLD_A = "> **2026-07-01 — old entry A**\n>\n"
_MID = "> **2026-07-02 — a kept line a guard depends on**\n\n"
_OLD_B = "> **2026-07-03 — old entry B, `CLOSED_IN_CODE` quoted**\n\n"
_POINTER = (
    "> **2026-10-19 — older entries moved verbatim to archive/hot_2026-07-01_2026-07-03.md**\n"
)
_BUDGET = "docs/architecture/brain_hot_budget.json"


def _archive_git(root: Path, *args: str, data: bytes | None = None, env=None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, input=data, env=env
    )
    return result.stdout.decode("utf-8").strip()


def _archive_init(tmp_path: Path) -> Path:
    root = tmp_path / "archive-probe"
    root.mkdir()
    _archive_git(root, "init", "-q", "-b", "main", ".")
    _archive_git(root, "config", "user.email", "guard-test@example.invalid")
    _archive_git(root, "config", "user.name", "Guard Test")
    _archive_git(root, "config", "commit.gpgsign", "false")
    return root


def _snapshot(root: Path, files: dict[str, str | bytes], *parents: str) -> str:
    """A commit whose tree is exactly ``files`` — built in a private index, HEAD untouched."""
    import os

    env = {**os.environ, "GIT_INDEX_FILE": str(root / ".git" / "probe-index")}
    _archive_git(root, "read-tree", "--empty", env=env)
    for path, content in files.items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        blob = _archive_git(root, "hash-object", "-w", "--stdin", data=data)
        _archive_git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
    tree = _archive_git(root, "write-tree", env=env)
    parent_args = [item for parent in parents for item in ("-p", parent)]
    return _archive_git(root, "commit-tree", tree, *parent_args, "-m", "snapshot")


def _codes(findings) -> list[str]:
    return [f.code for f in findings]


@pytest.mark.parametrize(
    "archived,accepted",
    [
        pytest.param(_OLD_A + _OLD_B, True, id="in-order-verbatim-move"),
        pytest.param(_OLD_B + _OLD_A, False, id="reordered-move"),
    ],
)
def test_a_hot_md_shrink_is_accepted_only_as_an_in_order_verbatim_move(
    guard, tmp_path, archived, accepted
):
    """The narrow exception, and the order it requires — two removed blocks, one archive."""
    root = _archive_init(tmp_path)
    parent = _snapshot(root, {_HOT: _TOP + _OLD_A + _MID + _OLD_B})
    after = _TOP + _POINTER + _MID
    assert len(after.encode()) < len((_TOP + _OLD_A + _MID + _OLD_B).encode())
    candidate = _snapshot(root, {_HOT: after, _ARCHIVE: archived}, parent)
    blocking, advisory, _ = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    if accepted:
        assert not blocking, "\n".join(str(f) for f in blocking)
        assert _codes(advisory) == ["JOURNAL_ARCHIVED"]
        assert _ARCHIVE in advisory[0].detail
    else:
        assert _codes(blocking) == ["JOURNAL_SHRANK"]
        assert "out of order" in blocking[0].detail, blocking[0].detail


def test_a_hot_md_deletion_without_an_archive_blocks_and_names_the_archive(guard, tmp_path):
    """Deletion stays a loss, and the message names the only remedy that exists."""
    root = _archive_init(tmp_path)
    parent = _snapshot(root, {_HOT: _TOP + _OLD_A + _MID + _OLD_B})
    candidate = _snapshot(root, {_HOT: _TOP + _POINTER + _MID}, parent)
    blocking, advisory, _ = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    assert _codes(blocking) == ["JOURNAL_SHRANK"]
    assert "sahool-brain/archive/" in blocking[0].detail, blocking[0].detail
    assert "JOURNAL_ARCHIVED" not in _codes(advisory)


@pytest.mark.parametrize(
    "archived",
    [
        pytest.param(
            _OLD_A + _OLD_B.replace("old entry B", "old entry b"), id="one-letter-changed"
        ),
        pytest.param(_OLD_A, id="second-block-missing"),
        pytest.param((_OLD_A + _OLD_B).replace("\n", "\r\n"), id="line-endings-rewritten"),
    ],
)
def test_an_archive_that_does_not_hold_the_removed_bytes_verbatim_blocks(guard, tmp_path, archived):
    root = _archive_init(tmp_path)
    parent = _snapshot(root, {_HOT: _TOP + _OLD_A + _MID + _OLD_B})
    candidate = _snapshot(root, {_HOT: _TOP + _POINTER + _MID, _ARCHIVE: archived}, parent)
    blocking, _, _ = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    assert _codes(blocking) == ["JOURNAL_SHRANK"]
    assert "not verbatim" in blocking[0].detail, blocking[0].detail


def test_archive_text_from_an_earlier_commit_cannot_fund_a_new_shrink(guard, tmp_path):
    """Only bytes ADDED in the same diff count: an old archive is not a credit to spend."""
    root = _archive_init(tmp_path)
    duplicated = _TOP + _OLD_A + _MID + _OLD_A
    parent = _snapshot(root, {_HOT: duplicated, _ARCHIVE: _OLD_A})
    candidate = _snapshot(root, {_HOT: _TOP + _OLD_A + _MID, _ARCHIVE: _OLD_A}, parent)
    blocking, _, _ = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    assert _codes(blocking) == ["JOURNAL_SHRANK"]
    assert "sahool-brain/archive/" in blocking[0].detail, blocking[0].detail


@pytest.mark.parametrize(
    "later,code",
    [
        pytest.param(_OLD_A, "ARCHIVE_REWRITTEN", id="archive-shrunk"),
        pytest.param(_OLD_A + _OLD_B.replace("B", "C"), "ARCHIVE_REWRITTEN", id="archive-edited"),
        pytest.param(None, "ARCHIVE_DELETED", id="archive-deleted"),
        pytest.param(_OLD_A + _OLD_B + _TOP, None, id="archive-appended-is-legal"),
    ],
)
def test_an_archive_is_append_only_after_it_lands(guard, tmp_path, later, code):
    root = _archive_init(tmp_path)
    archived_tree = {_HOT: _TOP + _POINTER + _MID, _ARCHIVE: _OLD_A + _OLD_B}
    parent = _snapshot(root, archived_tree)
    files = dict(archived_tree)
    if later is None:
        del files[_ARCHIVE]
    else:
        files[_ARCHIVE] = later
    candidate = _snapshot(root, files, parent)
    blocking, _, pairs = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    assert pairs == 2, "the archive itself must be one of the examined pairs"
    if code is None:
        assert not blocking, "\n".join(str(f) for f in blocking)
    else:
        assert _codes(blocking) == [code]
        assert blocking[0].path == _ARCHIVE


@pytest.mark.parametrize(
    "journal",
    ["sahool-brain/log.md", "sahool-brain/gaps/registry.md", "sahool-brain/decisions/ledger.md"],
)
def test_the_archive_exception_is_hot_md_only(guard, tmp_path, journal):
    """Every other journal keeps its behaviour: an archive copy does not license a shrink."""
    assert guard.archive_dirs() == {_HOT: "sahool-brain/archive/"}
    root = _archive_init(tmp_path)
    parent = _snapshot(root, {journal: _TOP + _OLD_A + _MID + _OLD_B})
    candidate = _snapshot(
        root,
        {journal: _TOP + _POINTER + _MID, _ARCHIVE: _OLD_A + _OLD_B},
        parent,
    )
    blocking, advisory, _ = guard.check_range(parent, candidate, files=(journal,), root=root)
    assert _codes(blocking) == ["JOURNAL_SHRANK"]
    assert "JOURNAL_ARCHIVED" not in _codes(advisory)


def test_the_archive_policy_comes_from_the_existing_classifier(guard):
    resolver = _load(RESOLVER, "_resolve_archive_probe")
    assert guard.archive_dirs() == dict(resolver.ARCHIVES)
    for archive_dir in resolver.ARCHIVES.values():
        assert f'"{archive_dir}"' not in GUARD.read_text(encoding="utf-8"), (
            "the archive directory is restated in the guard; it must come from the classifier"
        )
        assert resolver.classify(archive_dir + "hot_x.md") == "append_only"


@pytest.mark.parametrize("main_compacted_first", [True, False])
def test_an_older_branch_merging_the_compaction_passes_on_both_parents(
    guard, tmp_path, main_compacted_first
):
    """The shape every open PR meets after the compaction lands: one parent still has it all."""
    root = _archive_init(tmp_path)
    ancestor = _snapshot(root, {_HOT: _TOP + _OLD_A + _MID + _OLD_B})
    compacted = _snapshot(root, {_HOT: _TOP + _POINTER + _MID, _ARCHIVE: _OLD_A + _OLD_B}, ancestor)
    branch_top = "> **2026-10-20 — a line the older branch added**\n"
    branch = _snapshot(root, {_HOT: branch_top + _TOP + _OLD_A + _MID + _OLD_B}, ancestor)
    parents = (compacted, branch) if main_compacted_first else (branch, compacted)
    merge = _snapshot(
        root,
        {_HOT: branch_top + _TOP + _POINTER + _MID, _ARCHIVE: _OLD_A + _OLD_B},
        *parents,
    )
    blocking, advisory, _ = guard.check_range(ancestor, merge, files=(_HOT,), root=root)
    assert not blocking, "\n".join(str(f) for f in blocking)
    archived_pairs = {(f.parent, f.commit) for f in advisory if f.code == "JOURNAL_ARCHIVED"}
    assert archived_pairs == {(ancestor, compacted), (branch, merge)}


def test_a_line_kept_between_two_cuts_is_aligned_to_itself_not_to_a_blank(guard, tmp_path):
    """Found by the first real compaction, which the guard refused (2026-10-19).

    Fifteen old lines stayed in ``hot.md`` between the archived runs, with a blank line
    between them. An alignment that may anchor on a blank matched the inserted blank to a
    blank inside a cut, and then read a KEPT line as removed — a removal no archive holds,
    so a lossless move was blocked as ``not verbatim``. Blank and lone ``>`` lines may not
    anchor the alignment; they still travel with the run they sit in.
    """
    kept = "> **2026-07-02 — a kept line a guard depends on**\n"
    row = "| WS-C.1c | a kept table row a guard depends on |\n"
    old_a = "> **2026-07-01 — archived A**\n\n> **2026-07-01 — archived B**\n"
    old_c = "> **2026-07-03 — archived C**\n"
    root = _archive_init(tmp_path)
    parent = _snapshot(root, {_HOT: _TOP + old_a + kept + old_c + row})
    candidate = _snapshot(
        root, {_HOT: _TOP + _POINTER + kept + "\n" + row, _ARCHIVE: old_a + old_c}, parent
    )
    blocking, advisory, _ = guard.check_range(parent, candidate, files=(_HOT,), root=root)
    assert not blocking, "\n".join(str(f) for f in blocking)
    assert _codes(advisory) == ["JOURNAL_ARCHIVED"]


# ── the size budget: a ratchet, never raised ────────────────────────────────


def _budget(max_bytes: int) -> str:
    import json

    return json.dumps({"budgets": {_HOT: {"max_bytes": max_bytes}}}, indent=2) + "\n"


@pytest.mark.parametrize(
    "base_limit,head_limit,code",
    [
        pytest.param(100, 120, "BUDGET_RAISED", id="raised"),
        pytest.param(100, 100, None, id="unchanged"),
        pytest.param(100, 80, None, id="lowered"),
    ],
)
def test_the_budget_never_rises(guard, tmp_path, base_limit, head_limit, code):
    root = _archive_init(tmp_path)
    base = _snapshot(root, {_HOT: _TOP, _BUDGET: _budget(base_limit)})
    head = _snapshot(root, {_HOT: _TOP, _BUDGET: _budget(head_limit)}, base)
    blocking, _ = guard.check_budget(base, head, root=root)
    assert _codes(blocking) == ([code] if code else [])


@pytest.mark.parametrize("excess,code", [(1, "BUDGET_EXCEEDED"), (0, None)])
def test_hot_md_may_not_exceed_its_budget_at_head(guard, tmp_path, excess, code):
    root = _archive_init(tmp_path)
    limit = len((_TOP + _MID).encode())
    head_text = _TOP + _MID + ("x" * excess)
    base = _snapshot(root, {_HOT: _TOP, _BUDGET: _budget(limit)})
    head = _snapshot(root, {_HOT: head_text, _BUDGET: _budget(limit)}, base)
    blocking, _ = guard.check_budget(base, head, root=root)
    assert _codes(blocking) == ([code] if code else [])
    if code:
        assert "sahool-brain/archive/" in blocking[0].detail, "the remedy is archival, not a raise"


@pytest.mark.parametrize(
    "base_files,head_files,code",
    [
        pytest.param({_BUDGET: _budget(100)}, {}, "BUDGET_ABSENT_AT_HEAD", id="budget-deleted"),
        pytest.param({}, {}, "BUDGET_ABSENT_AT_HEAD", id="never-declared-is-not-a-pass"),
        pytest.param(
            {_BUDGET: _budget(100)},
            {_BUDGET: '{"budgets": {}}\n'},
            "BUDGET_RAISED",
            id="journal-dropped-from-budget",
        ),
        pytest.param({}, {_BUDGET: "{not json"}, "BUDGET_UNREADABLE", id="malformed"),
        pytest.param({}, {_BUDGET: _budget(100)}, None, id="introduced"),
    ],
)
def test_a_missing_or_unreadable_budget_fails_closed(guard, tmp_path, base_files, head_files, code):
    root = _archive_init(tmp_path)
    base = _snapshot(root, {_HOT: _TOP, **base_files})
    head = _snapshot(root, {_HOT: _TOP, **head_files}, base)
    blocking, advisory = guard.check_budget(base, head, root=root)
    assert _codes(blocking) == ([code] if code else [])
    if code is None:
        assert _codes(advisory) == ["BUDGET_INTRODUCED"]


def test_the_committed_budget_holds_on_this_tree(guard):
    """The live number: hot.md at this tree fits the committed budget, which is a decision."""
    import json

    doc = json.loads((ROOT / _BUDGET).read_text(encoding="utf-8"))
    limit = doc["budgets"][_HOT]["max_bytes"]
    size = (ROOT / _HOT).stat().st_size
    assert size <= limit, f"hot.md is {size:,} bytes, budget {limit:,}"
    registry = json.loads(
        (ROOT / "docs/architecture/claim_base_registry.json").read_text(encoding="utf-8")
    )
    assert Path(_BUDGET).name in registry["decided"], "the budget is an owner decision"
    assert doc.get("adjudicated_on"), "a decision carries its date"
