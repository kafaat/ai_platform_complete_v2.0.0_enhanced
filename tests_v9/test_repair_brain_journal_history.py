"""Repair a restored historical dip without mutating the source branch or its files.

The 485-byte loss in PR #1335 is reproduced in ordinary temporary Git repositories.
The unchanged append-only guard remains the oracle: the source stays red, while a
new commit with the same final tree and the last good parent must pass.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = "sahool-brain/gaps/registry.md"
HOT = "sahool-brain/hot.md"
LIMIT = 2048


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load(ROOT / "scripts/ci/brain_append_only_guard.py", "_repair_test_brain_guard")


@pytest.fixture(scope="module")
def repair():
    return _load(ROOT / "scripts/ci/repair_brain_journal_history.py", "_repair_history_test")


def _run_git(root: Path, *args: str, check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=check,
        env={
            **os.environ,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_GRAFT_FILE": os.path.join(os.devnull, "grafts"),
        },
    )


def _git(root: Path, *args: str) -> str:
    return _run_git(root, *args).stdout.decode("utf-8").strip()


def _blob(root: Path, ref: str, path: str) -> bytes:
    return _run_git(root, "show", f"{ref}:{path}").stdout


def _commit(root: Path, files: dict[str, bytes], message: str) -> str:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _line(prefix: str, size: int) -> bytes:
    data = prefix.encode("utf-8")
    return data + b"x" * (size - len(data) - 1) + b"\n"


HISTORICAL_LINE = _line("نصّ تاريخي يجب الاحتفاظ به: ", 1324)
SHORTER_LINE = _line("An incorrect replacement: ", 839)
CLOSURE_LINE = _line("Evidence added without deleting history: ", 801)
BEFORE = b"# Registry\n" + HISTORICAL_LINE + b"Last entry\n"
SHRUNK = BEFORE.replace(HISTORICAL_LINE, SHORTER_LINE)
RESTORED = BEFORE.replace(HISTORICAL_LINE, HISTORICAL_LINE + CLOSURE_LINE)


@dataclass
class Incident:
    root: Path
    base: str
    parent: str
    shrink: str
    head: str

    def args(self, **overrides):
        return {
            "root": self.root,
            "base": self.base,
            "parent": self.parent,
            "head": "source",
            "branch": "journal-repaired",
            **overrides,
        }


def _incident(tmp_path: Path, guard, *, earlier_loss: bool = False) -> Incident:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Journal repair test")
    _git(root, "config", "user.email", "journal-test@example.invalid")
    _git(root, "config", "commit.gpgSign", "false")
    _git(root, "config", "core.autocrlf", "false")
    files = {name: b"An existing journal entry.\n" for name in guard.append_only_files()}
    files[JOURNAL] = BEFORE
    files[guard.BUDGET] = json.dumps({"budgets": {HOT: {"max_bytes": LIMIT}}}).encode()
    files["service.py"] = b"mode = 'base'\n"
    base = _commit(root, files, "base")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    _git(root, "checkout", "-qb", "source")
    parent_files = {"service.py": b"mode = 'maintenance'\n"}
    if earlier_loss:
        parent_files["sahool-brain/log.md"] = b""
    parent = _commit(root, parent_files, "parent before the requested repair window")
    shrink = _commit(root, {JOURNAL: SHRUNK}, "replace historical paragraph")
    head = _commit(
        root,
        {JOURNAL: RESTORED, "service.py": b"mode = 'finished'\n"},
        "restore historical paragraph and retain the closure",
    )
    return Incident(root, base, parent, shrink, head)


@pytest.fixture
def incident(tmp_path, guard):
    return _incident(tmp_path, guard)


def _refs(root: Path) -> dict[str, str]:
    return {
        line.split(" ", 1)[1]: line.split(" ", 1)[0] for line in _git(root, "show-ref").splitlines()
    }


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _objects(root: Path) -> set[str]:
    return set(_git(root, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())


def _assert_no_destination(root: Path, branch: str = "journal-repaired") -> None:
    assert _run_git(root, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode


def test_plan_reproduces_the_485_byte_incident_without_persistent_writes(incident, guard, repair):
    blocking, _, pairs = guard.check_range(incident.base, incident.head, root=incident.root)
    assert pairs > 0
    assert [finding.code for finding in blocking] == ["JOURNAL_SHRANK"]
    assert blocking[0].parent == incident.parent
    assert blocking[0].commit == incident.shrink
    assert "485" in blocking[0].detail
    assert len(BEFORE) - len(SHRUNK) == 485
    refs, objects = _refs(incident.root), _objects(incident.root)
    index = (incident.root / ".git/index").read_bytes()

    result = repair.repair_history(**incident.args())

    assert result["status"] == "planned"
    assert result["applied"] is False
    assert result["commits_squashed"] == 2
    assert result["head"] == incident.head
    assert result["tree"] == _git(incident.root, "rev-parse", f"{incident.head}^{{tree}}")
    assert _refs(incident.root) == refs
    assert _objects(incident.root) == objects
    assert (incident.root / ".git/index").read_bytes() == index
    _assert_no_destination(incident.root)


def test_apply_keeps_exact_tree_and_dirty_worktree_while_only_new_branch_passes(
    incident, guard, repair
):
    root = incident.root
    (root / "service.py").write_bytes(b"staged user change\n")
    _git(root, "add", "service.py")
    (root / "service.py").write_bytes(b"unstaged user change\n")
    (root / "untracked.txt").write_bytes(b"untracked user work\n")
    refs, files = _refs(root), _files(root)
    index = (root / ".git/index").read_bytes()
    symbolic_head = (root / ".git/HEAD").read_bytes()

    result = repair.repair_history(**incident.args(apply=True))

    candidate = result["candidate"]
    assert result["status"] == "created"
    assert result["applied"] is True
    assert _refs(root) == {**refs, "refs/heads/journal-repaired": candidate}
    assert _git(root, "rev-list", "--parents", "-n", "1", candidate).split() == [
        candidate,
        incident.parent,
    ]
    assert _git(root, "diff", "--exit-code", incident.head, candidate) == ""
    assert _git(root, "rev-parse", f"{candidate}^{{tree}}") == _git(
        root, "rev-parse", f"{incident.head}^{{tree}}"
    )
    assert _blob(root, candidate, JOURNAL) == RESTORED
    assert not guard.check_range(incident.base, candidate, root=root)[0]
    assert not guard.check_budget(incident.base, candidate, root=root)[0]
    assert {f.code for f in guard.check_range(incident.base, "source", root=root)[0]} == {
        "JOURNAL_SHRANK"
    }
    assert (root / ".git/HEAD").read_bytes() == symbolic_head
    assert (root / ".git/index").read_bytes() == index
    assert _files(root) == files


def test_current_base_can_advance_independently_after_the_source_fork(incident, guard, repair):
    root = incident.root
    _git(root, "checkout", "-q", "main")
    advanced = _commit(
        root,
        {"repair_tool.py": b"# An independently merged repair tool.\n"},
        "advance main independently",
    )
    _git(root, "update-ref", "refs/remotes/origin/main", advanced)
    _git(root, "checkout", "-q", "source")
    assert _git(root, "merge-base", "--all", advanced, incident.parent) == incident.base
    assert advanced != incident.base
    refs = _refs(root)

    result = repair.repair_history(**incident.args(base="origin/main", apply=True))

    candidate = result["candidate"]
    assert result["base"] == advanced
    assert _refs(root) == {**refs, "refs/heads/journal-repaired": candidate}
    assert _git(root, "rev-parse", f"{candidate}^") == incident.parent
    assert _git(root, "diff", "--exit-code", incident.head, candidate) == ""
    assert _git(root, "rev-parse", f"{candidate}^{{tree}}") == result["tree"]
    assert not guard.check_range("origin/main", candidate, root=root)[0]
    assert not guard.check_budget("origin/main", candidate, root=root)[0]
    assert {
        finding.code for finding in guard.check_range("origin/main", "source", root=root)[0]
    } == {"JOURNAL_SHRANK"}


def test_unrelated_base_is_rejected_without_creating_a_branch(incident, repair):
    root = incident.root
    tree = _git(root, "rev-parse", f"{incident.base}^{{tree}}")
    unrelated = _git(root, "commit-tree", tree, "-m", "unrelated root history")
    assert (
        _run_git(root, "merge-base", "--all", unrelated, incident.parent, check=False).returncode
        == 1
    )
    refs = _refs(root)
    with pytest.raises(repair.RepairError, match="INVALID_BASE"):
        repair.repair_history(**incident.args(base=unrelated, apply=True))
    assert _refs(root) == refs
    _assert_no_destination(root)


def test_ambiguous_merge_bases_require_manual_review(incident, repair):
    root = incident.root
    tree = _git(root, "rev-parse", f"{incident.parent}^{{tree}}")
    first = _git(root, "commit-tree", tree, "-p", incident.base, "-m", "first independent parent")
    second = _git(root, "commit-tree", tree, "-p", incident.base, "-m", "second independent parent")
    parent = _git(root, "commit-tree", tree, "-p", first, "-p", second, "-m", "source-side merge")
    base = _git(root, "commit-tree", tree, "-p", second, "-p", first, "-m", "base-side merge")
    shrink_tree = _git(root, "rev-parse", f"{incident.shrink}^{{tree}}")
    head_tree = _git(root, "rev-parse", f"{incident.head}^{{tree}}")
    shrink = _git(root, "commit-tree", shrink_tree, "-p", parent, "-m", "historical shrink")
    head = _git(root, "commit-tree", head_tree, "-p", shrink, "-m", "restoration")
    assert set(_git(root, "merge-base", "--all", base, parent).splitlines()) == {first, second}
    refs = _refs(root)
    with pytest.raises(repair.RepairError, match="INVALID_BASE"):
        repair.repair_history(**incident.args(base=base, parent=parent, head=head, apply=True))
    assert _refs(root) == refs
    _assert_no_destination(root)


@pytest.mark.parametrize("replacement", [SHORTER_LINE, _line("Lost original text: ", 1324)])
def test_missing_original_text_is_rejected_even_when_byte_length_is_restored(
    incident, repair, replacement
):
    _commit(
        incident.root,
        {JOURNAL: RESTORED.replace(HISTORICAL_LINE, replacement)},
        "head no longer retains the original paragraph",
    )
    refs = _refs(incident.root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    assert _refs(incident.root) == refs
    _assert_no_destination(incident.root)


def _second_cycle_with_intermediate_entry(incident, other_journal, *, restore_entry):
    """A second registry dip must also protect entries added to another journal."""
    root = incident.root
    original = _blob(root, incident.head, other_journal)
    intermediate = original + b"Protected entry between the two registry repair cycles.\n"
    checkpoint = _commit(
        root, {other_journal: intermediate}, "append another journal between registry repairs"
    )
    shrink = _commit(
        root,
        {JOURNAL: RESTORED.replace(HISTORICAL_LINE, SHORTER_LINE)},
        "second historical registry shrink",
    )
    final = (
        intermediate + b"Additional evidence after preserving the intermediate entry.\n"
        if restore_entry
        else original
        + b"A longer replacement loses the protected intermediate entry without shrinking.\n"
    )
    head = _commit(
        root,
        {JOURNAL: RESTORED, other_journal: final},
        "restore registry and record the final other journal",
    )
    return checkpoint, shrink, head, intermediate


@pytest.mark.parametrize(
    "other_journal",
    [
        "sahool-brain/log.md",
        "sahool-brain/decisions/ledger.md",
        HOT,
        "docs/evidence/operational_evidence_log.md",
    ],
)
@pytest.mark.parametrize("apply", [False, True], ids=["plan", "apply"])
def test_every_pre_shrink_checkpoint_preserves_every_classified_journal(
    incident, guard, repair, other_journal, apply
):
    """Size-only checks miss replacing an intermediate entry with a longer line."""
    assert other_journal in guard.append_only_files()
    root = incident.root
    checkpoint, shrink, head, intermediate = _second_cycle_with_intermediate_entry(
        incident, other_journal, restore_entry=False
    )
    assert len(_blob(root, head, other_journal)) > len(intermediate)
    blocking, _, _ = guard.check_range(incident.base, head, root=root)
    assert {(finding.code, finding.path, finding.commit) for finding in blocking} == {
        ("JOURNAL_SHRANK", JOURNAL, incident.shrink),
        ("JOURNAL_SHRANK", JOURNAL, shrink),
    }
    refs, objects, files = _refs(root), _objects(root), _files(root)
    index = (root / ".git/index").read_bytes()
    with pytest.raises(repair.RepairError, match="UNRESTORED_JOURNAL") as caught:
        repair.repair_history(**incident.args(apply=apply))
    assert other_journal in str(caught.value)
    assert checkpoint in str(caught.value)
    assert _refs(root) == refs
    assert _objects(root) == objects
    assert _files(root) == files
    assert (root / ".git/index").read_bytes() == index
    _assert_no_destination(root)


@pytest.mark.parametrize(
    "other_journal",
    [
        "sahool-brain/log.md",
        "sahool-brain/decisions/ledger.md",
        HOT,
        "docs/evidence/operational_evidence_log.md",
    ],
)
def test_restoring_all_journals_after_multiple_shrink_cycles_is_accepted(
    incident, guard, repair, other_journal
):
    root = incident.root
    _, _, head, intermediate = _second_cycle_with_intermediate_entry(
        incident, other_journal, restore_entry=True
    )
    refs, files = _refs(root), _files(root)
    result = repair.repair_history(**incident.args(apply=True))
    candidate = result["candidate"]
    assert result["status"] == "created"
    assert result["shrinks_repaired"] == 2
    assert result["commits_squashed"] == 5
    assert result["tree"] == _git(root, "rev-parse", f"{head}^{{tree}}")
    assert _git(root, "diff", "--exit-code", head, candidate) == ""
    assert _blob(root, candidate, other_journal).startswith(intermediate)
    assert not guard.check_range(incident.base, candidate, root=root)[0]
    assert _refs(root) == {**refs, "refs/heads/journal-repaired": candidate}
    assert _files(root) == files


def test_an_existing_destination_is_never_moved(incident, repair):
    _git(incident.root, "branch", "journal-repaired", incident.base)
    refs = _refs(incident.root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    assert _refs(incident.root) == refs


def test_dangling_symbolic_destination_is_not_followed(incident, repair):
    root = incident.root
    ref = "refs/heads/journal-repaired"
    target = "refs/heads/unrelated"
    _git(root, "symbolic-ref", ref, target)
    refs = _refs(root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    assert _refs(root) == refs
    assert _git(root, "symbolic-ref", ref) == target
    assert _run_git(root, "show-ref", "--verify", target, check=False).returncode


@pytest.mark.parametrize("kind", ["direct", "symbolic"])
def test_concurrent_destination_creation_is_not_overwritten(incident, repair, monkeypatch, kind):
    create = repair._create_branch
    target = "refs/heads/unrelated"

    def race(root, ref, candidate):
        if kind == "direct":
            _git(root, "update-ref", ref, incident.base)
        else:
            _git(root, "symbolic-ref", ref, target)
        return create(root, ref, candidate)

    monkeypatch.setattr(repair, "_create_branch", race)
    refs = _refs(incident.root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    if kind == "direct":
        assert _refs(incident.root) == {**refs, "refs/heads/journal-repaired": incident.base}
    else:
        assert _refs(incident.root) == refs
        assert _git(incident.root, "symbolic-ref", "refs/heads/journal-repaired") == target
        assert _run_git(incident.root, "show-ref", "--verify", target, check=False).returncode


def test_a_dangling_symbolic_destination_is_refused_and_left_intact(incident, repair):
    """git 2.43 lets `update-ref --no-deref` `create` replace a dangling symref; the
    transaction must refuse it, keep the symref, and release the destination lock.

    Newer git (measured: 2.56.0 on the CI runner) already refuses at `prepare` with
    "dangling symref already exists"; on 2.43 the refusal comes from the check under the
    lock. Either refusal is correct — the assertions below are what must hold on both."""
    root = incident.root
    ref, target = "refs/heads/journal-repaired", "refs/heads/unrelated"
    _git(root, "symbolic-ref", ref, target)
    with pytest.raises(repair.RepairError, match="symbolic ref|dangling symref"):
        repair._create_branch(root, ref, incident.base)
    assert _git(root, "symbolic-ref", ref) == target
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir"))
    assert not list(git_dir.rglob("*.lock")), "the destination lock must be released"


def test_merge_windows_require_manual_review(incident, repair):
    root = incident.root
    _git(root, "checkout", "-qb", "side", incident.parent)
    _commit(root, {"side.txt": b"work from another parent\n"}, "side work")
    _git(root, "checkout", "-q", "source")
    _git(root, "merge", "--no-ff", "-qm", "merge side work", "side")
    refs = _refs(root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    assert _refs(root) == refs
    _assert_no_destination(root)


def test_shallow_repository_cannot_claim_complete_history(incident, repair, tmp_path):
    shallow = tmp_path / "shallow"
    _git(
        tmp_path,
        "clone",
        "-q",
        "--depth=3",
        "--branch=source",
        incident.root.as_uri(),
        str(shallow),
    )
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    _git(shallow, "config", "user.name", "Journal repair test")
    _git(shallow, "config", "user.email", "journal-test@example.invalid")
    with pytest.raises(repair.RepairError, match="(?i)shallow"):
        repair.repair_history(**incident.args(root=shallow, base=incident.parent, apply=True))
    _assert_no_destination(shallow)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base", "missing-base"),
        ("parent", "missing-parent"),
        ("head", "missing-head"),
        ("branch", "../outside"),
        ("parent", "source"),
    ],
)
def test_invalid_inputs_do_not_create_a_destination(incident, repair, field, value):
    refs = _refs(incident.root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(**{field: value}, apply=True))
    assert _refs(incident.root) == refs


def test_a_shrink_before_the_selected_window_is_still_blocking(tmp_path, guard, repair):
    incident = _incident(tmp_path, guard, earlier_loss=True)
    blocking, _, _ = guard.check_range(incident.base, incident.head, root=incident.root)
    assert {finding.commit for finding in blocking} == {incident.parent, incident.shrink}
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    _assert_no_destination(incident.root)


def test_healthy_history_is_not_squashed(incident, repair):
    root = incident.root
    _git(root, "checkout", "-qb", "healthy", incident.parent)
    _commit(root, {JOURNAL: BEFORE + b"new evidence\n"}, "append evidence")
    _commit(root, {"service.py": b"mode = 'healthy'\n"}, "ordinary source change")
    refs = _refs(root)
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(head="healthy", apply=True))
    assert _refs(root) == refs


def test_other_guard_failures_are_not_hidden_by_squashing(incident, guard, repair):
    root = incident.root
    hot = _blob(root, incident.head, HOT)
    _commit(root, {HOT: hot + b"x" * (LIMIT + 1)}, "exceed the unchanged byte budget")
    budget_failures, _ = guard.check_budget(incident.base, "source", root=root)
    assert [finding.code for finding in budget_failures] == ["BUDGET_EXCEEDED"]
    with pytest.raises(repair.RepairError):
        repair.repair_history(**incident.args(apply=True))
    _assert_no_destination(root)


@pytest.mark.parametrize("override", ["replace", "graft"])
def test_local_history_overrides_do_not_hide_the_real_dip(incident, repair, override):
    root = incident.root
    if override == "replace":
        _git(root, "replace", incident.shrink, incident.parent)
    else:
        (root / ".git/info/grafts").write_text(incident.shrink + "\n", encoding="utf-8")
    refs = _refs(root)
    result = repair.repair_history(**incident.args(apply=True))
    assert result["status"] == "created"
    assert _refs(root) == {**refs, "refs/heads/journal-repaired": result["candidate"]}
    assert _git(root, "diff", "--exit-code", incident.head, result["candidate"]) == ""


def test_cli_defaults_to_plan_and_reports_rejection_as_failure(
    incident, repair, monkeypatch, capsys
):
    monkeypatch.setattr(repair, "ROOT", incident.root)
    args = [
        "--base",
        "origin/main",
        "--parent",
        incident.parent,
        "--branch",
        "journal-repaired",
    ]
    assert repair.main(args) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "planned"
    _assert_no_destination(incident.root)

    assert repair.main([*args, "--head", "missing-source", "--apply"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.err or output.out)["status"] == "blocked"
    _assert_no_destination(incident.root)
