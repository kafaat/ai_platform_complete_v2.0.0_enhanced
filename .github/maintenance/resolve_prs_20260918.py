"""One-shot candidate preparation; never updates main or an existing PR ref."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = "kafaat/ai_platform_complete_v2.0.0_enhanced"
EXPECTED = {
    "1021": ("45d5205ee7acb4e1a4d182d451dc26cb80cdc012", "codex/edge-model-artifact-digest-01"),
    "1023": ("e3e62de41b1dff00c92322157ceb5b0396407fa9", "fix/railway-migration-runner"),
}
MAIN = "3873838bbdc3cbcac6ba52ac6b0a7ca3f2ce991b"


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise SystemExit("wrong_repository")
    number = os.environ["PR_NUMBER"]
    if number != "1021":
        raise SystemExit("resume_scope_is_pr1021_only")
    head, branch = EXPECTED[number]
    if (os.environ["PR_SHA"], os.environ["PR_BRANCH"], os.environ["MAIN_SHA"]) != (head, branch, MAIN):
        raise SystemExit("unexpected_input_identity")
    source = Path.cwd()
    work = Path(os.environ["RUNNER_TEMP"]) / "candidate"
    evidence = Path(os.environ["RUNNER_TEMP"]) / "evidence"
    evidence.mkdir(exist_ok=True)

    def run(args: list[str], *, cwd: Path | None = None, capture: bool = False, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        print("+", " ".join(args), flush=True)
        result = subprocess.run(args, cwd=cwd or work, text=True, stdout=subprocess.PIPE if capture else None, stderr=None, timeout=2700, check=False)
        if result.returncode not in allowed:
            raise SystemExit(f"command_failed:{result.returncode}:{args[0]}")
        return result

    def remote_sha(ref: str) -> str:
        text = run(["git", "ls-remote", "--exit-code", "origin", ref], cwd=source, capture=True).stdout.strip()
        rows = text.splitlines()
        if len(rows) != 1:
            raise SystemExit("ambiguous_remote_ref")
        return rows[0].split()[0]

    if remote_sha("refs/heads/main") != MAIN or remote_sha("refs/heads/" + branch) != head:
        raise SystemExit("remote_moved_before_preparation")
    run(["git", "worktree", "add", "--detach", str(work), head], cwd=source)
    run(["git", "config", "user.name", "SAHOOL conflict resolution"])
    run(["git", "config", "user.email", "noreply@openai.com"])
    run(["git", "merge", "--no-ff", "--no-commit", MAIN], allowed=(0, 1))
    conflicts = run(["git", "diff", "--name-only", "--diff-filter=U"], capture=True).stdout.splitlines()
    (evidence / "initial_conflicts.json").write_text(json.dumps(conflicts, indent=2) + "\n")
    import hashlib
    patch = Path(os.environ["RUNNER_TEMP"]) / "restored" / "worktree.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != "8c957b93ed96a6cd5d1629acf33d1504c816f3ed0cae72392b9764a90a40c8fd":
        raise SystemExit("regenerated_patch_digest_mismatch")
    # Restore the reviewed old-head base without clearing the merge's second parent,
    # then replay the exact generated worktree recovered from the first attempt.
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "--", "."])
    if run(["git", "rev-parse", "--verify", "MERGE_HEAD"], capture=True).stdout.strip() != MAIN:
        raise SystemExit("merge_parent_lost")
    run(["git", "apply", "--index", "--whitespace=nowarn", str(patch)])
    if run(["git", "diff", "--name-only", "--diff-filter=U"], capture=True).stdout.strip():
        raise SystemExit("replayed_patch_left_conflicts")
    run(["ruff", "check", "."])
    run(["ruff", "format", "--check", "."])
    run([sys.executable, "scripts/ci/verify_all_generated.py", "--check"])
    run(["git", "add", "-A"])
    run(["git", "-c", "core.whitespace=cr-at-eol", "diff", "--cached", "--check"])
    run(["git", "commit", "-m", f"fix(ci): reconcile PR #{number} with current main and regenerate owned artifacts"])
    run(["bash", "scripts/ci/preflight.sh", "--fast"])
    run([sys.executable, "-m", "pytest", "-q", "-m", "unit", "--cov=services", "--cov-report=xml:" + str(evidence / "coverage.xml"), "--cov-fail-under=43", "--junitxml=" + str(evidence / "unit.xml")])
    ignores = run([sys.executable, "scripts/ci/tests_tree_coverage_guard.py", "--pytest-ignores"], capture=True).stdout.split()
    run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", *ignores, "--junitxml=" + str(evidence / "repository.xml")])
    run([sys.executable, "scripts/ci/verify_all_generated.py", "--check"])
    run([sys.executable, "scripts/release/validate_release_package.py", "--root", "."])
    if run(["git", "status", "--porcelain=v1", "--untracked-files=no"], capture=True).stdout.strip():
        raise SystemExit("tests_modified_tracked_source")
    sha = run(["git", "rev-parse", "HEAD"], capture=True).stdout.strip()
    tree = run(["git", "rev-parse", "HEAD^{tree}"], capture=True).stdout.strip()
    (evidence / "resolved.diff").write_text(run(["git", "diff", MAIN, "HEAD"], capture=True).stdout)
    changed_paths = run(["git", "diff", MAIN, "HEAD", "--name-only"], capture=True).stdout.splitlines()
    (evidence / "capability_impact.json").write_text(run([sys.executable, "scripts/ci/capability_impact.py", "--json", *changed_paths], capture=True).stdout)
    if remote_sha("refs/heads/main") != MAIN or remote_sha("refs/heads/" + branch) != head:
        raise SystemExit("remote_moved_before_candidate_publish")
    destination = f"refs/heads/ops/resolved-pr{number}-20260918"
    # New candidate ref only. The connector will fast-forward the PR after review.
    run(["git", "push", "origin", f"{sha}:{destination}"])
    (evidence / "result.json").write_text(json.dumps({"pr": int(number), "old_head": head, "main": MAIN, "candidate": sha, "tree": tree, "destination": destination, "status": "local_checks_passed_not_merged"}, indent=2) + "\n")
    print("CANDIDATE_READY", sha, tree, flush=True)


if __name__ == "__main__":
    main()
