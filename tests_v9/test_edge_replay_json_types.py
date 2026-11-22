"""An edge replay with the same idempotency key must carry the same JSON, compared like jsonb.

Found by the lab (Edge v286 verification, 22 Nov 2026): a replay that changed
``"reviewed": true`` into ``"reviewed": 1`` was answered ``200 duplicate_ignored`` while the
stored row kept ``true``. PostgreSQL said the two ``jsonb`` values differ; the router compared
the decoded values with Python's ``==``, where ``True == 1``. The device then holds a success
receipt for a change that was never stored.

The expected answers below are PostgreSQL 16 ``jsonb`` equality, measured: ``true``/``1`` and
``false``/``0`` differ, ``null``/``false`` differ, ``"1"``/``1`` differ, ``1``/``1.0``/``1e0`` are
equal, object key order is ignored, array order is not.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "sahool-platform"))

# Match the application's entry point: importing edge first makes api.main's registrar
# see the incomplete circular import before edge.router exists, so it skips the router.
import api.main  # noqa: E402, F401
from api.routers import edge  # noqa: E402

JSONB_EQUALITY = [
    (True, 1, False),
    (False, 0, False),
    (None, False, False),
    ("1", 1, False),
    (1, 1.0, True),
    (1, 1e0, True),
    ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
    ([1, 2], [2, 1], False),
    ({"reviewed": True}, {"reviewed": 1}, False),
    ({"d": [{"c": 0.9, "ok": False}]}, {"d": [{"c": 0.9, "ok": 0}]}, False),
    ({"d": [{"c": 0.9, "ok": False}]}, {"d": [{"ok": False, "c": 0.9}]}, True),
    ({"a": 1}, {"a": 1, "b": None}, False),
    (True, True, True),
    # PostgreSQL stores 1e23 as the integer 100000000000000000000000 (numeric is exact).
    (100000000000000000000000, 1e23, True),
    (0.1, 0.1, True),
    (100000000000000000000001, 1e23, False),
    (int(1e23), 1e23, False),
    (2**53 + 1, float(2**53 + 1), False),
    ({"readings": [10**23]}, {"readings": [1e23]}, True),
]


@pytest.mark.parametrize(("stored", "sent", "equal"), JSONB_EQUALITY)
def test_same_json_follows_jsonb_equality(stored, sent, equal):
    assert edge.same_json(stored, sent) is equal
    assert edge.same_json(sent, stored) is equal


def _replay_comparisons() -> list[ast.Compare | ast.Call]:
    """The terms of the condition that raises ``edge_idempotency_conflict`` in the route."""
    tree = ast.parse(inspect.getsource(edge.edge_sync_receive))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        raised = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Constant) and n.value == "edge_idempotency_conflict"
        ]
        if raised and isinstance(node.test, ast.BoolOp):
            return [
                v.operand if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not) else v
                for v in node.test.values
            ]
    raise AssertionError("the replay conflict condition is no longer in edge_sync_receive")


def test_the_replay_check_compares_the_body_with_same_json():
    # The route compares the stored row with the resent body through same_json, so the
    # comparator tests above are what the route answers. (A route test with a stand-in
    # connection would add to the fake-connection debt; the live proof is in
    # test_edge_sync_tenant_per_request_live_pg.py.)
    calls = [
        term
        for term in _replay_comparisons()
        if isinstance(term, ast.Call)
        and isinstance(term.func, ast.Name)
        and term.func.id == "same_json"
    ]
    assert [ast.unparse(c) for c in calls] == ["same_json(payload, req.data)"], (
        "edge_sync_receive must compare the resent body with same_json(payload, req.data)"
    )


def test_the_body_is_not_also_compared_with_python_equality():
    plain = [
        ast.unparse(term)
        for term in _replay_comparisons()
        if isinstance(term, ast.Compare) and "payload" in ast.unparse(term)
    ]
    assert plain == [], f"a Python ==/!= on the body treats True as 1 and reopens the bug: {plain}"
