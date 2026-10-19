#!/usr/bin/env python3
"""Deterministic duration-aware shard planner; does not execute tests."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def assign(data: dict, num_shards: int) -> list[dict]:
    if num_shards < 1:
        raise ValueError("num_shards must be positive")
    if data.get("schema") != "ata/durations/v1":
        raise ValueError("Expected ata/durations/v1")
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("groups must be a nonempty array")
    affinities: dict[str, list] = defaultdict(list)
    ids = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("group must be object")
        identifier, seconds = group.get("id"), group.get("seconds")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ValueError("Invalid or duplicate group id")
        if not isinstance(seconds, (float, int)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("durations must be positive finite numbers")
        ids.add(identifier)
        key = group.get("affinity", identifier)
        if not isinstance(key, str) or not key:
            raise ValueError("affinity must be nonempty string")
        affinities[key].append(group)
    jobs = [(key, sum(float(g["seconds"]) for g in members), members) for key, members in affinities.items()]
    jobs.sort(key=lambda x: (-x[1], x[0]))
    shards = [{"shard": i + 1, "estimated_seconds": 0.0, "groups": []} for i in range(num_shards)]
    for _, seconds, members in jobs:
        target = min(shards, key=lambda s: (s["estimated_seconds"], s["shard"]))
        target["estimated_seconds"] += seconds
        target["groups"].extend(sorted((g["id"] for g in members)))
    for shard in shards:
        shard["estimated_seconds"] = round(shard["estimated_seconds"], 3)
    return shards


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--durations", type=Path, required=True)
    p.add_argument("--shards", type=int, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    planned = assign(json.loads(args.durations.read_text(encoding="utf-8")), args.shards)
    payload = {"schema": "ata/shard-assignment/v1", "planner": "LPT groups with affinity preserved",
               "shards": planned, "note": "Estimate only; not executed; confirm test independence and resource limits"}
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
