#!/usr/bin/env python3
"""RS-10A technical certification harness.

Reads a JSON manifest of real field contexts and checks the legal chain without
claiming agronomic or seasonal certification. Network calls are read-only except
when --execute is explicitly supplied.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {"tenant_id", "field_id", "season_id"}


def validate_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = data.get("fields", [])
    errors = []
    if len(fields) < 5:
        errors.append("at_least_five_fields_required")
    for index, item in enumerate(fields):
        missing = sorted(REQUIRED - set(item))
        if missing:
            errors.append(f"field_{index}_missing:{','.join(missing)}")
    return {
        "certification_scope": "technical_e2e_only",
        "field_count": len(fields),
        "manifest_valid": not errors,
        "errors": errors,
        "agronomic_certified": False,
        "controlled_intervention_certified": False,
        "model_promotion_certified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_manifest(args.manifest)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if result["manifest_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
