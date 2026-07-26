#!/usr/bin/env python3
"""Map changed repository paths to directly and transitively affected capabilities."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    caps = json.loads(REGISTRY.read_text(encoding="utf-8"))["capabilities"]
    direct = set()
    for c in caps:
        refs = set(
            c.get("services", [])
            + c.get("tests", [])
            + c.get("ui_consumers", [])
            + c.get("mobile_consumers", [])
        )
        refs |= {e["path"] for e in c.get("evidence", []) if e.get("type") == "repository"}
        for changed in a.paths:
            if any(
                changed == ref
                or changed.startswith(ref.rstrip("/") + "/")
                or ref.startswith(changed.rstrip("/") + "/")
                for ref in refs
            ):
                direct.add(c["id"])
                break
    dependents = defaultdict(list)
    for c in caps:
        for dep in c.get("dependencies", []):
            dependents[dep].append(c["id"])
    affected = set(direct)
    q = deque(direct)
    while q:
        x = q.popleft()
        for y in dependents[x]:
            if y not in affected:
                affected.add(y)
                q.append(y)
    payload = {
        "changed_paths": a.paths,
        "direct": sorted(direct),
        "transitive": sorted(affected - direct),
        "affected": sorted(affected),
    }
    print(json.dumps(payload, indent=2) if a.json else "\n".join(payload["affected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
