#!/usr/bin/env python3
"""Read-only, source-derived GitHub Actions inventory. Never infer required status checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
COMMAND_PATTERN = re.compile(r"(?:pytest|ruff|mypy|vitest|playwright|flutter|npm|pnpm|yarn|python|bash|sh|docker|helm|trivy|bandit|pip-audit|mutmut|crosshair)", re.I)
TEST_PATTERN = re.compile(r"(?:^|[\s'\"=])((?:tests|tests_v9|services)/[\w./-]*test[\w./-]*\.py)")

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()

def parse_workflow(raw: bytes) -> dict:
    # BaseLoader prevents PyYAML's YAML-1.1 conversion of the GitHub 'on' key to True.
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required; refusing partial/regex-only YAML parsing") from exc
    data = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(data, dict):
        raise ValueError("workflow must be a mapping")
    jobs = data.get("jobs", {})
    if not isinstance(jobs, dict):
        raise ValueError("jobs must be a mapping")
    return data

def inventory(root: Path) -> dict:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir() or workflow_dir.is_symlink():
        raise ValueError("missing or symlinked .github/workflows")
    files = sorted(p for p in workflow_dir.iterdir() if p.suffix in (".yml", ".yaml"))
    if not files:
        raise ValueError("no workflow files")
    workflows = []
    for path in files:
        if not regular_file(path) or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"invalid workflow file: {path.name}")
        raw = path.read_bytes()
        document = parse_workflow(raw)
        jobs = document.get("jobs", {})
        rows = []
        for job_id, job in sorted(jobs.items()):
            if not isinstance(job, dict):
                raise ValueError(f"invalid job {job_id} in {path.name}")
            steps = job.get("steps", [])
            if steps is None:
                steps = []
            if not isinstance(steps, list):
                raise ValueError(f"invalid steps in {path.name}:{job_id}")
            commands = []
            tests = set()
            for step in steps:
                if not isinstance(step, dict):
                    raise ValueError(f"invalid step in {path.name}:{job_id}")
                command = step.get("run")
                if command is not None:
                    if not isinstance(command, str):
                        raise ValueError("run must be a string")
                    commands.append({"name": step.get("name", ""), "run": command,
                                     "test_paths": sorted(set(TEST_PATTERN.findall(command))),
                                     "tool_hints": sorted(set(m.group(0).lower() for m in COMMAND_PATTERN.finditer(command)))})
                    tests.update(TEST_PATTERN.findall(command))
            rows.append({
                "id": job_id, "name": job.get("name", job_id),
                "needs": job.get("needs", []), "if": job.get("if"),
                "runs_on": job.get("runs-on"), "uses": job.get("uses"),
                "strategy": job.get("strategy"), "timeout_minutes": job.get("timeout-minutes"),
                "commands": commands, "explicit_test_paths": sorted(tests),
            })
        triggers = document.get("on", {})
        workflows.append({"path": path.relative_to(root).as_posix(), "sha256": digest(raw),
                          "name": document.get("name", path.stem), "on": triggers,
                          "permissions": document.get("permissions"), "concurrency": document.get("concurrency"),
                          "jobs": rows, "job_count": len(rows)})
    return {
        "schema_version": 1, "source": "repository_workflow_files",
        "scope": "static_workflow_inventory_not_required_check_authority",
        "workflow_count": len(workflows), "job_count": sum(x["job_count"] for x in workflows),
        "workflows": workflows,
        "limitations": [
            "No branch-protection or ruleset required-check status is inferred",
            "Reusable workflows and dynamic commands require transitive inspection",
            "Runtime matrix expansion, skip decisions and test discovery are not executed",
            "Job run history and durations are not included",
            "Tool hints are lexical only and do not prove execution or test coverage",
        ],
    }

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, help="Optional new JSON output; refuse overwrite")
    args = parser.parse_args(argv)
    try:
        result = inventory(args.root.resolve())
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            target = args.output.absolute()
            if target.exists() or target.is_symlink():
                raise ValueError("output already exists; refusing overwrite")
            if target.resolve().is_relative_to(args.root.resolve()):
                raise ValueError("output must be outside repository worktree")
            target.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0
    except (ValueError, RuntimeError, OSError, UnicodeError) as exc:
        print(f"CI_INVENTORY_BLOCKED: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
