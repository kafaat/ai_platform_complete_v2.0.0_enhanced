#!/usr/bin/env python3
"""WX-10.7 — Keep the reviewer/decision path a state transition, never execution.

The review path (platform BFF router + the decision-service review endpoint/persistence) may
only transition a candidate to a terminal approved|rejected Decision Record + append an audit
row + emit an outbox event. It must NEVER dispatch, create a task, execute equipment, or write
outcome/learning rows. Unlike the *candidate* boundary guard, `approved`/`rejected` are the
legitimate output here — so this guard bans execution/side-effect tokens only.

Docstrings/comments are stripped before scanning (they legitimately name the forbidden actions
in the negative); value string-literals are kept. decision-service files are scanned only inside
the review function/endpoint (so the unrelated dispatch/outcome writers in the same modules never
trip the guard).
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROUTER = ROOT / "services/sahool-platform/api/routers/decision_review.py"
DS_PERSISTENCE = ROOT / "services/decision-service/persistence.py"
DS_MAIN = ROOT / "services/decision-service/main.py"
DS_REVIEW_FUNC = "review_decision"
DS_REVIEW_ENDPOINT = "review_candidate"

# Execution / side-effect tokens that would cross the review boundary.
FORBIDDEN = (
    "record_dispatch",
    "dispatch_decision",
    "persist_dispatch",
    "actuator",
    "equipment_command",
    "issue_command",
    "execute_plan",
    "task_create",
    "create_task",
    "record_outcome",
    "persist_outcome",
    "record_learning",
    "persist_learning",
    "record_recommendation_outcome",
    "run_field_intelligence",
)

# The platform router must keep the authz + fail-closed contract explicit (raw text).
REQUIRED_IN_ROUTER = ("DECISION_APPROVE", "require_permission", "authoritative")


def _strip_docstrings(text: str) -> str:
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


def _func_source(text: str, name: str) -> str:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return ""


violations: list[str] = []

router_raw = PLATFORM_ROUTER.read_text(encoding="utf-8")
ds_review_src = _func_source(DS_PERSISTENCE.read_text(encoding="utf-8"), DS_REVIEW_FUNC)
ds_endpoint_src = _func_source(DS_MAIN.read_text(encoding="utf-8"), DS_REVIEW_ENDPOINT)

if not ds_review_src:
    violations.append(f"{DS_PERSISTENCE.relative_to(ROOT)}: {DS_REVIEW_FUNC} not found")
if not ds_endpoint_src:
    violations.append(f"{DS_MAIN.relative_to(ROOT)}: {DS_REVIEW_ENDPOINT} not found")

targets = {
    str(PLATFORM_ROUTER.relative_to(ROOT)): _strip_docstrings(router_raw),
    f"{DS_PERSISTENCE.relative_to(ROOT)}::{DS_REVIEW_FUNC}": _strip_docstrings(ds_review_src)
    if ds_review_src
    else "",
    f"{DS_MAIN.relative_to(ROOT)}::{DS_REVIEW_ENDPOINT}": _strip_docstrings(ds_endpoint_src)
    if ds_endpoint_src
    else "",
}
for label, code in targets.items():
    low = code.lower()
    for token in FORBIDDEN:
        if token.lower() in low:
            violations.append(f"{label}: forbidden execution token {token!r} on review path")

for token in REQUIRED_IN_ROUTER:
    if token not in router_raw:
        violations.append(f"{PLATFORM_ROUTER.relative_to(ROOT)}: missing required token {token!r}")

if violations:
    print("decision_review_boundary_gate_failed")
    print("\n".join(violations))
    sys.exit(1)
print("decision_review_boundary_gate_ok")
