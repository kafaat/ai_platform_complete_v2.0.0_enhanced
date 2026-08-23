#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "database-audit/generated/database_contract_graph.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()
    d = json.loads(P.read_text(encoding="utf-8"))
    m = d["manifest"]
    if m["missing"]:
        print("Manifest references missing migrations: " + ", ".join(m["missing"]), file=sys.stderr)
        raise SystemExit(1)
    entries = m["entries"]
    if len(entries) != len(set(entries)):
        print("Duplicate migration entries in MANIFEST", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"migration graph: PASS ({len(entries)} ordered entries; {len(m['unlisted_sql'])} review-only unlisted SQL files)"
    )


if __name__ == "__main__":
    main()
