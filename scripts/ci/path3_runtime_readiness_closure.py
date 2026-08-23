#!/usr/bin/env python3
"""Close PATH-3 static runtime readiness without claiming live verification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "runtime-verification/generated/compose_runtime_targets.json"
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
OUT_JSON = ROOT / "governance/path3-generated/PATH3_RUNTIME_READINESS_CLOSURE.json"
OUT_MD = ROOT / "governance/path3-generated/PATH3_RUNTIME_READINESS_CLOSURE.md"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build() -> tuple[dict[str, Any], str]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    planned = sorted(row["service"] for row in plan["services"] if row.get("probes"))
    by_name = {row["service"]: row for row in targets["targets"]}
    missing = sorted(set(planned) - set(by_name))
    unresolved = sorted(name for name in planned if not by_name.get(name, {}).get("resolved"))
    fanout = {
        name: len(by_name[name].get("members", []))
        for name in planned
        if by_name.get(name, {}).get("members")
    }
    profiles = {
        name: by_name[name].get("profiles", [])
        for name in planned
        if by_name.get(name, {}).get("profiles")
    }
    checks = {
        "all_probeable_services_have_target_records": not missing,
        "all_target_records_resolved": not unresolved,
        "mcp_fanout_is_complete": fanout.get("mcp_servers") == 4,
        "model_registry_adapter_profile_is_explicit": "model-lifecycle"
        in profiles.get("model-registry-adapter", []),
        "target_plan_hash_matches": targets.get("source_plan_sha256") == plan.get("plan_sha256"),
        "resolver_remains_fail_closed": targets.get("fail_closed") is True,
        "no_runtime_truth_claimed": targets.get("runtime_verified") is False,
        "no_production_truth_claimed": targets.get("production_certified") is False,
    }
    closed = all(checks.values())
    core = {
        "schema_version": 1,
        "status": "READY_FOR_LIVE_EXECUTION" if closed else "BLOCKED_STATIC_READINESS",
        "closed": closed,
        "planned_services": len(planned),
        "resolved_services": len(planned) - len(unresolved),
        "missing_services": missing,
        "unresolved_services": unresolved,
        "fanout_targets": fanout,
        "required_profiles": profiles,
        "checks": checks,
        "runtime_verified_services": 0,
        "production_certified_services": 0,
    }
    payload = {**core, "closure_sha256": digest(core)}
    lines = [
        "# PATH-3 Runtime Readiness Closure",
        "",
        f"- Status: **{payload['status']}**",
        f"- Checks: **{sum(checks.values())}/{len(checks)} PASS**",
        f"- Compose-resolved probeable services: **{payload['resolved_services']}/{payload['planned_services']}**",
        f"- MCP deployments required: **{fanout.get('mcp_servers', 0)}**",
        "- Runtime verified services: **0**",
        "- Production certified services: **0**",
        "",
        "This closes static readiness only. Live Docker execution and valid evidence remain mandatory.",
    ]
    return payload, "\n".join(lines) + "\n"


def write() -> None:
    payload, report = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload, report = build()
    if args.generate:
        write()
    if args.check:
        if (
            not OUT_JSON.exists()
            or json.loads(OUT_JSON.read_text(encoding="utf-8")) != payload
            or not OUT_MD.exists()
            or OUT_MD.read_text(encoding="utf-8") != report
        ):
            print("PATH-3 runtime readiness closure drift")
            return 1
    passed = sum(payload["checks"].values())
    print(f"PATH-3 runtime readiness: {passed}/{len(payload['checks'])} PASS — {payload['status']}")
    return 0 if payload["closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
