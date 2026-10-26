#!/usr/bin/env python3
"""Derive which Railway services a change redeploys, from the committed watch patterns.

PR-DEPLOY-EFFECT-CLAIM-NOT-DERIVED-FROM-WATCH-PATTERNS-01. The deploy effect of a PR
was written by hand. #1285 said its merge redeploys the gateway alone; Railway then
redeployed auth-main, soil and vegetation as well, because test files under their
service folders match their watch patterns. Under the freeze the owner decides merges
on that line, so it is derived here from the patterns Railway actually holds.

The patterns live in Railway, not in the repository. They are captured read-only into
``docs/architecture/railway_watch_patterns.json``; ``--compare`` reports drift between
that file and a fresh capture. The answer is only as current as the capture, and the
output says how old it is.

Railway watch paths are gitignore-style and relative to the repository root; a push
that matches none of a service's patterns skips that service. Only services that
deploy from ``main`` without a pinned commit are triggered by a merge; others are
listed apart.

Not a gate: it prints, and exits 0 unless the input is unusable or ``--compare`` finds
drift.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "architecture" / "railway_watch_patterns.json"
MERGE_BRANCH = "main"
# A merge that rebuilds the migrator can apply migrations to the live database.
MIGRATOR_SERVICES = frozenset({"sahool-migrate-main"})


@cache
def _compile(pattern: str) -> tuple[re.Pattern[str], bool]:
    """Translate one gitignore-style pattern into a regex over repo-relative POSIX paths."""
    negate = pattern.startswith("!")
    body = pattern[1:] if negate else pattern
    dir_only = body.endswith("/")
    body = body.strip("/") if dir_only else body
    # A slash anywhere but the end anchors the pattern at the root; otherwise it
    # matches at any depth.
    anchored = "/" in body
    body = body.lstrip("/")
    out = []
    i = 0
    while i < len(body):
        if body.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif body.startswith("**", i):
            out.append(".*")
            i += 2
        elif body[i] == "*":
            out.append("[^/]*")
            i += 1
        elif body[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(body[i]))
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    # A pattern that names a directory covers everything below it; a directory-only
    # pattern covers nothing but what is below it.
    suffix = "/.+" if dir_only else "(?:/.+)?"
    return re.compile(f"^{prefix}{''.join(out)}{suffix}$"), negate


def matches(path: str, patterns: list[str]) -> bool:
    """gitignore order: the last pattern that matches decides, ``!`` re-includes."""
    path = path.replace("\\", "/").lstrip("/")
    hit = False
    for pattern in patterns:
        regex, negate = _compile(pattern)
        if regex.match(path):
            hit = not negate
    return hit


def load_snapshot(path: Path = SNAPSHOT) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for svc in data.get("services", []):
        patterns = svc.get("watch_patterns")
        if not patterns:
            # Railway rebuilds on every push when a service has no watch paths; the
            # snapshot must say so explicitly rather than leave it to a default here.
            raise ValueError(
                f"{svc.get('environment')}/{svc.get('service')}: no watch_patterns in snapshot"
            )
    return data


def impact(paths: list[str], snapshot: dict) -> dict:
    triggered: dict[str, list[dict]] = {}
    other_branch: list[dict] = []
    for svc in snapshot["services"]:
        hits = [p for p in paths if matches(p, svc["watch_patterns"])]
        if not hits:
            continue
        entry = {"service": svc["service"], "branch": svc["branch"], "paths": hits}
        if svc.get("pinned_commit"):
            # Measured: staging tts-service is pinned to d301c136 with branch main and
            # has had no deployment since 2026-10-17, through every later main merge
            # that touched /shared/**. A pinned service does not follow the branch.
            entry["pinned_commit"] = svc["pinned_commit"]
            other_branch.append({"environment": svc["environment"], **entry})
        elif svc["branch"] == MERGE_BRANCH:
            triggered.setdefault(svc["environment"], []).append(entry)
        else:
            other_branch.append({"environment": svc["environment"], **entry})
    migrator = sorted(
        {
            f"{env}/{e['service']}"
            for env, items in triggered.items()
            for e in items
            if e["service"] in MIGRATOR_SERVICES
        }
    )
    return {"triggered": triggered, "other_branch": other_branch, "migrator": migrator}


def deploy_effect_line(result: dict) -> str:
    parts = [
        f"{env}[{','.join(sorted(e['service'] for e in items))}]"
        for env, items in sorted(result["triggered"].items())
    ]
    return "Deploy-Effect: " + (" ".join(parts) if parts else "NONE")


def snapshot_age_days(snapshot: dict, now: datetime | None = None) -> float:
    captured = datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00"))
    return ((now or datetime.now(UTC)) - captured).total_seconds() / 86400


def compare(old: dict, new: dict) -> list[str]:
    """Differences that change the answer: services added/removed, branch or patterns changed."""

    def index(snap: dict) -> dict:
        return {
            (s["environment"], s["service"]): (
                s["branch"],
                tuple(s["watch_patterns"] or ()),
                s.get("pinned_commit"),
            )
            for s in snap["services"]
        }

    a, b = index(old), index(new)
    drift = [f"removed: {env}/{svc}" for env, svc in sorted(a.keys() - b.keys())]
    drift += [f"added: {env}/{svc}" for env, svc in sorted(b.keys() - a.keys())]
    for key in sorted(a.keys() & b.keys()):
        if a[key] != b[key]:
            drift.append(f"changed: {key[0]}/{key[1]}: {a[key]} -> {b[key]}")
    return drift


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="changed paths (default: git diff BASE...HEAD)")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--compare", type=Path, metavar="NEW_SNAPSHOT", help="report drift against a fresh capture"
    )
    args = ap.parse_args(argv)

    snapshot = load_snapshot(args.snapshot)
    if args.compare:
        drift = compare(snapshot, load_snapshot(args.compare))
        for line in drift:
            print(line)
        print(f"railway_deploy_impact: {'DRIFT' if drift else 'no drift'} ({len(drift)})")
        return 1 if drift else 0

    paths = args.paths or changed_paths(args.base, args.head)
    result = impact(paths, snapshot)
    age = snapshot_age_days(snapshot)
    if args.json:
        print(
            json.dumps(
                {**result, "snapshot_captured_at": snapshot["captured_at"], "paths": len(paths)},
                indent=2,
            )
        )
        return 0

    print(deploy_effect_line(result))
    for env, items in sorted(result["triggered"].items()):
        for e in sorted(items, key=lambda x: x["service"]):
            print(
                f"  {env}/{e['service']}: {', '.join(e['paths'][:3])}{' …' if len(e['paths']) > 3 else ''}"
            )
    for e in result["other_branch"]:
        source = (
            f"pinned commit {e['pinned_commit'][:9]}" if e.get("pinned_commit") else e["branch"]
        )
        print(
            f"  not triggered by a {MERGE_BRANCH} merge: {e['environment']}/{e['service']} deploys from {source}"
        )
    if result["migrator"]:
        print(
            f"  ⚠ MIGRATOR would rebuild: {', '.join(result['migrator'])} — migrations can reach the live database"
        )
    print(
        f"  watch patterns captured {snapshot['captured_at']} ({age:.0f} days ago); refresh: see {SNAPSHOT.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
