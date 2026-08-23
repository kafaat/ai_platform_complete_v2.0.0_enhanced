#!/usr/bin/env python3
"""Fail-closed PR gate for capability lifecycle and evidence regressions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REG = "docs/capability-registry/generated/capability_registry.json"
WAIVER_RE = re.compile(r"(?im)^Capability-Regression-Waiver:\s*(\S.*?)\s*$")
PARITY = {
    "missing": 0,
    "behind": 1,
    "unassessed": 1,
    "parity": 2,
    "emerging_differentiator": 3,
    "leader": 4,
    "differentiator": 4,
}


def git_json(ref: str, path: str) -> dict[str, Any]:
    p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True, capture_output=True)
    if p.returncode:
        raise ValueError(f"cannot read {path} at {ref}: {p.stderr.strip()}")
    return json.loads(p.stdout)


def index(doc):
    return {c["id"]: c for c in doc.get("capabilities", [])}


def compare(base, head):
    b = index(base)
    h = index(head)
    changes = []
    for cid in sorted(set(b) - set(h)):
        changes.append({"capability_id": cid, "kind": "removed", "from": True, "to": False})
    for cid in sorted(set(b) & set(h)):
        x, y = b[cid], h[cid]
        for field in ("maturity", "evidence_level"):
            if int(y.get(field, 0)) < int(x.get(field, 0)):
                changes.append(
                    {
                        "capability_id": cid,
                        "kind": f"{field}_regression",
                        "from": x.get(field),
                        "to": y.get(field),
                    }
                )
        if bool(x.get("production_certified")) and not bool(y.get("production_certified")):
            changes.append(
                {
                    "capability_id": cid,
                    "kind": "production_certification_removed",
                    "from": True,
                    "to": False,
                }
            )
        px, py = (
            x.get("parity_classification", "unassessed"),
            y.get("parity_classification", "unassessed"),
        )
        if px != "unassessed" and py != "unassessed" and PARITY.get(py, 0) < PARITY.get(px, 0):
            changes.append(
                {"capability_id": cid, "kind": "parity_regression", "from": px, "to": py}
            )
        removed_deps = sorted(set(x.get("dependencies", [])) - set(y.get("dependencies", [])))
        if removed_deps:
            changes.append(
                {
                    "capability_id": cid,
                    "kind": "dependency_edges_removed",
                    "from": removed_deps,
                    "to": [],
                }
            )
    return changes


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--base-file")
    p.add_argument("--head-file")
    p.add_argument("--pr-body-file")
    p.add_argument("--output")
    a = p.parse_args(argv)
    try:
        base = (
            json.loads(Path(a.base_file).read_text(encoding="utf-8"))
            if a.base_file
            else git_json(a.base, REG)
        )
        head = (
            json.loads(Path(a.head_file).read_text(encoding="utf-8"))
            if a.head_file
            else git_json(a.head, REG)
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
    regressions = compare(base, head)
    body = Path(a.pr_body_file).read_text(encoding="utf-8") if a.pr_body_file else ""
    waiver = WAIVER_RE.search(body)
    waived = bool(waiver and waiver.group(1).strip().lower() not in ("none", "n/a"))
    result = {
        "schema_version": "1.0.0",
        "regressions": regressions,
        "waiver": waiver.group(1).strip() if waiver else None,
        "decision": "PASS" if not regressions or waived else "BLOCK",
    }
    if a.output:
        Path(a.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
