#!/usr/bin/env python3
"""Ratchet the platform capability cores against silently returning to orphaned.

Reads one registry — docs/architecture/capability_core_consumption_registry.json — and
proves, per core, that reality matches its declared status:

  status=wired          the declared consumer must exist and must actually import the
                        declared symbol from the core, checked on the AST so a mention in
                        a docstring or comment can never stand in for a real consumer.
  status=pending_wiring the core must exist and must NOT declare a consumer. A core is
                        promoted to wired only in the same change that adds its consumer.

The ratchet is the wired count: it may rise, never fall. Losing a consumer, renaming it,
or downgrading a wired core back to pending all fail here rather than passing quietly.

Deliberately scoped: these are the cores tracked by CAPABILITY-CORES-NOT-WIRED. Optional
feature activation (ml_pest_detection and friends) is a different concern that shares only
the word "capability"; scripts/ci/capability_core_consumer_gate.py governs that. Merging
the two would report this gap closed while these cores are still orphaned.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/architecture/capability_core_consumption_registry.json"

STATUS_WIRED = "wired"
STATUS_PENDING = "pending_wiring"
_VALID_STATUSES = {STATUS_WIRED, STATUS_PENDING}


def _module_path_to_import_root(module: str) -> str:
    """services/sahool-platform/core/x.py -> core.x (the import path a consumer uses)."""
    relative = module.split("services/sahool-platform/", 1)[-1]
    return relative[: -len(".py")].replace("/", ".")


def _imports_symbol(consumer: Path, module_dotted: str, symbol: str) -> bool:
    """True when the consumer really imports the symbol, judged on the AST only."""
    tree = ast.parse(consumer.read_text(encoding="utf-8"), filename=str(consumer))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_dotted:
            if any(alias.name == symbol for alias in node.names):
                return True
        if isinstance(node, ast.Import):
            if any(alias.name == module_dotted for alias in node.names):
                return True
    return False


def check() -> tuple[list[str], int, int]:
    errors: list[str] = []
    if not REGISTRY.is_file():
        return [f"registry missing: {REGISTRY.relative_to(ROOT)}"], 0, 0

    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cores = document.get("cores")
    if not isinstance(cores, list) or not cores:
        return ["registry declares no cores"], 0, 0

    seen: set[str] = set()
    wired = 0
    for index, core in enumerate(cores):
        if not isinstance(core, dict):
            errors.append(f"core #{index} is not an object")
            continue
        module = str(core.get("module") or "")
        status = str(core.get("status") or "")
        if not module:
            errors.append(f"core #{index} declares no module")
            continue
        if module in seen:
            errors.append(f"{module}: declared twice")
            continue
        seen.add(module)

        if status not in _VALID_STATUSES:
            errors.append(f"{module}: unsupported status {status!r}")
            continue
        if not (ROOT / module).is_file():
            errors.append(f"{module}: core module missing")
            continue

        consumer_rel = core.get("consumer")
        symbol = core.get("consumed_symbol")

        if status == STATUS_PENDING:
            if consumer_rel or symbol:
                errors.append(
                    f"{module}: status is {STATUS_PENDING} but a consumer is declared; "
                    f"promote it to {STATUS_WIRED} in the same change that wires it"
                )
            continue

        wired += 1
        if not consumer_rel or not symbol:
            errors.append(f"{module}: status is {STATUS_WIRED} but no consumer/symbol declared")
            continue
        consumer = ROOT / str(consumer_rel)
        if not consumer.is_file():
            errors.append(f"{module}: declared consumer missing: {consumer_rel}")
            continue
        try:
            imported = _imports_symbol(consumer, _module_path_to_import_root(module), str(symbol))
        except (OSError, SyntaxError) as exc:
            errors.append(f"{module}: cannot inspect {consumer_rel}: {exc}")
            continue
        if not imported:
            errors.append(
                f"{module}: {consumer_rel} must import {symbol!r} from "
                f"{_module_path_to_import_root(module)} — a docstring mention is not a consumer"
            )

    return errors, wired, len(cores)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without writing")
    parser.parse_args()
    errors, wired, total = check()
    if errors:
        print("capability core consumption guard: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"capability core consumption guard: PASS ({wired}/{total} cores wired)")
    if wired < total:
        pending = total - wired
        print(
            f"  {pending} core(s) still pending a production consumer (CAPABILITY-CORES-NOT-WIRED)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
