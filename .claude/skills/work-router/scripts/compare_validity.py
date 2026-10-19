#!/usr/bin/env python3
"""Compare declared receipt contexts; never performs actions or declares test PASS."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED = ("inputs_digest", "command_digest")
GIT = ("source_head", "source_tree", "base_head", "merge_base")
ENV = ("environment_digest",)
FLAGS = ("requires_git", "requires_environment", "has_volatile_external_inputs")


def compare(previous: dict, current: dict) -> dict:
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ValueError("contexts must be objects")
    for f in FLAGS:
        if not isinstance(previous.get(f), bool) or not isinstance(current.get(f), bool):
            raise ValueError(f"missing or invalid boolean flag {f}")
    keys = list(REQUIRED)
    if previous["requires_git"] or current["requires_git"]:
        keys += list(GIT)
    if previous["requires_environment"] or current["requires_environment"]:
        keys += list(ENV)
    differences = [f for f in FLAGS if previous[f] != current[f]]
    unknown = []
    for key in keys:
        a, b = previous.get(key), current.get(key)
        if not isinstance(a, str) or not a.strip() or not isinstance(b, str) or not b.strip():
            unknown.append(key)
        elif a != b:
            differences.append(key)
    if differences:
        status = "STALE"
    elif unknown:
        status = "UNKNOWN"
    elif previous["has_volatile_external_inputs"] or current["has_volatile_external_inputs"]:
        status = "EXTERNAL_RECHECK_REQUIRED"
    else:
        status = "CONTEXT_MATCH_ONLY"
    return {
        "status": status,
        "changed_fields": sorted(set(differences)),
        "missing_or_unknown_fields": sorted(set(unknown)),
        "can_claim_test_pass": False,
        "can_auto_retry_external_effect": False,
        "note": "Matching context is not proof that a receipt exists or a project gate passed. External state must be freshly checked.",
    }


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--previous",required=True,type=Path)
    ap.add_argument("--current",required=True,type=Path)
    x=ap.parse_args()
    try:
        result=compare(json.loads(x.previous.read_text(encoding='utf-8')),json.loads(x.current.read_text(encoding='utf-8')))
    except (OSError,ValueError,json.JSONDecodeError) as e:
        ap.error(str(e))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
