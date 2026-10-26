#!/usr/bin/env python3
"""Compare user-supplied frozen A/B results; never runs agents or promotes a skill.

Offline deterministic policy evaluator (stdlib). Evidence hashes are claims: the tool does
NOT fetch or independently authenticate the underlying result or grade.

Fixed candidate of the v4.3 script (gap UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01). The input
could satisfy the gates by itself: one task listed under several case IDs counted toward
``min_cases``; one evidence digest repeated across trials (or shared by the baseline and
candidate arms) counted toward ``min_trials_per_arm``; and a JSON key written twice was
read with its last value while a reviewer reads the first. Each is now refused. The
thresholds themselves still come from the policy file, by design (EVALUATION_POLICY.md).
The command-line interface and exit codes are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HEX = set("0123456789abcdef")


def _no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(
                f"duplicate JSON key {key!r}: the file reads differently to a reviewer"
            )
        obj[key] = value
    return obj


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)


def is_sha(x):
    return isinstance(x, str) and len(x) == 64 and all(c in HEX for c in x)


def canonical(data):
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def check_number(x, lo=0, hi=1):
    return (
        isinstance(x, (float, int))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and lo <= x <= hi
    )


def compare(data, policy):
    if not isinstance(data, dict) or data.get("schema") != "uwrp.skill-ab-results.v1":
        raise ValueError("results schema mismatch")
    for k in ("baseline_skill_sha256", "candidate_skill_sha256", "dataset_sha256"):
        if not is_sha(data.get(k)):
            raise ValueError(f"bad {k}")
    if data["baseline_skill_sha256"] == data["candidate_skill_sha256"]:
        raise ValueError("baseline and candidate have identical hashes: no A/B change")
    context = data.get("context")
    if not isinstance(context, dict) or set(context) != {
        "agent_family",
        "model",
        "toolset_digest",
        "environment_digest",
    }:
        raise ValueError("shared frozen context required")
    if (
        not isinstance(context["agent_family"], str)
        or not isinstance(context["model"], str)
        or not context["model"]
    ):
        raise ValueError("agent/model must be explicit")
    if not is_sha(context["toolset_digest"]) or not is_sha(context["environment_digest"]):
        raise ValueError("context digests required")
    provenance = data.get("measurement_origin")
    if provenance not in ("synthetic", "reported_real"):
        raise ValueError("measurement origin must be synthetic or reported_real")
    if data.get("grader") not in ("human", "deterministic", "model"):
        raise ValueError("grader type required")
    if type(data.get("blind")) is not bool:
        raise ValueError("blind must be boolean")
    if not isinstance(policy, dict) or policy.get("schema") != "uwrp.skill-ab-policy.v1":
        raise ValueError("policy schema mismatch")
    for k in ("min_cases", "min_trials_per_arm"):
        if type(policy.get(k)) is not int or policy[k] < 2:
            raise ValueError(f"{k} must be integer >=2")
    for k in ("min_mean_gain", "max_case_regression", "max_mean_cost_increase_ratio"):
        if not check_number(policy.get(k)):
            raise ValueError(f"{k} must be a finite 0..1 number")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) < policy["min_cases"]:
        raise ValueError("missing or insufficient A/B cases")
    case_ids, task_digests, evidence_digests, observations = set(), set(), set(), []
    all_base, all_cand, all_base_cost, all_cand_cost = [], [], [], []
    any_unsafe, any_regression, n_critical_regression = False, False, 0
    for row in cases:
        if not isinstance(row, dict) or set(row) != {
            "case_id",
            "task_digest",
            "critical",
            "baseline",
            "candidate",
        }:
            raise ValueError("unexpected case fields")
        cid = row["case_id"]
        if not isinstance(cid, str) or not cid or cid in case_ids or not is_sha(row["task_digest"]):
            raise ValueError("duplicate/invalid case ID or task hash")
        case_ids.add(cid)
        if row["task_digest"] in task_digests:
            raise ValueError(f"{cid}: task digest repeats another case (one task is one case)")
        task_digests.add(row["task_digest"])
        if type(row["critical"]) is not bool:
            raise ValueError("critical must be boolean")
        seen_trials = set()
        for arm in ("baseline", "candidate"):
            trials = row.get(arm)
            if not isinstance(trials, list) or len(trials) < policy["min_trials_per_arm"]:
                raise ValueError(f"{cid} {arm}: insufficient trials")
            for t in trials:
                if not isinstance(t, dict) or set(t) != {
                    "trial_id",
                    "quality",
                    "cost_units",
                    "safety_violation",
                    "evidence_digest",
                }:
                    raise ValueError("invalid trial fields")
                if (
                    not isinstance(t["trial_id"], str)
                    or not t["trial_id"]
                    or t["trial_id"] in seen_trials
                ):
                    raise ValueError(f"{cid}: duplicate trial identifier")
                seen_trials.add(t["trial_id"])
                if not check_number(t["quality"]) or not check_number(t["cost_units"], 0, 10**9):
                    raise ValueError(f"{cid}: invalid quality/cost")
                if type(t["safety_violation"]) is not bool or not is_sha(t["evidence_digest"]):
                    raise ValueError(f"{cid}: invalid safety/evidence")
                if t["evidence_digest"] in evidence_digests:
                    raise ValueError(
                        f"{cid}: evidence digest reused (each trial needs its own evidence)"
                    )
                evidence_digests.add(t["evidence_digest"])
                any_unsafe |= t["safety_violation"]
        b = sum(t["quality"] for t in row["baseline"]) / len(row["baseline"])
        c = sum(t["quality"] for t in row["candidate"]) / len(row["candidate"])
        bc = sum(t["cost_units"] for t in row["baseline"]) / len(row["baseline"])
        cc = sum(t["cost_units"] for t in row["candidate"]) / len(row["candidate"])
        regression = c < b - policy["max_case_regression"] - 1e-12
        any_regression |= regression
        if regression and row["critical"]:
            n_critical_regression += 1
        all_base.append(b)
        all_cand.append(c)
        all_base_cost.append(bc)
        all_cand_cost.append(cc)
        observations.append(
            {
                "case_id": cid,
                "critical": row["critical"],
                "baseline_quality": round(b, 6),
                "candidate_quality": round(c, 6),
                "gain": round(c - b, 6),
                "regression": regression,
            }
        )
    mean_b = sum(all_base) / len(all_base)
    mean_c = sum(all_cand) / len(all_cand)
    base_cost = sum(all_base_cost) / len(all_base_cost)
    cand_cost = sum(all_cand_cost) / len(all_cand_cost)
    cost_ratio = (
        (cand_cost - base_cost) / base_cost
        if base_cost > 0
        else (0 if cand_cost == 0 else math.inf)
    )
    gain = mean_c - mean_b
    concerns = []
    if any_unsafe:
        concerns.append("safety_violation_in_one_or_both_arms")
    if any_regression:
        concerns.append("per_case_quality_regression")
    if gain + 1e-12 < policy["min_mean_gain"]:
        concerns.append("insufficient_quality_gain")
    if cost_ratio > policy["max_mean_cost_increase_ratio"] + 1e-12:
        concerns.append("cost_increase_above_limit")
    if not data["blind"]:
        concerns.append("unblinded_grading")
    eligible = not concerns and provenance == "reported_real"
    # This report is conditional on supplied data; no acceptance or automated promotion.
    status = (
        "REPORTED_REVIEW_CANDIDATE"
        if eligible
        else ("SANDBOX_ONLY" if provenance == "synthetic" else "DO_NOT_PROMOTE")
    )
    return {
        "schema": "uwrp.skill-ab-report.v1",
        "status": status,
        "adoption_authorized": False,
        "data_authenticity_verified": False,
        "measurement_origin": provenance,
        "case_count": len(observations),
        "mean_quality_baseline": round(mean_b, 6),
        "mean_quality_candidate": round(mean_c, 6),
        "mean_gain": round(gain, 6),
        "mean_cost_increase_ratio": None if not math.isfinite(cost_ratio) else round(cost_ratio, 6),
        "safety_violation_present": any_unsafe,
        "critical_regressions": n_critical_regression,
        "concerns": concerns,
        "case_results": observations,
        "results_digest": digest(data),
        "policy_digest": digest(policy),
        "next_gate": "Independent trace audit, human authority, and a reversible pilot are required.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--policy", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        d = load_json(a.results)
        policy = load_json(a.policy)
        report = compare(d, policy)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "REPORTED_REVIEW_CANDIDATE" else 3
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
