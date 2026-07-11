#!/usr/bin/env python3
"""WX-10.6 — Keep the Crop→Decision candidate path a reviewable candidate, never execution.

The crop decision-candidate boundary (bridge + endpoint) may only build/submit a
``pending_approval`` candidate owned by decision-service. It must never auto-approve,
dispatch, execute, create a task, or issue an equipment/actuator command — and it must
always require approval. This static guard fails CI if that boundary is crossed.

Docstrings and comments are stripped before scanning (they legitimately *name* the
forbidden actions in the negative, e.g. "never dispatch"); value string-literals are kept
so a real ``status="approved"`` is still caught.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "services/sahool-platform/api/crop_decision_bridge.py"
ROUTER = ROOT / "services/sahool-platform/api/routers/crop_twin.py"
CANDIDATE_FUNC = "crop_decision_candidate_endpoint"

# Tokens that would mean the candidate path *executes* rather than proposes.
FORBIDDEN = (
    "'approved'",
    '"approved"',
    "auto_approve",
    "record_dispatch",
    "dispatch_decision",
    "actuator",
    "equipment_command",
    "issue_command",
    "run_field_intelligence",
    "execute_plan",
    "task_create",
    "create_task",
)

# The bridge must keep the pending-approval + approval-required contract explicit (raw text).
REQUIRED_IN_BRIDGE = (
    "pending_approval",
    '"approval_required": True',
    '"status": "pending_approval"',
)


def _strip_docstrings(text: str) -> str:
    """Return unparsed source with module/function/class docstrings removed (comments are
    already dropped by the AST); value string-literals are preserved."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _candidate_func_source(text: str) -> str:
    """Isolate the candidate endpoint function (so unrelated routes in the same file — e.g.
    the legit execution-path comment — never trip the guard)."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == CANDIDATE_FUNC
        ):
            return ast.unparse(node)
    return ""


violations: list[str] = []

bridge_raw = BRIDGE.read_text(encoding="utf-8")
router_raw = ROUTER.read_text(encoding="utf-8")

candidate_src = _candidate_func_source(router_raw)
if not candidate_src:
    violations.append(f"{ROUTER.relative_to(ROOT)}: {CANDIDATE_FUNC} not found")

# Scan executable code only (docstrings/comments stripped).
scan_targets = {
    str(BRIDGE.relative_to(ROOT)): _strip_docstrings(bridge_raw),
    f"{ROUTER.relative_to(ROOT)}::{CANDIDATE_FUNC}": _strip_docstrings(candidate_src)
    if candidate_src
    else "",
}
for label, code in scan_targets.items():
    low = code.lower()
    for token in FORBIDDEN:
        if token.lower() in low:
            violations.append(f"{label}: forbidden execution token {token!r} on candidate path")

for token in REQUIRED_IN_BRIDGE:
    if token not in bridge_raw:
        violations.append(f"{BRIDGE.relative_to(ROOT)}: missing required contract token {token!r}")

if violations:
    print("decision_candidate_boundary_gate_failed")
    print("\n".join(violations))
    sys.exit(1)
print("decision_candidate_boundary_gate_ok")
