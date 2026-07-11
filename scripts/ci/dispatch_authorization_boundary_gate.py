#!/usr/bin/env python3
"""WX-10.10 guard: authorization must not become dispatch or execution."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    ROOT / "services/decision-service/persistence.py": "authorize_dispatch",
    ROOT / "services/decision-service/main.py": "authorize_execution_plan_dispatch",
    ROOT
    / "services/sahool-platform/api/routers/decision_review.py": "authorize_execution_plan_dispatch",
}
FORBIDDEN = (
    "persist_dispatch_decision",
    "record_dispatch_decision",
    "create_task",
    "task_create",
    "equipment_command",
    "issue_command",
    "actuator",
    "record_outcome",
    "record_learning",
)
REQUIRED = {
    "services/decision-service/persistence.py": (
        "DISPATCH_AUTHORIZATION_CREATED",
        "decision_dispatch_authorizations",
    ),
    "services/sahool-platform/api/routers/decision_review.py": (
        "DECISION_DISPATCH_AUTHORIZE",
        "authoritative",
        "persisted",
    ),
}


def function_source(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:] or [ast.Pass()]
            return ast.unparse(node)
    return ""


violations = []
for path, name in TARGETS.items():
    src = function_source(path, name)
    if not src:
        violations.append(f"{path.relative_to(ROOT)}: missing {name}")
        continue
    low = src.lower()
    for token in FORBIDDEN:
        if token in low:
            violations.append(f"{path.relative_to(ROOT)}::{name}: forbidden token {token}")
for rel, tokens in REQUIRED.items():
    raw = (ROOT / rel).read_text(encoding="utf-8")
    for token in tokens:
        if token not in raw:
            violations.append(f"{rel}: missing required token {token}")

if violations:
    print("dispatch_authorization_boundary_gate_failed")
    print("\n".join(violations))
    sys.exit(1)
print("dispatch_authorization_boundary_gate_ok")
