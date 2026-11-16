#!/usr/bin/env python3
"""Every default-profile compose service is a Helm workload or a ledgered exclusion (W3-09).

The Helm chart declared six workloads while ``docker-compose.v9.yml`` ran sixty-seven
services without a ``profiles:`` key, and nothing said which of the other sixty-one were
left out on purpose. A service added to compose never reached the chart, and a workload
that dropped a variable compose refuses to start without (``${VAR:?...}``) rendered a pod
that would not boot. Nobody measured either gap.

This guard makes the chart's coverage of the compose stack a set equality, not a claim:

* every default-profile compose service is either a workload in ``helm/sahool/values.yaml``
  (same name) or an entry in ``docs/architecture/helm_compose_workload_ledger.json`` with a
  category and a written reason;
* a ledger entry for a service that now has a workload, or that compose no longer runs,
  is stale and blocks (the ledger shrinks, it does not rot);
* every workload names a compose service, so its required variables can be read;
* for each workload, every container variable compose marks required (its value holds a
  ``${NAME:?...}`` interpolation) is rendered by the workload's ``env`` or ``secretEnv``,
  or is excused in the ledger with a reason. An excuse for a variable that is now rendered,
  or no longer required, is stale and blocks.

It reads YAML and JSON only. It does not run ``helm template``; what the chart renders for
``env``/``secretEnv`` is the loop in ``templates/deployments.yaml``, which emits one
container variable per key plus ``SAHOOL_ENV``.

    python scripts/ci/helm_compose_workload_guard.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
VALUES = ROOT / "helm" / "sahool" / "values.yaml"
LEDGER = ROOT / "docs" / "architecture" / "helm_compose_workload_ledger.json"

#: Container variables templates/deployments.yaml renders for every workload, whatever
#: its values say.
ALWAYS_RENDERED = frozenset({"SAHOOL_ENV"})

#: ``${NAME:?message}`` or ``${NAME?message}``: compose refuses to start without NAME.
_REQUIRED = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?\?")


def _environment(service: dict) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        pairs = (item.split("=", 1) if "=" in item else (item, "") for item in env)
        return {key: value for key, value in pairs}
    return {str(key): "" if value is None else str(value) for key, value in env.items()}


def default_profile_services(compose: dict) -> dict[str, dict]:
    """Services ``docker compose up`` starts with no ``--profile``."""
    return {
        name: (spec or {})
        for name, spec in (compose.get("services") or {}).items()
        if not (spec or {}).get("profiles")
    }


def required_variables(service: dict) -> set[str]:
    """Container variables whose compose value refuses to interpolate when unset."""
    return {key for key, value in _environment(service).items() if _REQUIRED.search(value)}


def rendered_variables(workload: dict) -> set[str]:
    return (
        set(workload.get("env") or {})
        | set(workload.get("secretEnv") or {})
        | set(ALWAYS_RENDERED)
    )


def audit(compose: dict, values: dict, ledger: dict) -> tuple[list[str], dict[str, int]]:
    """Problems (empty means pass) and the counts the PASS line reports."""
    problems: list[str] = []
    services = default_profile_services(compose)
    workloads: dict[str, dict] = values.get("workloads") or {}
    categories: dict[str, str] = ledger.get("categories") or {}
    excluded: dict[str, dict] = {
        k: v for k, v in (ledger.get("excluded") or {}).items() if not k.startswith("$")
    }
    excused: dict[str, dict] = {
        k: v for k, v in (ledger.get("env_excused") or {}).items() if not k.startswith("$")
    }

    if not services:
        # Zero services read as a pass would certify nothing.
        problems.append(f"{COMPOSE.name}: no default-profile service was read")
    if not workloads:
        problems.append(f"{VALUES.relative_to(ROOT).as_posix()}: no workload was read")

    for name in sorted(set(services) - set(workloads) - set(excluded)):
        problems.append(
            f"{name}: compose service with no Helm workload and no ledger entry — add a "
            f"workload to helm/sahool/values.yaml or an entry with a reason to "
            f"{LEDGER.relative_to(ROOT).as_posix()}"
        )
    for name in sorted(set(excluded) & set(workloads)):
        problems.append(f"{name}: stale ledger entry — the chart now declares this workload")
    for name in sorted(set(excluded) - set(services)):
        problems.append(f"{name}: stale ledger entry — not a default-profile compose service")
    for name in sorted(set(workloads) - set(services)):
        problems.append(
            f"{name}: Helm workload with no default-profile compose service of that name — "
            "its required variables cannot be read"
        )

    for name, entry in sorted(excluded.items()):
        category = (entry or {}).get("category")
        if category not in categories:
            problems.append(f"{name}: ledger category {category!r} is not declared")
        if not str((entry or {}).get("reason", "")).strip():
            problems.append(f"{name}: ledger entry has no reason")

    checked = 0
    for name in sorted(set(workloads) & set(services)):
        required = required_variables(services[name])
        rendered = rendered_variables(workloads[name])
        excuses = {k: v for k, v in (excused.get(name) or {}).items() if not k.startswith("$")}
        for var in sorted(required - rendered - set(excuses)):
            problems.append(
                f"{name}: compose requires {var} (${{...:?}}) and the workload renders it in "
                "neither env nor secretEnv, and the ledger does not excuse it"
            )
        for var, reason in sorted(excuses.items()):
            if var in rendered:
                problems.append(f"{name}: stale excuse for {var} — the workload now renders it")
            elif var not in required:
                problems.append(f"{name}: stale excuse for {var} — compose no longer requires it")
            elif not str(reason).strip():
                problems.append(f"{name}: excuse for {var} has no reason")
        checked += len(required)
    for name in sorted(set(excused) - set(workloads)):
        problems.append(f"{name}: stale env excuse — the chart declares no such workload")

    counts = {
        "services": len(services),
        "workloads": len(set(workloads) & set(services)),
        "excluded": len(set(excluded) & set(services)),
        "required": checked,
    }
    return problems, counts


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main() -> int:
    problems, counts = audit(
        _load_yaml(COMPOSE),
        _load_yaml(VALUES),
        json.loads(LEDGER.read_text(encoding="utf-8")),
    )
    if problems:
        print("helm_compose_workload_guard: FAIL")
        for line in problems:
            print(f"  - {line}")
        return 1
    print(
        "helm_compose_workload_guard: PASS "
        f"({counts['services']} default-profile compose services == "
        f"{counts['workloads']} Helm workloads + {counts['excluded']} ledger exclusions; "
        f"{counts['required']} compose-required variables checked on the workloads)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
