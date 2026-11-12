"""Reverting a field boundary takes the tenant geometry lock and refuses an overlap (409).

Review finding (team review of #1392): PATCH serialised geometry writers and refused
overlaps, but revert_field_geometry wrote fields.geometry with neither. Scenario: field A
is edited away from an area, field B is created there, then A is reverted to its old
revision. Before the fix this returned 200 and stored two overlapping fields.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

_BOX = {
    "type": "Polygon",
    "coordinates": [[[44, 16], [44.01, 16], [44.01, 16.01], [44, 16.01], [44, 16]]],
}


class _Conn:
    def __init__(self):
        self.executed: list[str] = []

    async def fetchrow(self, query, *args):
        if "FROM field_geometry_history" in query:
            return {"geometry": _BOX, "revision": 1}
        raise AssertionError(f"unexpected fetchrow after a refused revert: {query[:60]}")

    async def execute(self, query, *args):
        self.executed.append(query)


async def test_revert_into_another_fields_space_is_refused_before_any_write(monkeypatch):
    from api import main  # noqa: F401  (import the app before its routers, as production does)
    from api.routers import fields as mod

    conn = _Conn()
    calls = []

    @asynccontextmanager
    async def fake_tenant_connection(_user):
        yield conn

    async def fake_assert(_conn, _field_id):
        return None

    async def refuse_overlap(c, tenant_id, geometry, exclude_field_id=None):
        calls.append((tenant_id, exclude_field_id))
        raise HTTPException(status_code=409, detail={"code": "field_geometry_overlap"})

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_assert_field_in_tenant", fake_assert)
    monkeypatch.setattr(mod, "_lock_and_reject_field_overlap", refuse_overlap)

    user = SimpleNamespace(tenant_id="11111111-1111-4111-8111-111111111111", user_id="u1")
    with pytest.raises(HTTPException) as exc:
        await mod.revert_field_geometry("field-a", 1, background_tasks=None, user=user)

    assert exc.value.status_code == 409
    assert calls == [("11111111-1111-4111-8111-111111111111", "field-a")]
    assert not any("UPDATE fields" in q for q in conn.executed)


async def test_the_combined_guard_locks_before_checking(monkeypatch):
    from api import field_models

    order = []

    async def lock(conn, tenant_id):
        order.append(("lock", tenant_id))

    async def reject(conn, tenant_id, geometry, exclude_field_id=None):
        order.append(("reject", tenant_id, exclude_field_id))

    monkeypatch.setattr(field_models, "_lock_field_boundaries", lock)
    monkeypatch.setattr(field_models, "_reject_field_overlap", reject)
    await field_models._lock_and_reject_field_overlap(object(), "t", _BOX, "f")
    assert order == [("lock", "t"), ("reject", "t", "f")]
