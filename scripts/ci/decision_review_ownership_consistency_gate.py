#!/usr/bin/env python3
"""WX-10.7 — ownership/config consistency for the decision review transition.

There is a real gap between runtime-capable SoR code and the deployed configuration: the code
can become authoritative when DECISION_SERVICE_SOR_ENABLED + DATABASE_URL are set, but the
deployed reality (db_ownership.yml) still marks the loop tables as platform-owned
(`status: interim-bridge`, mirror: decision-service).

This guard ties the code to that ownership state: **while `decision_record` is `interim-bridge`
(mirror), the review endpoint MUST fail closed in mirror mode** — it must NOT return a mirror
ack for a review (a state transition cannot be honestly mirrored). Concretely, the
`review_candidate` endpoint must, when `sor_enabled()` is false, raise a 503 and never call
`_mirror_ack`. If ownership is later promoted (status != interim-bridge), this guard's premise
relaxes and it becomes a no-op for the mirror requirement.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP = ROOT / "docs/architecture/db_ownership.yml"
DS_MAIN = ROOT / "services/decision-service/main.py"
ENDPOINT = "review_candidate"


def _decision_record_status(text: str) -> str | None:
    """Dependency-free lookup of tables.decision_record.status (no pyyaml required)."""
    lines = text.splitlines()
    in_block = False
    block_indent = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("decision_record:"):
            in_block = True
            block_indent = len(line) - len(line.lstrip())
            continue
        if in_block:
            indent = len(line) - len(line.lstrip())
            if stripped and indent <= block_indent:
                break  # left the decision_record block
            if stripped.startswith("status:"):
                return stripped.split(":", 1)[1].strip()
    return None


def _func_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return ""


violations: list[str] = []

status = _decision_record_status(OWNERSHIP.read_text(encoding="utf-8"))
endpoint_src = _func_source(DS_MAIN.read_text(encoding="utf-8"), ENDPOINT)

if not endpoint_src:
    violations.append(f"{DS_MAIN.relative_to(ROOT)}: {ENDPOINT} not found")
elif status == "interim-bridge":
    # Mirror deployment ⇒ the review must fail closed, never mirror-ack.
    if "_mirror_ack" in endpoint_src:
        violations.append(
            f"{DS_MAIN.relative_to(ROOT)}::{ENDPOINT}: returns a mirror ack while decision_record "
            "ownership is interim-bridge — a review transition must fail closed (503), not mirror"
        )
    if "sor_enabled" not in endpoint_src:
        violations.append(
            f"{DS_MAIN.relative_to(ROOT)}::{ENDPOINT}: missing sor_enabled() gate "
            "(cannot claim authoritative under interim-bridge ownership)"
        )
    if "503" not in endpoint_src:
        violations.append(
            f"{DS_MAIN.relative_to(ROOT)}::{ENDPOINT}: missing fail-closed 503 for mirror mode"
        )

if violations:
    print("decision_review_ownership_consistency_gate_failed")
    print("\n".join(violations))
    sys.exit(1)
print(f"decision_review_ownership_consistency_gate_ok (decision_record status={status})")
