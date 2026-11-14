"""Admin authorization follow-up (#1427): the denial log is tenant-scoped over real HTTP.

``GET /api/v1/admin/security/denials`` reads the in-process ring buffer of
``core.tenant_audit``. The PR claims two things about its HTTP responses: a caller sees only
its own tenant's denials, and events without tenant attribution are never returned to a
tenant user. The unit tests check ``TenantAuditLog`` directly and a source string of the
router. This file drives the real platform app instead: two tenants produce real 403
denials through ``require_permission``, unattributed events are recorded the way trusted
in-process diagnostics record them, and each tenant's auditor reads the endpoint.

The buffer is in memory by design (persistence is an open residual of the PR), so Postgres
is not on this path. Token revocation is: the app runs against the real Redis denylist that
auth writes, and a revoked auditor token is refused before it can read anything.

Run: ``TEST_REDIS_URL=… pytest -m integration tests_v9/test_platform_denial_log_scope_live.py``.
``AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1`` turns every skip into a failure.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED") == "1"
_REDIS_URL = os.getenv("TEST_REDIS_URL") or ""

if not _REDIS_URL and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1 without TEST_REDIS_URL: the denylist the"
        " platform reads would silently fall back to process memory."
    )

pytestmark.append(
    pytest.mark.skipif(not _REDIS_URL, reason="needs TEST_REDIS_URL (the live revocation store)")
)

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
_ENDPOINT = "/api/v1/admin/security/denials"


@pytest.fixture(scope="module")
def platform():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        if _CERTIFICATION_REQUIRED:
            raise
        pytest.skip("fastapi is not installed; the platform app cannot be built here")

    mp = pytest.MonkeyPatch()
    mp.setenv("REDIS_URL", _REDIS_URL)
    mp.delenv("DENYLIST_REDIS_URL", raising=False)
    mp.setenv("SAHOOL_ENV", "development")
    mp.setenv("SAHOOL_JWT_SECRET", os.getenv("JWT_SECRET") or "p" * 48)
    mp.delenv("JWT_PUBLIC_KEY", raising=False)
    mp.syspath_prepend(str(PLATFORM))
    try:
        import api.main as main
        from core.jwt_denylist import RedisDenylist
        from core.tenant_audit import AUDIT

        # The denylist is built at import, and in a shared pytest process api.main may
        # already have been imported by an earlier test with no REDIS_URL (memory). Build it
        # again from this test's live URL; get_current_user and routers/auth.py read
        # api.main._DENYLIST at call time, so this is the store the requests use. A fallback
        # to memory (Redis unreachable) would test nothing live, so it still fails here.
        mp.setattr(main, "_DENYLIST", main._build_denylist())
        assert isinstance(main._DENYLIST, RedisDenylist), type(main._DENYLIST).__name__
        # No lifespan: the endpoint reads memory, and the scheduler/outbox are off this path.
        yield {
            "client": TestClient(main.app, raise_server_exceptions=False),
            "m": main,
            "audit": AUDIT,
        }
    finally:
        mp.undo()


def _token(platform, tenant: str, role: str) -> tuple[str, dict]:
    from core.canonical_schemas import UserRole, UserSchema

    user_id = f"den-{role}-{uuid.uuid4().hex[:8]}"
    user = UserSchema(user_id=user_id, tenant_id=tenant, role=UserRole(role), name_ar="تدقيق")
    return user_id, {"Authorization": f"Bearer {platform['m'].create_token(user)}"}


def _read(platform, hdr: dict, **params) -> dict:
    r = platform["client"].get(_ENDPOINT, headers=hdr, params=params)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_each_tenant_reads_only_its_own_denials_and_never_unattributed_ones(platform):
    c, audit = platform["client"], platform["audit"]
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())

    # Real denials: callers without AUDIT_VIEW hit the endpoint and are refused (403).
    denied = {tenant_a: set(), tenant_b: set()}
    for tenant, role, times in ((tenant_a, "viewer", 3), (tenant_b, "worker", 2)):
        for _ in range(times):
            user_id, hdr = _token(platform, tenant, role)
            assert c.get(_ENDPOINT, headers=hdr).status_code == 403
            denied[tenant].add(user_id)

    # Unattributed events, recorded the way in-process diagnostics record them.
    marker = uuid.uuid4().hex[:8]
    audit.record("auth", user_id=f"system-{marker}")
    audit.record("permission", user_id=f"none-{marker}", tenant_id=None, action="x")
    audit.record("tenant_scope", user_id=f"empty-{marker}", tenant_id="", action="x")
    unattributed = {f"system-{marker}", f"none-{marker}", f"empty-{marker}"}

    for tenant, other in ((tenant_a, tenant_b), (tenant_b, tenant_a)):
        for role in ("owner", "manager", "platform_admin"):
            _, hdr = _token(platform, tenant, role)
            body = _read(platform, hdr)
            seen = body["denials"]
            assert {d["tenant_id"] for d in seen} <= {tenant}, (role, seen[:3])
            got = {d["user_id"] for d in seen}
            assert got == denied[tenant], (role, sorted(got ^ denied[tenant]))
            assert not got & (denied[other] | unattributed), role
            assert body["summary"]["total"] == len(denied[tenant])
            assert body["summary"]["by_kind"] == {"permission": len(denied[tenant])}

    # The whole buffer still holds every event: the scope is the response, not the store.
    everything = {r["user_id"] for r in audit.recent()}
    assert denied[tenant_a] | denied[tenant_b] | unattributed <= everything


def test_limit_applies_after_the_tenant_filter(platform):
    c = platform["client"]
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    order = []
    for tenant in (tenant_a, tenant_b, tenant_a, tenant_b):
        user_id, hdr = _token(platform, tenant, "viewer")
        assert c.get(_ENDPOINT, headers=hdr).status_code == 403
        order.append((tenant, user_id))
    _, auditor = _token(platform, tenant_a, "owner")
    newest_a = [u for t, u in order if t == tenant_a][-1]
    assert [d["user_id"] for d in _read(platform, auditor, limit=1)["denials"]] == [newest_a]


def test_a_revoked_auditor_token_reads_nothing(platform):
    import jwt
    import redis

    c = platform["client"]
    tenant = str(uuid.uuid4())
    _, hdr = _token(platform, tenant, "viewer")
    assert c.get(_ENDPOINT, headers=hdr).status_code == 403
    _, auditor = _token(platform, tenant, "owner")
    assert _read(platform, auditor)["summary"]["total"] == 1
    token = auditor["Authorization"].split(" ", 1)[1]
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    # Written straight to Redis under the key auth's ``revoke_jti`` writes on logout.
    store = redis.Redis.from_url(_REDIS_URL)
    try:
        store.setex(f"sahool:jti:revoked:{jti}", 60, "1")
    finally:
        store.close()
    r = c.get(_ENDPOINT, headers=auditor)
    assert r.status_code == 401, r.text[:200]
