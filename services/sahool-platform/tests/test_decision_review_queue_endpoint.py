from __future__ import annotations

import api.main  # noqa: F401
import api.routers.decision_review as mod
import pytest
from api.routers.decision_review import get_decision_review_queue
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="reviewer-1",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.MANAGER,
    name_ar="مراجع",
)


@pytest.mark.asyncio
async def test_authoritative_queue_passes_through(monkeypatch):
    seen = {}

    async def fake(*, tenant_id=None, limit=100):
        seen.update(tenant_id=tenant_id, limit=limit)
        return {
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant_id,
            "items": [],
            "count": 0,
        }

    monkeypatch.setattr(mod, "ds_list_review_queue", fake)
    out = await get_decision_review_queue(limit=25, user=_USER)
    assert out["count"] == 0
    assert seen == {"tenant_id": str(_USER.tenant_id), "limit": 25}


@pytest.mark.asyncio
async def test_non_authoritative_queue_fails_closed(monkeypatch):
    async def fake(*, tenant_id=None, limit=100):
        return {"authoritative": False, "persisted": False, "items": [], "count": 0}

    monkeypatch.setattr(mod, "ds_list_review_queue", fake)
    with pytest.raises(HTTPException) as exc:
        await get_decision_review_queue(limit=25, user=_USER)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_invalid_queue_contract_fails_closed(monkeypatch):
    async def fake(*, tenant_id=None, limit=100):
        return {
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant_id,
            "items": [],
            "count": 1,
        }

    monkeypatch.setattr(mod, "ds_list_review_queue", fake)
    with pytest.raises(HTTPException) as exc:
        await get_decision_review_queue(limit=25, user=_USER)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_service_down_becomes_503(monkeypatch):
    async def fake(*, tenant_id=None, limit=100):
        raise HTTPException(status_code=502, detail="down")

    monkeypatch.setattr(mod, "ds_list_review_queue", fake)
    with pytest.raises(HTTPException) as exc:
        await get_decision_review_queue(limit=25, user=_USER)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant,field,typed,embedded,allowed",
    [
        (str(_USER.tenant_id), "f", "s", None, True),
        (str(_USER.tenant_id), "f", None, "s", True),
        ("other", "f", "s", "s", False),
        (str(_USER.tenant_id), "other", "s", "s", False),
        (str(_USER.tenant_id), "f", "s", "other", False),
        (str(_USER.tenant_id), "f", None, None, False),
    ],
)
async def test_scoped_queue_proves_the_requested_scope(
    monkeypatch, tenant, field, typed, embedded, allowed
):
    async def fake(**kwargs):
        return {
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "count": 1,
            "items": [
                {"field_id": field, "season_id": typed, "decision_value": {"season_id": embedded}}
            ],
        }

    monkeypatch.setattr(mod, "ds_list_review_queue", fake)
    request = get_decision_review_queue(10, "f", "s", _USER)
    if allowed:
        assert (await request)["count"] == 1
    else:
        with pytest.raises(HTTPException) as exc:
            await request
        assert exc.value.status_code == 503
