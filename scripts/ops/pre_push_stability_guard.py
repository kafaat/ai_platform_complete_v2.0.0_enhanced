#!/usr/bin/env python3
"""Fail-closed guard for staging/pushing from a stable SAHOOL worktree.

Checks repository contamination (temporary probes, bytecode/cache artifacts),
worktree stability, and—unless disabled—concurrent processes known to mutate
source/generated artifacts. It never modifies the tree.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_MUTATOR_MARKERS = (
    "verify_all_generated.py --fix",
    "verify_all_generated --fix",
    "build_release_bundle.py",
    "platform_route_budget_guard.py --write",
    "platform_route_release_binding.py --write",
    "pytest",
)
_PROBE_NAME_MARKERS = ("probe_unadjudicated", "_probe_")
_CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_CACHE_SUFFIXES = {".pyc", ".pyo"}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, timeout=30)


def _tracked_files() -> list[str]:
    proc = _git("ls-files", "-z")
    if proc.returncode != 0:
        return []
    return [item for item in proc.stdout.split("\0") if item]


def contamination() -> list[str]:
    problems: list[str] = []
    tracked = _tracked_files()
    candidates = [ROOT / rel for rel in tracked] if tracked else list(ROOT.rglob("*"))

    for path in candidates:
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        parts = set(path.parts)
        if any(cache in parts for cache in _CACHE_DIRS) or path.suffix in _CACHE_SUFFIXES:
            problems.append(f"cache/bytecode artifact: {rel}")
        if path.is_file() and any(marker in path.name for marker in _PROBE_NAME_MARKERS):
            # Only executable platform router probes are forbidden by name. Runtime probe
            # plans and tests legitimately use "probe" terminology.
            if rel.startswith("services/sahool-platform/api/routers/"):
                problems.append(f"temporary probe router: {rel}")
        if path.is_file() and rel.startswith("services/sahool-platform/api/routers/"):
            try:
                header = path.read_text(encoding="utf-8", errors="ignore")[:1000]
            except OSError:
                header = ""
            if "must never be tracked" in header or "مِسبار اختبار مؤقّت — غير متعقَّب" in header:
                problems.append(f"tracked temporary-test artifact: {rel}")
    return sorted(set(problems))


def active_mutators() -> list[str]:
    proc = subprocess.run(["ps", "-eo", "pid=,args="], text=True, capture_output=True, timeout=15)
    if proc.returncode != 0:
        return ["could not inspect process table"]
    own_pid = os.getpid()
    parent_pid = os.getppid()
    found: list[str] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            pid_text, args = line.split(maxsplit=1)
            pid = int(pid_text)
        except (ValueError, IndexError):
            continue
        if pid in {own_pid, parent_pid} or "pre_push_stability_guard.py" in args:
            continue
        if any(marker in args for marker in _MUTATOR_MARKERS):
            found.append(f"pid={pid} {args}")
    return found


def worktree_snapshot() -> str:
    proc = _git("status", "--porcelain=v1", "--untracked-files=all")
    if proc.returncode != 0:
        return ""
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-process-check", action="store_true", help="for CI/containers")
    parser.add_argument(
        "--allow-dirty", action="store_true", help="validate stability, not cleanliness"
    )
    parser.add_argument("--stability-delay", type=float, default=2.0)
    args = parser.parse_args()

    problems = contamination()
    if not args.skip_process_check:
        problems.extend(f"active mutator: {item}" for item in active_mutators())

    first = worktree_snapshot()
    time.sleep(max(0.0, args.stability_delay))
    second = worktree_snapshot()
    if first != second:
        problems.append("worktree changed during stability window")
    if first and not args.allow_dirty:
        problems.append(
            "worktree is dirty; stage/commit only after generation and verification finish"
        )

    if problems:
        print("pre_push_stability_guard: FAIL")
        for problem in sorted(set(problems)):
            print(f"  - {problem}")
        return 1
    print("pre_push_stability_guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
