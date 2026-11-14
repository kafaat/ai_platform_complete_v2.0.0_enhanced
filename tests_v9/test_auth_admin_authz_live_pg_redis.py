"""Admin authorization follow-up (#1427): the pre-merge gates, on real Postgres and Redis.

The PR body makes two gates mandatory before merge: two-tenant role, denial and invitation
tests on a real Postgres and Redis, "including concurrent acceptance and Redis outage". The
tenant scope of the three team routes is proven in ``test_auth_admin_tenant_scope_live_pg.py``;
this file proves the rest of the auth side through the real app (TestClient => lifespan =>
asyncpg pool as a NOBYPASSRLS role, redis.asyncio client):

* **Concurrent acceptance.** Two accepts of one invitation token are held on the invitation
  row lock by a third transaction and released together. Exactly one creates the member; the
  other is refused, and one user row and one consumed invitation remain.
* **Redis outage.** A role change and a deactivate revoke the target's sessions before the
  account row changes. With revocation unavailable (Redis down since boot, Redis unreachable
  mid-flight, or Redis refusing the revocation writes), each returns 503 and the row is
  unchanged. With Redis up, the same calls succeed and the target's refresh tokens and older
  access tokens stop working.
* **Reads during the outage (owner decision, 14 November 2026).** With Redis unreachable
  mid-flight, ``GET /v1/auth/users`` and ``GET /v1/auth/me`` answer 200 and the list stays
  scoped to the caller's tenant; a stale owner is still refused (403) because membership is
  read from Postgres. The writes above stay 503.
* **Stale membership.** A signed owner/admin token whose DB membership is inactive, demoted,
  of another role or of another tenant gets 403, on the team routes and on invitations.

The denial-log scope lives in sahool-platform and is proven in
``test_platform_denial_log_scope_live.py``.

Run: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… TEST_REDIS_URL=… pytest -m integration``.
``AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1`` turns every skip into a failure.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import sys
import threading
import time
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import redis
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")
    redis = pytest.importorskip("redis", reason="redis is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
_REDIS_URL = os.getenv("TEST_REDIS_URL") or ""
_LIVE = bool(_ADMIN_DSN and _APP_DSN and _REDIS_URL)

if not _LIVE and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL,"
        " TEST_DATABASE_URL and TEST_REDIS_URL: the job certifies with nothing to certify on."
    )

pytestmark.append(
    pytest.mark.skipif(
        not _LIVE,
        reason="needs TEST_DATABASE_ADMIN_URL, TEST_DATABASE_URL and TEST_REDIS_URL"
        " (a live database, a restricted role and a live Redis)",
    )
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PASSWORD = "Live-Authz-Pass!2026"
_CONSUMED = "دعوة غير صالحة أو مستهلَكة"


def _load_auth_main():
    """The routers import ``main`` by name (pattern of the tenant-scope live test)."""
    from tests_v9.service_module import purge_generic_modules

    auth_dir = os.path.join(ROOT, "services/auth")
    for p in (ROOT, auth_dir):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, auth_dir)
    purge_generic_modules()
    spec = importlib.util.spec_from_file_location(
        "auth_main_admin_authz", os.path.join(auth_dir, "main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_admin_authz"] = m
    sys.modules["main"] = m
    spec.loader.exec_module(m)
    return m


async def _admin_fetch(sql, *args):
    conn = await asyncpg.connect(_ADMIN_DSN, statement_cache_size=0)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def _q(sql, *args):
    return asyncio.run(_admin_fetch(sql, *args))


def _app_role() -> str:
    from urllib.parse import urlsplit

    return urlsplit(_APP_DSN).username or ""


def _closed_port() -> int:
    """A local port with nothing listening (bound, then released)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def world():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        if _CERTIFICATION_REQUIRED:
            raise
        pytest.skip("fastapi is not installed; the auth app cannot be built here")

    role = _q(
        "SELECT rolsuper OR rolbypassrls AS bypass FROM pg_roles WHERE rolname = $1", _app_role()
    )
    assert role and not role[0]["bypass"], "the TEST_DATABASE_URL role bypasses RLS"
    store = redis.Redis.from_url(_REDIS_URL, decode_responses=True)
    assert store.ping(), "TEST_REDIS_URL does not answer"

    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", _APP_DSN)
    mp.setenv("REDIS_URL", _REDIS_URL)
    mp.setenv("JWT_SECRET", os.getenv("JWT_SECRET") or "z" * 48)
    mp.setenv("SAHOOL_ENV", "development")
    mp.setenv("ENFORCE_ADMIN_STEPUP_MFA", "false")
    mp.delenv("JWT_PRIVATE_KEY", raising=False)
    mp.delenv("JWT_PUBLIC_KEY", raising=False)

    m = _load_auth_main()
    marker = uuid.uuid4().hex[:10]
    tenants = (str(uuid.uuid4()), str(uuid.uuid4()))
    password_hash = m.hash_password(_PASSWORD, 4)
    created: list[int] = []

    def new_user(role: str, tenant: str | None = None, *, active: bool = True) -> dict:
        tenant = tenant or tenants[0]
        email = f"authz-{role}-{uuid.uuid4().hex[:8]}-{marker}@example.com"
        row = _q(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active) "
            "VALUES ($1, $2, 'authz live', $3, $4::uuid, $5) RETURNING id",
            email,
            password_hash,
            role,
            tenant,
            active,
        )[0]
        created.append(row["id"])
        return {"id": row["id"], "email": email, "role": role, "tenant": tenant}

    def bearer(user: dict, *, role: str | None = None, tenant: str | None = None) -> dict:
        tok, _ = m.create_access_token(
            user["id"], user["email"], role or user["role"], "authz live", tenant or user["tenant"]
        )
        return {"Authorization": f"Bearer {tok}"}

    try:
        with TestClient(m.app, raise_server_exceptions=False) as client:
            assert m._redis is not None, "the auth app booted without Redis"
            yield {
                "client": client,
                "m": m,
                "store": store,
                "tenants": tenants,
                "new_user": new_user,
                "bearer": bearer,
                "marker": marker,
            }
    finally:
        mp.undo()
        store.close()
        # No DELETE: audit_log is append-only and references users. Fresh tenants per run.
        if created:
            _q("UPDATE users SET active = FALSE WHERE id = ANY($1::int[])", created)


