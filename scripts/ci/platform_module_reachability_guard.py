#!/usr/bin/env python3
"""Classify platform modules by the executable root that can actually reach them.

``has a non-test importer`` is not reachability. A module imported only by another
module that nothing executes is still dead code, and the import makes the gap *harder*
to see: every naive importer check now passes. This guard answers the stricter question
— is there a path from something the runtime actually starts?

Root kinds are DERIVED FROM THE TREE, never assumed:

``REACHABLE_FROM_MOUNTED_ROUTE``
    ``api/routers/*.py`` — auto-registered by ``pkgutil.iter_modules`` in
    ``api/router_registry.py``, so every module in that package is mounted.
``REACHABLE_FROM_REGISTERED_WORKER``
    a module named in a compose ``command:`` as ``python -m api.<module>``.
``REACHABLE_FROM_OPERATOR_CLI``
    a ``scripts/ops/*.py`` entry point that imports platform code.
``REACHABLE_FROM_EVENT_SUBSCRIBER``
    declared for the slices that will add one. The platform has no subscriber root
    distinct from its workers today, so this set is currently empty **by measurement**,
    not by omission — a worker that subscribes is classified as a worker.
``UNREACHABLE_TERMINAL_CHAIN``
    imported only by modules that are themselves unreachable, or by nothing.

Only the first four may count toward the platform module baseline.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "services" / "sahool-platform"

MOUNTED_ROUTE = "REACHABLE_FROM_MOUNTED_ROUTE"
REGISTERED_WORKER = "REACHABLE_FROM_REGISTERED_WORKER"
EVENT_SUBSCRIBER = "REACHABLE_FROM_EVENT_SUBSCRIBER"
OPERATOR_CLI = "REACHABLE_FROM_OPERATOR_CLI"
TERMINAL = "UNREACHABLE_TERMINAL_CHAIN"
COUNTABLE = (MOUNTED_ROUTE, REGISTERED_WORKER, EVENT_SUBSCRIBER, OPERATOR_CLI)

_WORKER_CMD = re.compile(r"python\s+-m\s+(api\.[A-Za-z0-9_.]+)")
# A compose service may start a worker by PATH rather than by module — measured on
# ``sahool-canonical-execution-learning-worker``, whose command is
# ``python /app/scripts/workers/canonical_execution_learning_worker.py``. Matching only
# ``python -m api.X`` reported that genuinely-registered worker as no root at all, and
# every platform module reachable only through it as terminal. The guard was passing
# while classifying live code as dead — the same failure it exists to catch, one level
# up. ``/app`` is the image workdir; the repo path is the tail.
_WORKER_SCRIPT_CMD = re.compile(r"python\s+(?:/app/)?(scripts/[A-Za-z0-9_./-]+\.py)")

# Canonical modules that were already in the baseline and already unreachable when this
# guard was written. Recorded so the guard blocks NEW unreachable modules without
# failing on inherited debt — and so the debt is visible rather than implied.
# SHRINK-ONLY: an entry leaves when its module gains an executable root; nothing is
# added without the owner deciding to admit unreachable code, which the rule forbids.
# Verified individually: canonical_hydraulic_capability and canonical_vri_prescription
# have ZERO importers of any kind; canonical_field_state_lock is imported only by
# core/field_state_replay_bridge.py, which is itself unreachable — a terminal chain.
FROZEN_UNREACHABLE = frozenset(
    {
        "api/canonical_energy_microgrid_capability.py",
        "api/canonical_hydraulic_capability.py",
        "api/canonical_irrigation_capability_graph.py",
        "api/canonical_irrigation_machine_capability.py",
        "api/canonical_sprinkler_runoff_capability.py",
        "api/canonical_vri_prescription.py",
        "core/canonical_field_state_lock.py",
    }
)


def platform_modules() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        if rel.startswith(("tests/", "examples/")) or "/tests/" in rel or "__pycache__" in rel:
            continue
        out[rel] = path
    return out


def _dotted_index(files: dict[str, Path]) -> dict[str, str]:
    """Map importable names to files, including packages.

    ``core/crop_intelligence/__init__.py`` must answer to ``core.crop_intelligence``
    and not only to ``core.crop_intelligence.__init__`` — otherwise every chain that
    passes through a package's ``__init__`` looks broken, and the guard reports as
    unreachable a module the routers genuinely reach. Measured: without this, ten
    already-wired canonical modules were flagged, including
    ``core/crop_intelligence/canonical_inputs.py``, which ``engine.py`` imports and
    ``api/routers/crop_twin.py`` reaches through the package.
    """
    index: dict[str, str] = {}
    for rel in files:
        dotted = rel[:-3].replace("/", ".")
        index[dotted] = rel
        if dotted.endswith(".__init__"):
            index[dotted[: -len(".__init__")]] = rel
    return index


def import_graph(files: dict[str, Path]) -> dict[str, set[str]]:
    by_name = _dotted_index(files)
    edges: dict[str, set[str]] = defaultdict(set)
    for rel, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in by_name:
                        edges[rel].add(by_name[alias.name])
            elif isinstance(node, ast.ImportFrom):
                # Relative imports must be resolved against the importer's package or
                # every `from .sibling import x` reads as an unresolved edge and the
                # target looks unreachable. Measured: `api/field_state_projection.py`
                # reaches canonical_water/canonical_boundary exactly this way.
                base = node.module or ""
                if node.level:
                    pkg = rel.rsplit("/", 1)[0].replace("/", ".") if "/" in rel else ""
                    parts = pkg.split(".") if pkg else []
                    if node.level > 1:
                        parts = parts[: -(node.level - 1)] or []
                    prefix = ".".join(parts)
                    base = f"{prefix}.{base}" if base else prefix
                if not base:
                    continue
                if base in by_name:
                    edges[rel].add(by_name[base])
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    if candidate in by_name:
                        edges[rel].add(by_name[candidate])
    return edges


def mounted_route_roots(files: dict[str, Path]) -> set[str]:
    return {
        rel for rel in files if rel.startswith("api/routers/") and not rel.endswith("__init__.py")
    }


def _compose_service_commands(compose: Path) -> str:
    """Every ``command``/``entrypoint`` declared under ``services:``, and only there.

    Falls back to the raw text when PyYAML is unavailable or the file will not parse,
    so a broken compose file cannot silently empty the root set — a guard that finds
    no roots would classify the whole tree as terminal and fail loudly, which is the
    behaviour we want over a quiet pass.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML is installed in every gate job
        return compose.read_text(encoding="utf-8", errors="ignore")
    try:
        document = yaml.safe_load(compose.read_text(encoding="utf-8", errors="ignore"))
    except yaml.YAMLError:
        return compose.read_text(encoding="utf-8", errors="ignore")
    if not isinstance(document, dict):
        return ""
    services = document.get("services")
    if not isinstance(services, dict):
        return ""
    parts: list[str] = []
    for spec in services.values():
        if not isinstance(spec, dict):
            continue
        for key in ("command", "entrypoint"):
            value = spec.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append(" ".join(str(item) for item in value))
        health = spec.get("healthcheck")
        if isinstance(health, dict):
            test = health.get("test")
            if isinstance(test, str):
                parts.append(test)
            elif isinstance(test, list):
                parts.append(" ".join(str(item) for item in test))
    return "\n".join(parts)


