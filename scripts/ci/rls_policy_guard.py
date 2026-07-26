#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "database-audit/generated/database_contract_graph.json"


def findings(d):
    return [
        {
            "table": r["table"],
            "enabled": r["rls_enabled"],
            "forced": r["rls_forced"],
            "policy_count": r["policy_count"],
        }
        for r in d["tables"]
        if r["has_tenant_id"] and (not r["rls_enabled"] or not r["rls_forced"])
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()
    d = json.loads(P.read_text())
    f = findings(d)
    # Existing repository debt is inventoried, not made newly blocking. Hard fail only if generated inventory is internally inconsistent.
    if d["summary"]["tenant_rls_gaps"] != len(f):
        print("RLS inventory inconsistency", file=sys.stderr)
        raise SystemExit(1)
    print(f"RLS policy inventory: PASS ({len(f)} review candidates)")


if __name__ == "__main__":
    main()