def _row(user_id):
    return dict(
        _q("SELECT role, active, tenant_id::text AS tenant FROM users WHERE id=$1", user_id)[0]
    )


def _sessions(world, user: dict):
    """A refresh token in the real Redis and an access token issued before any revocation."""
    refresh = world["client"].portal.call(
        world["m"].create_refresh_token, user["id"], user["tenant"]
    )
    assert refresh, "Redis is up, yet no refresh token was issued"
    return refresh, world["bearer"](user)


def _assert_sessions_alive(world, user: dict, refresh: str, access: dict):
    store = world["store"]
    assert store.exists(f"sahool:refresh:{refresh}") == 1
    assert refresh in store.smembers(f"sahool:user:refreshset:{user['id']}")
    assert store.get(f"sahool:user:token_floor:{user['id']}") is None
    assert world["client"].get("/v1/auth/me", headers=access).status_code == 200


# ── concurrent invitation acceptance ────────────────────────────────────────


def _invite(world, inviter: dict, email: str, role: str = "farmer") -> dict:
    r = world["client"].post(
        "/v1/auth/invitations",
        json={"email": email, "role": role},
        headers=world["bearer"](inviter),
    )
    assert r.status_code == 201, r.text[:300]
    return r.json()


def _accept(world, token: str, name: str):
    return world["client"].post(
        "/v1/auth/invitations/accept",
        json={"token": token, "password": _PASSWORD, "full_name": name},
    )


