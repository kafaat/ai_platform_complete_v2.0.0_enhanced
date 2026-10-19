#!/usr/bin/env python3
"""Read-only conservative CPU/memory/disk profile and safe starting worker suggestion."""
from __future__ import annotations
import argparse
import json
import math
import os
import shutil
from pathlib import Path


def read_int(path: str):
    try:
        s = Path(path).read_text().strip()
        return None if s == "max" else int(s)
    except (ValueError, OSError):
        return None


def cpu_budget() -> int:
    n = os.cpu_count() or 1
    if hasattr(os, "sched_getaffinity"):
        try:
            n = min(n, len(os.sched_getaffinity(0)))
        except OSError:
            pass
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            n = min(n, max(1, math.floor(int(quota) / int(period))))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    return max(1, n)


def memory_budget_bytes():
    cgroup_limit = read_int("/sys/fs/cgroup/memory.max")
    mem_avail = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) * 1024
                break
    except OSError:
        pass
    cgroup_current = read_int("/sys/fs/cgroup/memory.current")
    cgroup_free = (cgroup_limit - cgroup_current) if cgroup_limit is not None and cgroup_current is not None else None
    candidates = [max(0, n) for n in (mem_avail, cgroup_free) if n is not None]
    return min(candidates) if candidates else None


def profile(path: Path, worker_memory_gib: float = 1.0, worker_disk_gib: float = 1.0) -> dict:
    if (not math.isfinite(worker_memory_gib) or not math.isfinite(worker_disk_gib)
            or worker_memory_gib <= 0 or worker_disk_gib <= 0):
        raise ValueError("Per-worker memory and disk estimates must be finite, positive numbers")
    free_disk = shutil.disk_usage(path).free
    free_mem = memory_budget_bytes()
    mem_bound = int(free_mem / (worker_memory_gib * 1024**3)) if free_mem is not None else 1
    disk_bound = int(max(0, free_disk - 2 * 1024**3) / (worker_disk_gib * 1024**3))
    recommended = max(0, min(cpu_budget(), mem_bound, disk_bound, 4))
    return {"schema": "ata/resources/v1", "cpu_effective_cores": cpu_budget(),
            "memory_free_estimate_bytes": free_mem, "disk_free_bytes": free_disk,
            "starting_workers": recommended,
            "can_start_by_budget": recommended >= 1,
            "requires_review": True,
            "note": "Heuristic only; zero means insufficient estimated resources. DB-exclusive tests start at one worker; verify measured RSS, disk/IO and fixture cost."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path.cwd())
    parser.add_argument("--mem-gib", type=float, default=1.0)
    parser.add_argument("--disk-gib", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(profile(args.path, args.mem_gib, args.disk_gib), indent=2))


if __name__ == "__main__":
    main()
