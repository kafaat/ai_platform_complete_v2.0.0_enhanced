"""Regression contracts for tenant-scoped sharing-key revocation (PR #1542)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_revoke_key_uses_tenant_connection_and_canonical_uuid(monkeypatch):
    from api.routers import sharing

    key_id = str(uuid4()).upper()
    tenant_id = str(uuid4())
    observed = []

    @asynccontextmanager
    async def tenant_connection(user):
        observed.append(("tenant_connection", user.tenant_id))
        yield object()

    class Service:
        def __init__(self, pool, conn):
            assert conn is not None

        async def revoke_key(self, key, tenant):
            observed.append(("revoke", key, tenant))
            return True

    monkeypatch.setattr(sharing, "tenant_connection", tenant_connection)
    monkeypatch.setattr(sharing, "get_pool", lambda: None)
    monkeypatch.setattr(sharing, "SharingKeyService", Service)
    result = await sharing.revoke_sharing_key(key_id, SimpleNamespace(tenant_id=tenant_id))
    assert result == {"key_id": key_id.lower(), "status": "revoked"}
    assert observed == [
        ("tenant_connection", tenant_id),
        ("revoke", key_id.lower(), tenant_id),
    ]


@pytest.mark.asyncio
async def test_revoke_missing_or_foreign_key_has_same_not_found_response(monkeypatch):
    from api.routers import sharing

    @asynccontextmanager
    async def tenant_connection(user):
        yield object()

    class Service:
        def __init__(self, pool, conn):
            pass

        async def revoke_key(self, key, tenant):
            return False

    monkeypatch.setattr(sharing, "tenant_connection", tenant_connection)
    monkeypatch.setattr(sharing, "get_pool", lambda: None)
    monkeypatch.setattr(sharing, "SharingKeyService", Service)
    for tenant in (str(uuid4()), str(uuid4())):
        with pytest.raises(HTTPException) as exc:
            await sharing.revoke_sharing_key(str(uuid4()), SimpleNamespace(tenant_id=tenant))
        assert exc.value.status_code == 404
        assert exc.value.detail == "sharing_key_not_found"


@pytest.mark.asyncio
async def test_revoke_rejects_invalid_uuid_before_database(monkeypatch):
    from api.routers import sharing

    @asynccontextmanager
    async def forbidden_connection(user):
        pytest.fail("Invalid UUID must not touch the database")
        yield

    monkeypatch.setattr(sharing, "tenant_connection", forbidden_connection)
    with pytest.raises(HTTPException) as exc:
        await sharing.revoke_sharing_key("not-a-uuid", SimpleNamespace(tenant_id=str(uuid4())))
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_sharing_key_id"
