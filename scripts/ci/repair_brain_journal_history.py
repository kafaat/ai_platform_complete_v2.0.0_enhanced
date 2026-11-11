#!/usr/bin/env python3
"""Prepare a new branch that combines a restored, linear journal repair window.

The existing append-only guard remains authoritative. A later restoration does not
erase a historical shrink; combining that shrink and restoration can, provided every
original journal line survives in order and the final tree stays byte-identical.

The default is a plan using temporary Git objects. ``--apply`` creates only a new
local branch; it never checks out files, moves an existing ref, or pushes anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
GUARD = Path(__file__).with_name("brain_append_only_guard.py")


class RepairError(RuntimeError):
    """The requested history cannot be repaired by this narrow operation."""


def _git_env(objects: Path | None = None, alternate: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_SHALLOW_FILE",
    ):
        env.pop(name, None)
    env.update(
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_GRAFT_FILE=os.path.join(os.devnull, "grafts"),
        GIT_NO_LAZY_FETCH="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
    )
    if objects is not None:
        env["GIT_OBJECT_DIRECTORY"] = str(objects)
    if alternate is not None:
        # Git understands C-quoted paths, including an embedded path-list separator.
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = json.dumps(str(alternate), ensure_ascii=False)
    return env


def _git(
    root: Path,
    *args: str,
    input: bytes | None = None,
    objects: Path | None = None,
    alternate: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    env = _git_env(objects, alternate)
    result = subprocess.run(["git", *args], cwd=root, input=input, capture_output=True, env=env)
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RepairError(f"git {args[0]} failed: {detail}")
    return result


def _resolve(root: Path, ref: str) -> str:
    return (
        _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        .stdout.decode("ascii")
        .strip()
    )


@contextmanager
def _no_bytecode():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def _load_guard(*, objects: Path | None = None, alternate: Path | None = None) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_journal_history_repair_guard", GUARD)
    if spec is None or spec.loader is None:
        raise RepairError(f"Cannot load the existing guard: {GUARD}")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    def guarded_git(*args: str, root: Path = ROOT):
        return _git(root, *args, objects=objects, alternate=alternate, check=False)

    # Only the object store changes. Classification and every guard rule are reused.
    guard._git = guarded_git
    return guard


def _findings(guard: ModuleType, root: Path, base: str, head: str):
    try:
        blocking, advisory, pairs = guard.check_range(base, head, root=root)
        budget_blocking, budget_advisory = guard.check_budget(base, head, root=root)
    except SystemExit as exc:
        raise RepairError(f"Guard could not inspect the history: {exc}") from exc
    return blocking + budget_blocking, advisory + budget_advisory, pairs


def _preserve_lines(before: bytes, after: bytes, path: str, parent: str) -> None:
    """Prove byte-line subsequence preservation, including duplicate lines/newlines."""
    remaining = iter(after.splitlines(keepends=True))
    for number, line in enumerate(before.splitlines(keepends=True), 1):
        if not any(candidate == line for candidate in remaining):
            raise RepairError(
                f"UNRESTORED_JOURNAL: {path} line {number} from {parent} "
                "is missing, changed, or reordered at head"
            )


def _create_branch(root: Path, ref: str, candidate: str) -> None:
    """Create ``ref`` only if nothing — not even a dangling symbolic ref — occupies it.

    ``create`` is an absent-ref compare-and-swap, but git 2.43 treats a *dangling* symbolic
    ref as absent and, with ``--no-deref``, replaces it (reproduced: exit 0, the symref is
    gone). So the creation runs as a transaction: ``prepare`` takes the destination lock,
    the symbolic-ref check runs while that lock is held — no git-mediated writer can change
    the ref until ``commit``/``abort`` — and only then is the transaction committed.
    """
    proc = subprocess.Popen(
        ["git", "update-ref", "--no-deref", "--stdin"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_env(),
    )
    assert proc.stdin is not None and proc.stdout is not None

    def send(line: str) -> None:
        proc.stdin.write(line.encode() + b"\n")
        proc.stdin.flush()

    def expect(step: str) -> None:
        got = proc.stdout.readline().decode("ascii", "replace").strip()
        if got != f"{step}: ok":
            proc.stdin.close()
            detail = proc.stderr.read().decode("utf-8", "replace").strip()
            proc.wait()
            raise RepairError(
                f"git update-ref {step} failed for {ref}: {detail or got or 'no output'}"
            )

    try:
        send("start")
        expect("start")
        send(f"create {ref} {candidate}")
        send("prepare")
        expect("prepare")
        if _git(root, "symbolic-ref", "-q", ref, check=False).returncode == 0:
            send("abort")
            expect("abort")
            raise RepairError(f"{ref} exists as a symbolic ref; refusing to replace it")
        send("commit")
        expect("commit")
    finally:
        if not proc.stdin.closed:
            proc.stdin.close()
        proc.wait()


def repair_history(
    *,
    root: Path,
    base: str,
    parent: str,
    head: str = "HEAD",
    branch: str,
    apply: bool = False,
) -> dict[str, object]:
    """Plan or create a new branch; all source refs and the source tree stay intact."""
    with _no_bytecode():
        return _repair_history(
            root=Path(root).resolve(),
            base=base,
            parent=parent,
            head=head,
            branch=branch,
            apply=apply,
        )


def _repair_history(
    *, root: Path, base: str, parent: str, head: str, branch: str, apply: bool
) -> dict[str, object]:
    if _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() != b"false":
        raise RepairError("SHALLOW_HISTORY: a complete history is required")
    if not branch or branch.startswith(("-", "refs/")) or branch == "HEAD":
        raise RepairError("INVALID_BRANCH: supply a new branch name, not a ref or revision")
    ref = f"refs/heads/{branch}"
    _git(root, "check-ref-format", ref)
    symbolic = _git(root, "symbolic-ref", "--quiet", ref, check=False)
    if symbolic.returncode == 0:
        raise RepairError(f"BRANCH_EXISTS: destination is a symbolic ref: {ref}")
    if symbolic.returncode != 1:
        raise RepairError(f"Cannot inspect destination symbolic ref: {ref}")
    existing = _git(root, "show-ref", "--verify", "--quiet", ref, check=False)
    if existing.returncode == 0:
        raise RepairError(f"BRANCH_EXISTS: {ref}")
    if existing.returncode != 1:
        raise RepairError(f"Cannot inspect destination branch: {ref}")

    source_refs = {"base": base, "parent": parent, "head": head}
    resolved = {name: _resolve(root, value) for name, value in source_refs.items()}
    base_sha, parent_sha, head_sha = (resolved[key] for key in ("base", "parent", "head"))
    common = _git(root, "merge-base", "--all", base_sha, parent_sha, check=False)
    if common.returncode or len(common.stdout.splitlines()) != 1:
        raise RepairError("INVALID_BASE: base and parent must have exactly one common merge base")
    rows = (
        _git(root, "rev-list", "--reverse", "--parents", f"{parent_sha}..{head_sha}")
        .stdout.decode("ascii")
        .splitlines()
    )
    if len(rows) < 2:
        raise RepairError("INVALID_WINDOW: select at least two commits after parent")
    previous = parent_sha
    commits = []
    for row in rows:
        fields = row.split()
        if len(fields) != 2 or fields[1] != previous:
            raise RepairError(
                "NONLINEAR_WINDOW: every selected commit must have its predecessor as its sole parent"
            )
        previous = fields[0]
        commits.append(previous)
    if previous != head_sha:
        raise RepairError("INVALID_WINDOW: the selected window does not end at head")

    guard = _load_guard()
    blocking, _advisory, original_pairs = _findings(guard, root, base_sha, head_sha)
    shrinks = [finding for finding in blocking if finding.code == "JOURNAL_SHRANK"]
    if not shrinks:
        raise RepairError("NO_HISTORICAL_SHRINK: there is no JOURNAL_SHRANK to repair")
    unsupported = [
        finding
        for finding in blocking
        if finding.code != "JOURNAL_SHRANK"
        or finding.commit not in commits
        or finding.commit == head_sha
    ]
    if unsupported:
        raise RepairError("UNSUPPORTED_FAILURE: " + "\n".join(map(str, unsupported)))

    # Preserve every journal at the initial parent and every pre-shrink checkpoint.
    # A different journal can lose intervening entries while growing in byte length,
    # so the shrinking path alone does not describe the snapshots we must preserve.
    journal_paths = guard.append_only_files()
    checkpoint_refs = {parent_sha} | {finding.parent for finding in shrinks}
    checkpoints = {(checkpoint, path) for checkpoint in checkpoint_refs for path in journal_paths}
    for checkpoint, path in sorted(checkpoints):
        before = _git(root, "show", f"{checkpoint}:{path}").stdout
        after = _git(root, "show", f"{head_sha}:{path}").stdout
        _preserve_lines(before, after, path, checkpoint)

    tree = _git(root, "rev-parse", f"{head_sha}^{{tree}}").stdout.decode("ascii").strip()
    message = (
        "Repair restored append-only journal history\n\n"
        f"Preserve tree {tree} from {head_sha}.\n"
        f"Combine {len(commits)} commits after {parent_sha}; keep the source branch intact.\n\n"
        "Original commits:\n"
    ).encode()
    for commit in commits:
        message += (
            commit.encode("ascii")
            + b"\n"
            + _git(root, "show", "-s", "--format=%B", commit).stdout
            + b"\n"
        )
    alternate = Path(
        _git(root, "rev-parse", "--path-format=absolute", "--git-path", "objects")
        .stdout.decode("utf-8")
        .strip()
    )
    with tempfile.TemporaryDirectory(prefix="brain-journal-repair-") as temporary:
        objects = Path(temporary) / "objects"
        objects.mkdir()
        candidate = (
            _git(
                root,
                "commit-tree",
                tree,
                "-p",
                parent_sha,
                input=message,
                objects=objects,
                alternate=alternate,
            )
            .stdout.decode("ascii")
            .strip()
        )
        candidate_guard = _load_guard(objects=objects, alternate=alternate)
        remaining, advisory, candidate_pairs = _findings(candidate_guard, root, base_sha, candidate)
        if remaining:
            raise RepairError("CANDIDATE_REJECTED: " + "\n".join(map(str, remaining)))
        candidate_tree = (
            _git(root, "rev-parse", f"{candidate}^{{tree}}", objects=objects, alternate=alternate)
            .stdout.decode("ascii")
            .strip()
        )
        if candidate_tree != tree:
            raise RepairError("TREE_MISMATCH: candidate does not preserve the source tree")
        if apply:
            for name, original_ref in source_refs.items():
                if _resolve(root, original_ref) != resolved[name]:
                    raise RepairError(f"SOURCE_MOVED: {name} changed while preparing the repair")
            payload = _git(
                root, "cat-file", "commit", candidate, objects=objects, alternate=alternate
            ).stdout
            persisted = (
                _git(root, "hash-object", "-t", "commit", "-w", "--stdin", input=payload)
                .stdout.decode("ascii")
                .strip()
            )
            if persisted != candidate:
                raise RepairError(
                    "COMMIT_MISMATCH: persisted object differs from the validated candidate"
                )
            _create_branch(root, ref, candidate)

    return {
        "status": "created" if apply else "planned",
        **resolved,
        "tree": tree,
        "candidate": candidate,
        "candidate_persisted": apply,
        "branch": branch,
        "commits_squashed": len(commits),
        "shrinks_repaired": len(shrinks),
        "original_pairs": original_pairs,
        "candidate_pairs": candidate_pairs,
        "advisories": [str(finding) for finding in advisory],
        "applied": apply,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base", required=True, help="Current CI range base; must share one merge base with parent"
    )
    parser.add_argument(
        "--parent", required=True, help="Last preserved commit before the repair window"
    )
    parser.add_argument("--head", default="HEAD", help="Final, restored tree (default: HEAD)")
    parser.add_argument("--branch", required=True, help="New local branch name; must not exist")
    parser.add_argument("--apply", action="store_true", help="Create the validated new branch")
    args = parser.parse_args(argv)
    try:
        result = repair_history(root=ROOT, **vars(args))
    except (RepairError, OSError, UnicodeError) as exc:
        print(
            json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=True), file=sys.stderr
        )
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
