"""save_field_geometry_revision is part of its caller's transaction: it never swallows a failure.

The live proof is tests_v9/test_field_geometry_save_atomic_live_pg.py (real handlers, a
PostgreSQL refusal, the aborted transaction). This is the unit-level contract the handlers
rely on: the revision comes back as an int, and an error from the INSERT reaches the caller
instead of being turned into ``None`` (the old "best effort" that let COMMIT on an aborted
transaction roll back silently while the handler answered success).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from api.spatial_sync import save_field_geometry_revision

pytestmark = pytest.mark.unit

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[44.3, 15.45], [44.31, 15.45], [44.3, 15.46], [44.3, 15.45]]],
}


class _Conn:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, tuple]] = []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        if self.error is not None:
            raise self.error
        return self.result


def _save(conn, **overrides):
    kwargs = {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "field_id": "f-1",
        "geometry": SQUARE,
        "changed_by": "u-1",
        "reason": "field.updated",
        "source": "api.patch",
    }
    kwargs.update(overrides)
    return asyncio.run(save_field_geometry_revision(conn, **kwargs))


def test_the_revision_comes_back_as_an_int_from_one_insert_on_the_callers_connection():
    conn = _Conn(result=3)
    assert _save(conn, metadata={"field_revision": 2}) == 3
    [(sql, args)] = conn.calls
    assert "INSERT INTO field_geometry_history" in sql and "RETURNING revision" in sql
    assert json.loads(args[2]) == SQUARE
    assert json.loads(args[6]) == {"field_revision": 2}


def test_missing_metadata_is_stored_as_an_empty_object():
    conn = _Conn(result=1)
    _save(conn)
    assert json.loads(conn.calls[0][1][6]) == {}


def test_an_insert_error_reaches_the_caller_instead_of_becoming_none():
    class InsufficientPrivilege(Exception):
        pass

    conn = _Conn(error=InsufficientPrivilege("permission denied for table field_geometry_history"))
    with pytest.raises(InsufficientPrivilege):
        _save(conn)
