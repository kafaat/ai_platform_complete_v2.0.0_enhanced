"""Durability, contention and lease cleanup admission on a real SQLite database."""

from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/realtime-session"))
contracts = importlib.import_module("realtime_session.contracts")
Session = contracts.Session
SessionError = contracts.SessionError
SessionStore = importlib.import_module("realtime_session.store").SessionStore
sys.path.remove(str(ROOT / "services/realtime-session"))


def lease(number=1, **changes):
    session = Session(
        session_id=f"session-{number}",
        room_name=f"room-{number}",
        tenant_id="tenant-a",
        user_id=f"user-{number}",
        field_id="field-a",
        created_at=100,
        expires_at=200,
        status="PENDING",
    )
    return replace(session, **changes)


async def initialized(tmp_path, **kwargs):
    store = SessionStore(tmp_path / "leases.sqlite", **kwargs)
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_reopening_the_database_preserves_server_owned_session_state(tmp_path):
    store = await initialized(tmp_path)
    original = lease()
    await store.reserve(original, 100)
    await store.activate(original.session_id, 101)
    restarted = SessionStore(tmp_path / "leases.sqlite")
    await restarted.initialize()
    assert await restarted.get(original.session_id) == replace(original, status="ACTIVE"), (
        "A process restart must preserve active room ownership and expiration"
    )


@pytest.mark.asyncio
async def test_concurrent_store_instances_cannot_exceed_tenant_capacity(tmp_path):
    stores = [SessionStore(tmp_path / "shared.sqlite") for _ in range(12)]
    await asyncio.gather(*(store.initialize() for store in stores))
    results = await asyncio.gather(
        *(store.reserve(lease(i), 100) for i, store in enumerate(stores)),
        return_exceptions=True,
    )
    admitted = [result for result in results if result is None]
    rejected = [result for result in results if isinstance(result, SessionError)]
    assert len(admitted) == 2, "Atomic quota admission permits exactly two tenant leases"
    assert len(rejected) == 10 and all(error.status == 429 for error in rejected), (
        "Contending stores must reject excess leases instead of racing quota counts"
    )


@pytest.mark.asyncio
async def test_actor_capacity_is_scoped_by_tenant_and_shared_across_instances(tmp_path):
    first = await initialized(tmp_path, max_per_tenant=10)
    second = SessionStore(tmp_path / "leases.sqlite", max_per_tenant=10)
    results = await asyncio.gather(
        first.reserve(lease(1, user_id="same-user"), 100),
        second.reserve(lease(2, user_id="same-user"), 100),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 1, (
        "A shared actor may reserve only one lease even through different store objects"
    )
    await second.reserve(lease(3, user_id="same-user", tenant_id="tenant-b"), 100)
    assert (await first.get("session-3")).tenant_id == "tenant-b", (
        "Identical actor identifiers in different tenants do not share capacity"
    )


@pytest.mark.asyncio
async def test_expiration_and_failed_room_cleanup_do_not_release_quota(tmp_path):
    store = await initialized(tmp_path, max_per_tenant=1)
    await store.reserve(lease(), 100)
    await store.activate("session-1", 101)
    for now in (200, 500):
        with pytest.raises(SessionError) as denied:
            await store.reserve(lease(2, created_at=now, expires_at=now + 100), now)
        assert denied.value.status == 429, (
            "A token or lease expiring does not prove the participant was disconnected"
        )
    await store.closing("session-1")
    # Model a failed SFU delete by retaining CLOSING without confirming closed().
    restarted = SessionStore(tmp_path / "leases.sqlite", max_per_tenant=1)
    assert (await restarted.cleanup_candidates(500))[0].status == "CLOSING", (
        "Failed external cleanup remains retryable after a restart"
    )
    with pytest.raises(SessionError) as denied:
        await restarted.reserve(lease(3, created_at=500, expires_at=600), 500)
    assert denied.value.status == 429, "A failed delete must continue consuming tenant quota"
    await restarted.closed("session-1")
    await restarted.reserve(lease(3, created_at=500, expires_at=600), 500)


@pytest.mark.asyncio
async def test_state_transitions_reject_expired_activation_and_premature_closure(tmp_path):
    store = await initialized(tmp_path)
    await store.reserve(lease(), 100)
    with pytest.raises(SessionError) as expired:
        await store.activate("session-1", 200)
    assert expired.value.status == 409, "Expired pending leases cannot issue active room access"
    with pytest.raises(SessionError) as premature:
        await store.closed("session-1")
    assert premature.value.status == 409, "Pending leases require external cleanup before closure"
    await store.closing("session-1")
    with pytest.raises(SessionError):
        await store.activate("session-1", 101)
    assert (await store.closing("session-1")).status == "CLOSING", (
        "Repeated cleanup claims retain the closing state"
    )
    assert (await store.closed("session-1")).status == "CLOSED", (
        "Confirmed external deletion releases a closing lease"
    )
    assert (await store.closed("session-1")).status == "CLOSED", (
        "Repeated confirmed cleanup is idempotent"
    )
    assert (await store.closing("session-1")).status == "CLOSED", (
        "Cleanup must never reopen a closed lease"
    )


@pytest.mark.asyncio
async def test_cleanup_uses_pending_grace_expiration_and_closing_state(tmp_path):
    store = await initialized(tmp_path, max_per_tenant=10)
    await store.reserve(lease(1, created_at=95), 100)
    await store.reserve(lease(2, created_at=90), 100)
    await store.reserve(lease(3, expires_at=110), 100)
    await store.activate("session-3", 101)
    await store.reserve(lease(4), 100)
    await store.closing("session-4")
    await store.reserve(lease(5), 100)
    await store.closing("session-5")
    await store.closed("session-5")
    assert {s.session_id for s in await store.cleanup_candidates(100)} == {
        "session-2",
        "session-4",
    }, "Young pending, unexpired active and confirmed closed leases are not cleanup candidates"
    assert "session-3" in {s.session_id for s in await store.cleanup_candidates(110)}, (
        "Expiration at the exact lease deadline schedules external room removal"
    )


@pytest.mark.asyncio
async def test_database_failures_surface_safe_dependency_errors(tmp_path):
    store = SessionStore(tmp_path)
    with pytest.raises(SessionError) as unavailable:
        await store.initialize()
    assert unavailable.value.status == 503, "An unusable database path fails closed"
    assert unavailable.value.code == "session_store_unavailable", (
        "The public dependency error does not disclose filesystem or SQLite details"
    )


@pytest.mark.asyncio
async def test_missing_sessions_cannot_be_activated_or_closed(tmp_path):
    store = await initialized(tmp_path)
    assert await store.get("missing") is None, "Missing sessions have no implicit state"
    for operation in (
        store.activate("missing", 100),
        store.closing("missing"),
        store.closed("missing"),
    ):
        with pytest.raises(SessionError) as missing:
            await operation
        assert missing.value.status == 404 and missing.value.code == "session_not_found", (
            "Missing session transitions cannot fabricate or reopen a lease"
        )
