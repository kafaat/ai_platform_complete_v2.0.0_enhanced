#!/usr/bin/env python3
"""Compare two capability registries and emit a release intelligence report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["capabilities"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--output")
    a = p.parse_args()
    before, after = load(a.before), load(a.after)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    improved = []
    regressed = []
    changed = []
    for cid in sorted(set(before) & set(after)):
        b, x = before[cid], after[cid]
        if b == x:
            continue
        changed.append(cid)
        delta = x["maturity"] - b["maturity"]
        if delta > 0:
            improved.append({"id": cid, "from": b["maturity"], "to": x["maturity"]})
        elif delta < 0:
            regressed.append({"id": cid, "from": b["maturity"], "to": x["maturity"]})
    report = {
        "added": added,
        "removed": removed,
        "changed": changed,
        "improved": improved,
        "regressed": regressed,
        "risk": "BLOCK" if removed or regressed else "PASS",
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 1 if report["risk"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
