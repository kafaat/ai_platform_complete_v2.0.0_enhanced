"""Governed learning review path — static contract (G14 / F-D02, unit, no database).

The live behaviour (tenant scope, idempotency, refusals) is measured in
``test_governed_learning_review_live_pg.py``. Here, without a database: the review writes only
the review columns (never ``auto_promote``/``auto_adjust``, evidence or proposed changes), both
routes are gated by the permission that already governs model-activation review, and the
existing role matrix decides who holds it (no new role).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
ROUTER = PLATFORM / "api" / "routers" / "learning.py"
ROUTES = {
    "list_governed_learning_proposals": ("get", "/api/v1/learning/governed-proposals"),
    "review_governed_learning_proposal": (
        "post",
        "/api/v1/learning/governed-proposals/{kind}/{proposal_id}/review",
    ),
}


def _feedback():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.learning_feedback as feedback

    return feedback


def test_the_review_update_sets_only_the_review_columns():
    feedback = _feedback()
    assert set(feedback._REVIEW_SQL) == set(feedback.LEARNING_PROPOSAL_KINDS)
    for kind, sql in feedback._REVIEW_SQL.items():
        set_clause = re.search(r"\bSET\b(.*?)\bWHERE\b", sql, re.S).group(1)
        columns = {part.split("=")[0].strip() for part in set_clause.split(",")}
        assert columns == {"status", "reviewed_by", "reviewed_at"}, kind
        for forbidden in ("auto_promote", "auto_adjust", "evidence", "proposed_parameter"):
            assert forbidden not in sql.split("RETURNING")[0], kind
        # compare-and-set on the status read under FOR UPDATE: no blind overwrite
        assert "AND status = $5" in sql, kind
    for kind, sql in feedback._LOCK_SQL.items():
        assert sql.rstrip().endswith("FOR UPDATE"), kind


def test_both_routes_require_the_model_activation_review_permission():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in ROUTES:
            [decorator] = node.decorator_list
            method = decorator.func.attr
            path = decorator.args[0].value
            gate = ast.unparse(node.args.defaults[-1])
            found[node.name] = (method, path, gate)
    assert set(found) == set(ROUTES)
    for name, (method, path, gate) in found.items():
        assert (method, path) == ROUTES[name]
        assert gate == "Depends(require_permission(Permission.DECISION_MODEL_ACTIVATION_APPROVE))"


def test_the_existing_role_matrix_decides_who_reviews():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from core.authorization import Permission, UserRole, has_permission
    from core.canonical_schemas import UserSchema

    def holds(role):
        user = UserSchema(user_id="u", tenant_id="t", role=role, name_ar="x")
        return has_permission(user, Permission.DECISION_MODEL_ACTIVATION_APPROVE)

    assert holds(UserRole.OWNER) is True
    for role in (UserRole.MANAGER, UserRole.AGRONOMIST, UserRole.WORKER):
        assert holds(role) is False