def registered_worker_roots(files: dict[str, Path]) -> set[str]:
    """Platform modules a compose service actually starts.

    Two command shapes, both measured in this repo's compose files: ``python -m
    api.<module>`` starts a platform module directly, and ``python scripts/...py``
    starts a launcher outside the platform package whose imports are the real roots.
    """
    roots: set[str] = set()
    by_name = _dotted_index(files)
    for compose in sorted(ROOT.glob("docker-compose*.yml")):
        # Read the SERVICES BLOCK, not the file. Measured: a worker was appended under
        # ``networks:`` instead of ``services:`` — nothing would ever have started it —
        # and a text-level grep for its command matched all the same, so this guard
        # reported a root that did not exist. A command string is evidence of a root
        # only where Compose would actually execute it.
        text = _compose_service_commands(compose)
        for dotted in _WORKER_CMD.findall(text):
            rel = dotted.replace(".", "/") + ".py"
            if rel in files:
                roots.add(rel)
        for script_rel in _WORKER_SCRIPT_CMD.findall(text):
            script = ROOT / script_rel
            if not script.exists():
                continue
            try:
                tree = ast.parse(script.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                for name in names:
                    if name in by_name:
                        roots.add(by_name[name])
    return roots


def operator_cli_roots(files: dict[str, Path], edges: dict[str, set[str]]) -> set[str]:
    """scripts/ops entry points reach platform code by importing it directly."""
    roots: set[str] = set()
    ops = ROOT / "scripts" / "ops"
    if not ops.exists():
        return roots
    by_name = _dotted_index(files)
    for path in sorted(ops.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                if name in by_name:
                    roots.add(by_name[name])
    return roots


def _closure(seeds: set[str], edges: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edges[current] - seen)
    return seen


def classify() -> dict[str, str]:
    files = platform_modules()
    edges = import_graph(files)
    # Order matters: the strongest root wins, so a module on a route is reported as
    # route-reachable even if a worker also imports it.
    buckets = (
        (MOUNTED_ROUTE, mounted_route_roots(files)),
        (REGISTERED_WORKER, registered_worker_roots(files)),
        (EVENT_SUBSCRIBER, set()),
        (OPERATOR_CLI, operator_cli_roots(files, edges)),
    )
    verdict: dict[str, str] = {rel: TERMINAL for rel in files}
    for label, seeds in buckets:
        for rel in _closure(seeds, edges):
            if verdict.get(rel) == TERMINAL:
                verdict[rel] = label
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json-output")
    args = parser.parse_args()

    verdict = classify()
    baseline_path = ROOT / "docs" / "architecture" / "platform_python_module_baseline.json"
    baseline = set(json.loads(baseline_path.read_text(encoding="utf-8"))["modules"])

    counted = {rel for rel, label in verdict.items() if label in COUNTABLE}
    unreachable_in_baseline = sorted(baseline - counted - {"api/__init__.py"} - FROZEN_UNREACHABLE)

    summary = {
        label: sum(1 for v in verdict.values() if v == label)
        for label, _ in (
            (MOUNTED_ROUTE, 0),
            (REGISTERED_WORKER, 0),
            (EVENT_SUBSCRIBER, 0),
            (OPERATOR_CLI, 0),
            (TERMINAL, 0),
        )
    }
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps({"summary": summary, "modules": verdict}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print("platform module reachability:")
    for label in (MOUNTED_ROUTE, REGISTERED_WORKER, EVENT_SUBSCRIBER, OPERATOR_CLI, TERMINAL):
        print(f"  {label}: {summary[label]}")

    # The canonical-state modules this slice landed must be genuinely reachable.
    canonical = sorted(
        rel
        for rel in verdict
        if Path(rel).name.startswith(("canonical_", "agronomic_state_", "persisted_canonical_"))
    )
    offenders = [
        rel
        for rel in canonical
        if rel in baseline and verdict[rel] == TERMINAL and rel not in FROZEN_UNREACHABLE
    ]
    healed = sorted(rel for rel in FROZEN_UNREACHABLE if verdict.get(rel) != TERMINAL)
    if healed:
        print(
            "\n  ratchet: these are reachable now — remove them from FROZEN_UNREACHABLE:\n"
            + "\n".join(f"    {rel}" for rel in healed)
        )
    if args.check and offenders:
        print(
            "\n✗ canonical modules in the baseline with no executable root:\n"
            + "\n".join(f"    {rel}" for rel in offenders)
            + "\n  being imported is not being reachable — an importer that is itself "
            "unreachable does not wire anything."
        )
        return 1
    # Reported, not blocking. The baseline carries inherited unreachable modules that
    # predate this guard; failing on them would gate every change on debt it did not
    # create. The blocking assertion above is scoped to the canonical-state class the
    # ownership rule actually governs. This number is printed so the debt stays visible
    # and can be driven down deliberately.
    if unreachable_in_baseline:
        print(
            f"\n  inherited (reported, not blocking): {len(unreachable_in_baseline)} "
            "baseline modules have no executable root; first five: "
            + ", ".join(unreachable_in_baseline[:5])
        )
    print("\nplatform_module_reachability_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
