#!/usr/bin/env python3
"""Check a work contract and measure its evidence closure. Standard library only; read-only.

  check_contract.py CONTRACT.json [--require-closure RATIO] [--json]

Exit 0: the contract is consistent (and closure >= RATIO when given).
Exit 1: violations found, or closure below RATIO.
Exit 2: the file is unreadable or not a contract.

What is checked (each one turns an instruction into something a machine can refuse):
  - every requirement has an acceptance condition and an evidence type
  - VERIFIED requires at least one evidence item; PASS evidence needs an exit code or a ref
  - task -> requirement and task -> task references resolve; no dependency cycles
  - no two tasks are writer of the same resource
  - status values come from the published vocabulary
Closure = VERIFIED requirements / all requirements. It measures recorded evidence, not truth:
the evidence itself still has to be inspected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQ_STATUS = {"NOT_STARTED", "IN_PROGRESS", "VERIFIED", "PARTIAL", "BLOCKED", "UNKNOWN"}
TASK_STATUS = {"PENDING", "IN_PROGRESS", "DONE", "BLOCKED", "CANCELLED"}
EVIDENCE_RESULT = {"PASS", "FAIL", "NOT_RUN", "SKIPPED", "OBSERVED"}


def check(contract: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    if contract.get("schema") != "uwrp-professional/work-contract/v2":
        errors.append("schema must be uwrp-professional/work-contract/v2")
    if not str(contract.get("objective", "")).strip():
        errors.append("objective is empty")
    requirements = contract.get("requirements")
    tasks = contract.get("tasks", [])
    if not isinstance(requirements, list) or not requirements:
        return errors + ["requirements must be a non-empty list"], {}
    if not isinstance(tasks, list):
        return errors + ["tasks must be a list"], {}

    req_ids: set[str] = set()
    verified = 0
    for req in requirements:
        rid = req.get("id")
        if not rid or rid in req_ids:
            errors.append(f"requirement id missing or duplicated: {rid!r}")
            continue
        req_ids.add(rid)
        if not str(req.get("acceptance", "")).strip():
            errors.append(f"{rid}: no acceptance condition")
        if not str(req.get("evidence_type", "")).strip():
            errors.append(f"{rid}: no evidence_type")
        status = req.get("status")
        if status not in REQ_STATUS:
            errors.append(f"{rid}: status {status!r} not in {sorted(REQ_STATUS)}")
        evidence = req.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"{rid}: evidence must be a list")
            evidence = []
        for i, item in enumerate(evidence):
            result = item.get("result") if isinstance(item, dict) else None
            if result not in EVIDENCE_RESULT:
                errors.append(
                    f"{rid}: evidence[{i}] result {result!r} not in {sorted(EVIDENCE_RESULT)}"
                )
            elif (
                result == "PASS"
                and item.get("exit_code") is None
                and not item.get("ref")
            ):
                errors.append(
                    f"{rid}: evidence[{i}] is PASS with neither exit_code nor ref"
                )
            elif result == "PASS" and item.get("exit_code") not in (None, 0):
                errors.append(
                    f"{rid}: evidence[{i}] is PASS with exit_code {item.get('exit_code')}"
                )
        if status == "VERIFIED":
            passing = [
                e
                for e in evidence
                if isinstance(e, dict) and e.get("result") in ("PASS", "OBSERVED")
            ]
            if not passing:
                errors.append(f"{rid}: VERIFIED without PASS/OBSERVED evidence")
            else:
                verified += 1

    task_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    writers: dict[str, str] = {}
    for task in tasks:
        tid = task.get("id")
        if not tid or tid in task_ids:
            errors.append(f"task id missing or duplicated: {tid!r}")
            continue
        task_ids.add(tid)
        if task.get("status") not in TASK_STATUS:
            errors.append(
                f"{tid}: status {task.get('status')!r} not in {sorted(TASK_STATUS)}"
            )
        for rid in task.get("requirements", []):
            if rid not in req_ids:
                errors.append(f"{tid}: unknown requirement {rid}")
        graph[tid] = list(task.get("depends_on", []))
        for resource in task.get("writes", []):
            if resource in writers:
                errors.append(
                    f"{tid}: {resource!r} already written by {writers[resource]} (one writer per resource)"
                )
            else:
                writers[resource] = tid
    for tid, deps in graph.items():
        for dep in deps:
            if dep not in task_ids:
                errors.append(f"{tid}: depends on unknown task {dep}")

    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for dep in graph.get(node, []):
            if state.get(dep) == 1:
                errors.append("dependency cycle: " + " -> ".join(path + [node, dep]))
            elif dep in graph and state.get(dep) is None:
                visit(dep, path + [node])
        state[node] = 2

    for node in graph:
        if state.get(node) is None:
            visit(node, [])

    uncovered = sorted(req_ids - {r for t in tasks for r in t.get("requirements", [])})
    metrics = {
        "requirements": len(req_ids),
        "verified": verified,
        "closure": round(verified / len(req_ids), 3) if req_ids else 0.0,
        "tasks": len(task_ids),
        "requirements_without_task": uncovered,
    }
    return errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("contract", type=Path)
    parser.add_argument("--require-closure", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        if not isinstance(contract, dict):
            raise TypeError("top level must be an object")
    except (OSError, ValueError, TypeError) as exc:
        print(f"unusable contract: {exc}", file=sys.stderr)
        return 2
    errors, metrics = check(contract)
    short = (
        args.require_closure is not None
        and metrics
        and metrics["closure"] < args.require_closure
    )
    if args.json:
        print(
            json.dumps(
                {
                    "errors": errors,
                    "metrics": metrics,
                    "closure_below_required": bool(short),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for error in errors:
            print("✗", error)
        if metrics:
            print(
                f"closure {metrics['verified']}/{metrics['requirements']} = {metrics['closure']}"
                + (
                    f" (required {args.require_closure})"
                    if args.require_closure is not None
                    else ""
                )
            )
            if metrics["requirements_without_task"]:
                print(
                    "requirements with no task:",
                    ", ".join(metrics["requirements_without_task"]),
                )
        print("OK" if not errors and not short else "NOT OK")
    return 1 if errors or short else 0


if __name__ == "__main__":
    raise SystemExit(main())
