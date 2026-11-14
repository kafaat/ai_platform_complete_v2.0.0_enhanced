#!/usr/bin/env python3
"""Offline-only format check; never grants production model admission.

Real source-record verification must be performed by Decision Service or an
independent, trusted evaluator. This CLI deliberately has no verifier override.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON with evaluation, promotion, evidence, target_environment",
    )
    args = parser.parse_args(argv)
    from shared.mlops import assess_agronomic_model_candidate

    try:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        result = assess_agronomic_model_candidate(
            doc["evaluation"],
            doc["promotion"],
            doc["evidence"],
            target_environment=doc["target_environment"],
            trusted_verifier=None,
        )
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INPUT_INVALID", "error": type(exc).__name__}))
        return 2
    print(
        json.dumps(
            {"status": "SCHEMA_PREFLIGHT_ONLY_NOT_AUTHORIZED", **result}, indent=2, sort_keys=True
        )
    )
    # No amount of caller-supplied material can make this CLI an approval.
    return 2


if __name__ == "__main__":
    sys.exit(main())
