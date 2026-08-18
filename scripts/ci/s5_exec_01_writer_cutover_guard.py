#!/usr/bin/env python3
"""Fail closed unless every frozen S5-EXEC-01 platform writer has a single-authority end state.

The writer inventory comes exclusively from the generated edge-freeze artifact.  This guard
never re-derives edge_class or writer identity lexically.  It verifies the code-side cutover
contract for each frozen writer while the pre-cutover bridge remains physically present.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/s5_exec_01_edge_freeze.json"

# Contract markers are intentionally end-state semantics, not SQL discovery. The exact writer
# set comes from FREEZE; adding a writer there without adding a cutover contract blocks CI.
CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "services/sahool-platform/api/routers/recommendations.py": {
        "recommendation_outcomes": (
            "if mode.strict_decision_service_required:",
            '"authoritative_store": "decision-service"',
            'assert_platform_may_write_decision_sor("recommendation_outcomes")',
        ),
    },
    "services/sahool-platform/api/routers/decision_record.py": {
        "decision_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("decision_record")',
            '"authoritative_store": "decision-service"',
        ),
        "outcome_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("outcome_record")',
            '"authoritative_store": "decision-service"',
        ),
    },
    "services/sahool-platform/api/routers/weather.py": {
        "decision_record": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("decision_record")',
            "decision-service did not prove authoritative weather-decision persistence",
        ),
    },
    "services/sahool-platform/api/phase_runtime_store.py": {
        "online_learning_updates": (
            "if mode.strict_decision_service_required:",
            'assert_platform_may_write_decision_sor("online_learning_updates")',
            "decision-service did not prove authoritative learning-update persistence",
        ),
    },
    "services/sahool-platform/api/routers/decision_dispatch.py": {
        "dispatch_decisions": (
            "if mode.strict_decision_service_required:",
            "legacy_dispatch_writer_retired_after_decision_sor_cutover",
            'assert_platform_may_write_decision_sor("dispatch_decisions")',
        ),
    },
}


def _frozen_pairs() -> set[tuple[str, str]]:
    doc = json.loads(FREEZE.read_text(encoding="utf-8"))
    if doc.get("schema") != "sahool.s5-exec-01.edge-freeze/v2":
        raise RuntimeError("unexpected S5-EXEC-01 freeze schema")
    pairs: set[tuple[str, str]] = set()
    for item in doc.get("writer_cutover_set_runtime_only", []):
        table = str(item.get("table", ""))
        for writer in item.get("writers", []):
            pairs.add((str(writer), table))
    return pairs


def findings() -> list[str]:
    errors: list[str] = []
    frozen = _frozen_pairs()
    declared = {(path, table) for path, tables in CONTRACTS.items() for table in tables}
    missing_contract = sorted(frozen - declared)
    stale_contract = sorted(declared - frozen)
    for writer, table in missing_contract:
        errors.append(f"FROZEN_WRITER_WITHOUT_CUTOVER_CONTRACT {table} {writer}")
    for writer, table in stale_contract:
        errors.append(f"STALE_CUTOVER_CONTRACT {table} {writer}")

    for writer, table in sorted(frozen & declared):
        path = ROOT / writer
        if not path.is_file():
            errors.append(f"MISSING_FROZEN_WRITER {table} {writer}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in CONTRACTS[writer][table]:
            if marker not in text:
                errors.append(f"CUTOVER_MARKER_MISSING {table} {writer}: {marker}")
    return errors


def main() -> int:
    errors = findings()
    if errors:
        print("S5_EXEC_01_WRITER_CUTOVER_BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"s5_exec_01_writer_cutover_ok frozen_writers={len(_frozen_pairs())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
