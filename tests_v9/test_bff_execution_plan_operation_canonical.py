"""The platform BFF branches on the same operation_type spelling decision-service stores.

decision-service normalises operation_type (strip + lowercase) before binding a plan to its
approved irrigation decision. The BFF compared the raw value, so " manual_irrigation " became a
validated canonical plan downstream while the BFF skipped its manual-irrigation checks and its
manual execution source. DECISION-MANUAL-PLAN-PADDED-OPERATION-BYPASS-01.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BFF = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "sahool-platform"
    / "api"
    / "routers"
    / "decision_review.py"
)


def _plan_handler() -> ast.AsyncFunctionDef:
    tree = ast.parse(BFF.read_text(encoding="utf-8"))
    return next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_decision_execution_plan"
    )


def _manual_branch_subjects() -> list[str]:
    subjects = []
    for node in ast.walk(_plan_handler()):
        if (
            isinstance(node, ast.Compare)
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value == "manual_irrigation"
        ):
            subjects.append(ast.unparse(node.left))
    return subjects


def test_the_manual_branch_exists():
    assert _manual_branch_subjects(), "the plan handler no longer branches on manual_irrigation"


@pytest.mark.parametrize(
    "raw", [" manual_irrigation ", "Manual_Irrigation", "\tMANUAL_IRRIGATION\n"]
)
def test_every_manual_branch_compares_the_canonical_spelling(raw):
    for subject in _manual_branch_subjects():
        assert subject == "req.operation_type.strip().lower()", (
            f"the BFF compares {subject!r}: a padded or capitalised value such as {raw!r} would "
            "skip the manual-irrigation checks that decision-service then treats as satisfied"
        )
        assert eval(subject, {}, {"req": type("R", (), {"operation_type": raw})}) == (
            "manual_irrigation"
        )
