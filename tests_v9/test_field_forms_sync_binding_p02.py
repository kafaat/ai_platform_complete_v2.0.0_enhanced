"""P0-2 (مراجعة PR #585): ربط sync proof إلزاميّ بالمستخدم والجهاز والتكليف — fail-closed.

قبل الإصلاح: حذف X-Actor-Id أو assignment_revision كان يُلغي المقارنة (if actor_id and ...).
بعده: أيّ غياب/عدم تطابق ⇒ None ⇒ invalid_sync_proof. وصفّ assignment يُقرأ من PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="integration job installs minimal deps (no fastapi)")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "scout-ingest-service"))

os.environ.setdefault("FIELD_FORMS_SYNC_HMAC_KEY", "test-secret-p02")
os.environ.setdefault("FIELD_FORMS_SYNC_HMAC_KEY_ID", "k1")

import field_forms_api as api  # noqa: E402

from shared.contracts.forms.sync_token import issue_token  # noqa: E402

TENANT = str(uuid.uuid4())
VERSION = str(uuid.uuid4())
ASSIGNMENT = str(uuid.uuid4())


def _token(**over):
    claims = {
        "token_version": 1,
        "key_id": "k1",
        "tenant_id": TENANT,
        "actor_id": "scout-1",
        "device_id": "device-9",
        "assignment_id": ASSIGNMENT,
        "revision": 3,
        "form_version_id": VERSION,
        "schema_hash": "abc123",
        "issued_at": time.time(),
    }
    claims.update(over)
    return issue_token(claims, secret="test-secret-p02", key_id="k1")


def _verify(token, **kw):
    args = {
        "tenant": TENANT,
        "actor_id": "scout-1",
        "device_id": "device-9",
        "assignment_revision": 3,
        "form_version_id": VERSION,
        "schema_hash": "abc123",
    }
    args.update(kw)
    return api._verify_sync_claims(token, **args)


def test_valid_full_binding_accepted() -> None:
    claims = _verify(_token())
    assert claims is not None and claims["assignment_id"] == ASSIGNMENT


def test_missing_actor_header_fails_closed() -> None:
    """كان يمرّ قبل الإصلاح (if actor_id and ...) — الآن None."""
    assert _verify(_token(), actor_id=None) is None


def test_wrong_actor_rejected() -> None:
    assert _verify(_token(), actor_id="intruder") is None


def test_missing_device_header_fails_closed() -> None:
    assert _verify(_token(), device_id=None) is None


def test_wrong_device_rejected() -> None:
    assert _verify(_token(), device_id="device-x") is None


def test_missing_assignment_revision_fails_closed() -> None:
    """كان يمرّ قبل الإصلاح (if revision is not None ...) — الآن None."""
    assert _verify(_token(), assignment_revision=None) is None


def test_wrong_revision_rejected() -> None:
    assert _verify(_token(), assignment_revision=2) is None


def test_no_token_rejected() -> None:
    assert _verify(None) is None


class _FakeConn:
    """يوثّق استعلام الإسناد ويرجع صفًّا مضبوطًا — برهان قراءة PostgreSQL بلا PG حيّ."""

    def __init__(self, row):
        self._row = row
        self.queries: list[tuple] = []

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        return self._row


def test_assignment_row_matched_by_field() -> None:
    conn = _FakeConn({"field_id": "field-1"})
    ok = asyncio.run(api._assignment_row_matches(conn, TENANT, ASSIGNMENT, "field-1"))
    assert ok is True
    query, args = conn.queries[0]
    assert "FROM field_form_assignments" in query and args[0] == TENANT


def test_assignment_row_wrong_field_rejected() -> None:
    conn = _FakeConn({"field_id": "field-other"})
    assert asyncio.run(api._assignment_row_matches(conn, TENANT, ASSIGNMENT, "field-1")) is False


def test_assignment_row_missing_rejected() -> None:
    conn = _FakeConn(None)
    assert asyncio.run(api._assignment_row_matches(conn, TENANT, ASSIGNMENT, "field-1")) is False


def test_assignment_row_bad_uuid_rejected() -> None:
    conn = _FakeConn({"field_id": "field-1"})
    assert asyncio.run(api._assignment_row_matches(conn, TENANT, "not-a-uuid", "field-1")) is False
    assert conn.queries == []  # فشل قبل لمس القاعدة


class _FakeFetchConn:
    def __init__(self, rows):
        self._rows = rows
        self.queries: list[tuple] = []

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return self._rows


def test_resolve_active_assignment_single() -> None:
    conn = _FakeFetchConn([{"id": ASSIGNMENT}])
    out = asyncio.run(api._resolve_active_assignment(conn, TENANT, "field-1", uuid.uuid4()))
    assert out == ASSIGNMENT
    query, _ = conn.queries[0]
    assert "v.status = 'published'" in query and "active_to IS NULL" in query


def test_resolve_active_assignment_none() -> None:
    conn = _FakeFetchConn([])
    assert asyncio.run(api._resolve_active_assignment(conn, TENANT, "f", uuid.uuid4())) is None


def test_resolve_active_assignment_ambiguous() -> None:
    conn = _FakeFetchConn([{"id": ASSIGNMENT}, {"id": str(uuid.uuid4())}])
    out = asyncio.run(api._resolve_active_assignment(conn, TENANT, "f", uuid.uuid4()))
    assert out == "ambiguous"