def test_two_simultaneous_accepts_create_exactly_one_member(world):
    """Both accepts are parked on the invitation row lock, then released together."""
    owner = world["new_user"]("owner")
    email = f"authz-invitee-{uuid.uuid4().hex[:8]}-{world['marker']}@example.com"
    inv = _invite(world, owner, email)

    loop = asyncio.new_event_loop()
    blocker = loop.run_until_complete(asyncpg.connect(_ADMIN_DSN, statement_cache_size=0))
    results: dict[str, object] = {}
    threads = [
        threading.Thread(
            target=lambda n=n: results.__setitem__(n, _accept(world, inv["token"], n)),
            name=f"accept-{n}",
        )
        for n in ("first", "second")
    ]
    try:
        tx = blocker.transaction()
        loop.run_until_complete(tx.start())
        loop.run_until_complete(
            blocker.execute("SELECT 1 FROM invitations WHERE id = $1 FOR UPDATE", inv["id"])
        )
        for t in threads:
            t.start()
        # The first waiter queues on the blocker's transaction, the second on the first
        # waiter's tuple lock; both show as app-role backends waiting on a lock in the
        # invitation lookup.
        deadline = time.monotonic() + 30
        waiting = 0
        while time.monotonic() < deadline:
            waiting = _q(
                "SELECT count(*) AS n FROM pg_stat_activity WHERE usename = $1"
                " AND wait_event_type = 'Lock' AND query LIKE '%FROM invitations%FOR UPDATE%'",
                _app_role(),
            )[0]["n"]
            if waiting == 2:
                break
            time.sleep(0.05)
        assert waiting == 2, f"expected both accepts parked on the row lock, saw {waiting}"
        loop.run_until_complete(tx.commit())
    finally:
        # Closing the blocker also ends its transaction if an assertion left it open.
        loop.run_until_complete(blocker.close())
        loop.close()
        for t in threads:
            t.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "an accept never returned"
    responses = sorted(results.values(), key=lambda r: r.status_code)
    assert [r.status_code for r in responses] == [201, 400], [
        (r.status_code, r.text[:200]) for r in responses
    ]
    won, lost = responses
    assert lost.json()["detail"] == _CONSUMED

    members = _q(
        "SELECT id, role, tenant_id::text AS tenant, active FROM users WHERE email = $1", email
    )
    assert len(members) == 1, f"{len(members)} user rows for one invitation"
    assert dict(members[0]) == {
        "id": won.json()["user_id"],
        "role": "farmer",
        "tenant": owner["tenant"],
        "active": True,
    }
    state = _q("SELECT status, accepted_at FROM invitations WHERE id = $1", inv["id"])[0]
    assert state["status"] == "accepted" and state["accepted_at"] is not None

    # The consumed token stays consumed for any later caller.
    again = _accept(world, inv["token"], "late")
    assert (again.status_code, again.json()["detail"]) == (400, _CONSUMED)
    assert len(_q("SELECT 1 FROM users WHERE email = $1", email)) == 1


# ── Redis outage on a role change and on a deactivate ──────────────────────


def _change_role(world, actor: dict, target: dict):
    return world["client"].patch(
        f"/v1/auth/users/{target['id']}/role",
        params={"role": "viewer"},
        headers=world["bearer"](actor),
    )


def _deactivate(world, actor: dict, target: dict):
    return world["client"].patch(
        f"/v1/auth/users/{target['id']}/deactivate", headers=world["bearer"](actor)
    )


_OPERATIONS = {"role": _change_role, "deactivate": _deactivate}


@pytest.mark.parametrize("operation", sorted(_OPERATIONS))
def test_with_redis_up_the_change_lands_and_revokes_the_targets_sessions(world, operation):
    owner = world["new_user"]("owner")
    target = world["new_user"]("farmer")
    refresh, access = _sessions(world, target)
    _assert_sessions_alive(world, target, refresh, access)

    r = _OPERATIONS[operation](world, owner, target)
    assert r.status_code == 200, r.text[:300]

    want = {"role": "viewer", "active": True} if operation == "role" else {"active": False}
    assert {k: _row(target["id"])[k] for k in want} == want
    store = world["store"]
    assert store.exists(f"sahool:refresh:{refresh}") == 0, "refresh token survived"
    assert store.exists(f"sahool:user:refreshset:{target['id']}") == 0
    assert store.get(f"sahool:user:token_floor:{target['id']}") is not None
    me = world["client"].get("/v1/auth/me", headers=access)
    assert me.status_code == 401, "an access token issued before the change still works"
    again = world["client"].post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401, again.text[:200]


