"""Reverting a field boundary takes the tenant geometry lock and refuses an overlap (409).

Review finding (team review of #1392): PATCH serialised geometry writers and refused
overlaps, but revert_field_geometry wrote fields.geometry with neither. Scenario: field A
is edited away from an area, field B is created there, then A is reverted to its old
revision; before the fix this returned 200 and stored two overlapping fields.

The combined guard is proven against PostGIS in test_field_overlap_postgis.py and #1392's
live harness; here we pin that every geometry writer of an existing field calls it before
its UPDATE, without a fake connection.
"""

import ast
import inspect
import textwrap

import pytest

pytestmark = pytest.mark.unit


def _calls_in_order(fn) -> list[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    names: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "_lock_and_reject_field_overlap":
                names.append((node.lineno, node.col_offset, "guard"))
            if name == "execute" and any(
                isinstance(a, ast.Constant) and "UPDATE fields" in str(a.value) for a in node.args
            ):
                names.append((node.lineno, node.col_offset, "update"))
    return [n for _, _, n in sorted(names)]


@pytest.mark.parametrize("writer", ["revert_field_geometry"])
def test_geometry_writers_guard_overlap_before_they_update(writer):
    from api import main  # noqa: F401  (import the app before its routers, as production does)
    from api.routers import fields as mod

    order = _calls_in_order(getattr(mod, writer))
    assert "guard" in order, f"{writer} never calls _lock_and_reject_field_overlap"
    assert "update" in order
    assert order.index("guard") < order.index("update")


def test_the_combined_guard_locks_before_checking(monkeypatch):
    import asyncio

    from api import field_models

    order = []

    async def lock(conn, tenant_id):
        order.append(("lock", tenant_id))

    async def reject(conn, tenant_id, geometry, exclude_field_id=None):
        order.append(("reject", tenant_id, exclude_field_id))

    monkeypatch.setattr(field_models, "_lock_field_boundaries", lock)
    monkeypatch.setattr(field_models, "_reject_field_overlap", reject)
    asyncio.run(field_models._lock_and_reject_field_overlap(None, "t", {}, "f"))
    assert order == [("lock", "t"), ("reject", "t", "f")]
