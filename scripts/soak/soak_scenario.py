#!/usr/bin/env python3
"""Generate deterministic 7-14 day soak test scenarios for Sahool."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SoakScenario:
    tenants: int
    fields: int
    duration_days: int
    field_ops_per_minute: int
    raster_ops_per_minute: int
    ai_ops_per_minute: int
    mobile_sync_ops_per_minute: int
    chaos_interval_minutes: int
    replay_interval_minutes: int


def build_scenario(tenants: int, fields: int, days: int) -> SoakScenario:
    tenants = max(1, tenants)
    fields = max(1, fields)
    return SoakScenario(
        tenants=tenants,
        fields=fields,
        duration_days=days,
        field_ops_per_minute=max(10, tenants // 2),
        raster_ops_per_minute=max(20, fields // 1000),
        ai_ops_per_minute=max(5, tenants // 10),
        mobile_sync_ops_per_minute=max(10, tenants // 5),
        chaos_interval_minutes=120,
        replay_interval_minutes=60,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenants", type=int, default=1000)
    p.add_argument("--fields", type=int, default=100000)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    print(
        json.dumps(
            asdict(build_scenario(args.tenants, args.fields, args.days)), indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