def _redis_down_since_boot(world, mp):
    # The lifespan leaves ``_redis`` as None when Redis is unreachable at start (dev/CI).
    mp.setattr(world["m"], "_redis", None)


def _redis_unreachable(world, mp):
    import redis.asyncio as aioredis

    mp.setattr(
        world["m"],
        "_redis",
        aioredis.from_url(
            f"redis://127.0.0.1:{_closed_port()}/0",
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
        ),
    )


def _redis_refuses_writes(world, mp):
    """Reads succeed (the caller's token checks pass) and the revocation writes fail."""
    import redis.asyncio as aioredis

    user, secret = f"authz_ro_{world['marker']}", uuid.uuid4().hex
    store = world["store"]
    store.execute_command(
        "ACL", "SETUSER", user, "reset", "on", f">{secret}", "~*", "+@read", "+ping"
    )
    mp.setattr(
        world["m"],
        "_redis",
        aioredis.from_url(
            _REDIS_URL, username=user, password=secret, encoding="utf-8", decode_responses=True
        ),
    )
    return lambda: store.execute_command("ACL", "DELUSER", user)


_OUTAGES = {
    "down_since_boot": _redis_down_since_boot,
    "unreachable": _redis_unreachable,
    "refuses_writes": _redis_refuses_writes,
}
# Which layer refuses, pinned by its message: the route's "no revocation backend" branch,
# the token check that cannot read the store, or the route's failed revocation write.
_REFUSAL = {
    "down_since_boot": "لا يمكن تعديل الحساب دون نظام إبطال الجلسات",
    "unreachable": "تعذّر التحقّق من إبطال التوكن — أعد المحاولة",
    "refuses_writes": "تعذّر إبطال الجلسات؛ لم يُعدّل الحساب",
}


@pytest.mark.parametrize("outage", sorted(_OUTAGES))
@pytest.mark.parametrize("operation", sorted(_OPERATIONS))
def test_revocation_unavailable_returns_503_and_leaves_the_account(world, operation, outage):
    owner = world["new_user"]("owner")
    target = world["new_user"]("farmer")
    refresh, access = _sessions(world, target)
    before = _row(target["id"])

    mp = pytest.MonkeyPatch()
    cleanup = None
    try:
        cleanup = _OUTAGES[outage](world, mp)
        r = _OPERATIONS[operation](world, owner, target)
    finally:
        mp.undo()
        if cleanup:
            cleanup()

    assert r.status_code == 503, (r.status_code, r.text[:300])
    assert r.json()["detail"] == _REFUSAL[outage]
    assert _row(target["id"]) == before, "the account changed although revocation was unavailable"
    # Nothing was revoked either: the change did not happen, and the target keeps its sessions.
    _assert_sessions_alive(world, target, refresh, access)


# ── safe reads while revocation is unreachable (owner decision, 14 November 2026) ──


def test_unreachable_redis_lets_get_users_through_scoped_to_the_callers_tenant(world):
    """Revocation state unknown + GET => 200 (was 503 since #1427), tenant scope unchanged.

    The same outage still refuses the role change and the deactivate with 503
    (``test_revocation_unavailable_returns_503_and_leaves_the_account[*-unreachable]``).
    """
    tenant_a, tenant_b = world["tenants"]
    owner = world["new_user"]("owner", tenant_a)
    mate = world["new_user"]("farmer", tenant_a)
    stranger = world["new_user"]("farmer", tenant_b)
    stale = world["new_user"]("owner", tenant_a, active=False)

    mp = pytest.MonkeyPatch()
    try:
        _redis_unreachable(world, mp)
        listed = world["client"].get("/v1/auth/users", headers=world["bearer"](owner))
        me = world["client"].get("/v1/auth/me", headers=world["bearer"](mate))
        stale_list = world["client"].get("/v1/auth/users", headers=world["bearer"](stale))
        write = _change_role(world, owner, mate)
    finally:
        mp.undo()

    assert listed.status_code == 200, (listed.status_code, listed.text[:300])
    rows = listed.json()
    assert {r["tenant_id"] for r in rows} == {tenant_a}, "a row from another tenant was listed"
    ids = {r["id"] for r in rows}
    assert {owner["id"], mate["id"]} <= ids
    assert stranger["id"] not in ids
    assert me.status_code == 200, (me.status_code, me.text[:300])
    assert me.json()["sub"] == str(mate["id"])
    # Membership is read from Postgres, not Redis: a deactivated owner still cannot list.
    assert stale_list.status_code == 403, (stale_list.status_code, stale_list.text[:300])
    # The write in the same outage keeps failing closed, and the row is unchanged.
    assert write.status_code == 503, (write.status_code, write.text[:300])
    assert write.json()["detail"] == _REFUSAL["unreachable"]
    assert _row(mate["id"])["role"] == "farmer"


