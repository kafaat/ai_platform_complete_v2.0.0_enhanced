#!/usr/bin/env python3
"""Read-only baseline of declared-operation classification on the tree it runs in.

Loads ``scripts/diagnostics/build_main_inventory.py`` and its resolver
``scripts/diagnostics/resolve_inventory_edges.py`` exactly as the inventory build does
(no copy, no modification) and prints the proven / refuted / unknown counts as JSON.
Nothing is written into the tree.

    python3 certification/evidence/architecture_remeasure_20261017/measure_edges.py
"""

from __future__ import annotations

import collections
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    inventory = _load("build_main_inventory", ROOT / "scripts/diagnostics/build_main_inventory.py")
    components = inventory.load_components()
    first_pass, declared = inventory.integration_edges(inventory.load_capabilities())
    out = inventory._resolver().classify(declared, components, ROOT)
    summary = out["report"]["classification"]
    ops = sum(len(e.get("entrypoints") or []) for e in declared)
    refuted_kinds = collections.Counter(
        (r.get("refutation") or {}).get("kind", "?") for r in out["refuted"]
    )
    refuted_ops_by_kind: dict[str, int] = {}
    for r in out["refuted"]:
        kind = (r.get("refutation") or {}).get("kind", "?")
        refuted_ops_by_kind[kind] = refuted_ops_by_kind.get(kind, 0) + len(
            r.get("entrypoints") or []
        )
    proven_ops = {
        (r["from"], r.get("to"), r.get("capability_id"), r.get("resolved_entrypoint"))
        for r in out["proven"]
    }
    proven_kinds = collections.Counter(
        r.get("evidence", {}).get("kind", "?") for r in out["proven"]
    )
    doc = {
        "engine": [
            "scripts/diagnostics/build_main_inventory.py (integration_edges, load_components)",
            "scripts/diagnostics/resolve_inventory_edges.py (classify) - unmodified",
        ],
        "edges_resolved_before_classify": len(first_pass),
        "declared_edges_entering_classify": len(declared),
        "declared_operations_entering_classify": ops,
        "proven_rows": summary["proven_rows"],
        "proven_operations_distinct": len(proven_ops),
        "proven_rows_by_evidence_kind": dict(sorted(proven_kinds.items())),
        "proven_nats_rows": summary["proven_nats_rows"],
        "refuted_operations": summary["refuted_operations"],
        "refuted_rows_by_kind": dict(sorted(refuted_kinds.items())),
        "refuted_operations_by_kind": dict(sorted(refuted_ops_by_kind.items())),
        "refuted_by_producer_count": len(summary["refuted_by_producer"]),
        "refutation_scope": summary["refutation_scope"],
        "unknown_operations": summary["unknown_operations"],
        "unknown_by_primary_reason": summary["unknown_by_primary_reason"],
        "unknown_operations_without_reason": summary["unknown_operations_without_reason"],
        "nats_subscriptions_located": summary["nats_subscriptions_located"],
        "partition_check": {
            "proven_plus_refuted_plus_unknown": len(proven_ops)
            + summary["refuted_operations"]
            + summary["unknown_operations"],
            "declared_operations": ops,
        },
        "exemption_problems": _load(
            "resolve_inventory_edges_for_exemptions",
            ROOT / "scripts/diagnostics/resolve_inventory_edges.py",
        ).exemption_problems(
            out["unknown"],
            json.loads(
                (ROOT / "docs/architecture/inventory_edge_exemptions.json").read_text(
                    encoding="utf-8"
                )
            ),
        ),
    }
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
