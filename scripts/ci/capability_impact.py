#!/usr/bin/env python3
"""Map changed repository paths to directly and transitively affected capabilities.

This is the tool a human or agent runs before writing a PR's ``Capability-Impact:``
line — ``docs/capabilities/CAPABILITY_GOVERNANCE.md`` documents exactly that. It is
therefore a thin CLI over the *same* engine the blocking gate uses
(``pr_capability_impact_gate.impact``), and never a second implementation of it.

It used to be a second implementation, and the two disagreed. Measured on one fixed
ten-path fixture spanning the platform API, a migration, the worker, the e2e scripts,
compose and the frontend:

    direct      legacy=0   gate=5    (DEC-006, GIS-003, INT-002, SEC-001, WX-006)
    affected    legacy=0   gate=12

The legacy walk read only the hand-maintained ``capabilities/registry`` lists
(``services``/``tests``/``ui_consumers``/``evidence``). The gate additionally reads
``capability_mapping.json`` — the generated map from real repository paths to
capabilities, by dimension (``mapping:backend``, ``mapping:events``, ``mapping:web``,
``mapping:other_evidence``). Every capability the legacy tool missed was reached
through that map, which is why the divergence grew with the size of the diff instead of
being one stray identifier.

That is not a display difference. Answering "what does my change affect?" with a number
that is too small is how a change escapes impact declaration; and a contributor who
trusts this tool then gets blocked by a gate quoting a different answer. One engine, one
answer, and a parity test that fails if they ever fork again:
``tests_v9/test_capability_impact_parity.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "ci") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "ci"))

from pr_capability_impact_gate import (  # noqa: E402  (import after sys.path insertion)
    current_snapshot,
    impact,
)


def compute(paths: list[str]) -> dict[str, object]:
    """Return the shared engine's verdict, in this CLI's long-standing output shape."""
    result = impact(paths, current_snapshot())
    return {
        "changed_paths": result["changed_paths"],
        "direct": result["direct"],
        "transitive": result["transitive"],
        "affected": result["affected"],
        # Kept from the engine: which path and which registry/mapping dimension pulled
        # each capability in. Without it a surprising id looks arbitrary — and it was
        # exactly this field that identified the divergence above as a mapping-layer
        # blindness rather than a stray entry.
        "matched_paths": result["matched_paths"],
        "matched_sources": result["matched_sources"],
        # Governance-wide paths (this file among them) make every capability affected.
        # The declaration for such a diff is the single token ALL, never an enumeration
        # of all 81 ids — passed through so callers can say so instead of guessing.
        "governance_wide": result["governance_wide"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = compute(args.paths)
    print(json.dumps(payload, indent=2) if args.json else "\n".join(payload["affected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