# ── stale membership ─────────────────────────────────────────────────────────


def _stale_cases(world):
    """(label, signed claims, DB state behind them) — each one no longer an active manager."""
    nu = world["new_user"]
    other_tenant = world["tenants"][1]
    inactive = nu("owner", active=False)
    demoted = nu("farmer")
    swapped = nu("admin")
    moved = nu("owner", other_tenant)
    return [
        ("owner deactivated in DB", inactive, {}),
        ("admin demoted to farmer in DB", demoted, {"role": "admin"}),
        ("owner claim, admin in DB", swapped, {"role": "owner"}),
        ("owner of tenant B claiming tenant A", moved, {"tenant": world["tenants"][0]}),
    ]


def test_stale_membership_cannot_manage_the_team(world):
    c = world["client"]
    for label, actor, claims in _stale_cases(world):
        hdr = world["bearer"](actor, **claims)
        target = world["new_user"]("farmer")
        assert c.get("/v1/auth/users", headers=hdr).status_code == 403, label
        r = c.patch(f"/v1/auth/users/{target['id']}/role", params={"role": "viewer"}, headers=hdr)
        assert r.status_code == 403, (label, r.text[:200])
        r = c.patch(f"/v1/auth/users/{target['id']}/deactivate", headers=hdr)
        assert r.status_code == 403, (label, r.text[:200])
        assert _row(target["id"]) == {"role": "farmer", "active": True, "tenant": target["tenant"]}


def test_stale_membership_cannot_invite_list_or_revoke_invitations(world):
    c = world["client"]
    owner = world["new_user"]("owner")
    pending = _invite(world, owner, f"authz-pending-{uuid.uuid4().hex[:8]}@example.com")
    for label, actor, claims in _stale_cases(world):
        hdr = world["bearer"](actor, **claims)
        email = f"authz-stale-{uuid.uuid4().hex[:8]}-{world['marker']}@example.com"
        r = c.post("/v1/auth/invitations", json={"email": email, "role": "farmer"}, headers=hdr)
        assert r.status_code == 403, (label, r.status_code, r.text[:200])
        assert not _q("SELECT 1 FROM invitations WHERE email = $1", email), label
        assert c.get("/v1/auth/invitations", headers=hdr).status_code == 403, label
        r = c.delete(f"/v1/auth/invitations/{pending['id']}", headers=hdr)
        assert r.status_code == 403, (label, r.status_code, r.text[:200])
    assert _q("SELECT status FROM invitations WHERE id = $1", pending["id"])[0]["status"] == (
        "pending"
    )


def test_active_manager_control_for_the_stale_cases(world):
    """The same calls by an active owner succeed, so the 403s above are about membership."""
    c = world["client"]
    owner = world["new_user"]("owner")
    hdr = world["bearer"](owner)
    target = world["new_user"]("farmer")
    assert c.get("/v1/auth/users", headers=hdr).status_code == 200
    email = f"authz-ok-{uuid.uuid4().hex[:8]}-{world['marker']}@example.com"
    inv = _invite(world, owner, email)
    assert c.get("/v1/auth/invitations", headers=hdr).status_code == 200
    assert c.delete(f"/v1/auth/invitations/{inv['id']}", headers=hdr).status_code == 200
    r = c.patch(f"/v1/auth/users/{target['id']}/role", params={"role": "viewer"}, headers=hdr)
    assert r.status_code == 200, r.text[:200]
