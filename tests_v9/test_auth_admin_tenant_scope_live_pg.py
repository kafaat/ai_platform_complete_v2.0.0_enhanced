"""C-01: دور ``admin`` في خدمة auth مالكُ مستأجِرٍ لا مديرُ منصّة — على القاعدة الحقيقيّة.

**العطل المقيس (تدقيق المالك C-01):** ``GET /v1/auth/users`` كان يسرد مستخدمي **كلّ**
المستأجرين، و``PATCH …/role`` و``PATCH …/deactivate`` يكتبان أيّ ``user_id`` بلا
``tenant_id`` في شرط ``WHERE``. وRLS لا تحمي هذا المسار: ``main._acquire`` يضبط
``app.current_role='admin'`` على كلّ اتّصال، وسياسة ``user_self`` (v97) تفتح كلّ الصفوف
لذلك السياق. فكان أيّ مالكِ مستأجِر يقرأ ويعطّل ويُعيد تدوير أدوار مستأجِرٍ آخر.

**قرار المالك (2026-11-13):** ``admin`` = مالك المستأجِر، محصورٌ في مستأجِره؛
``platform_admin`` وحده عابرٌ للمستأجرين — وهو غير معروف في خدمة auth أصلاً.

يُقاس عبر التطبيق الحقيقيّ (TestClient ⇒ lifespan ⇒ مسبح asyncpg) بدورٍ مقيَّد
(NOSUPERUSER NOBYPASSRLS — حارس auth يرفض الإقلاع على غيره)، والزرع والقراءة بالدور
المدير. لا بديلَ اتّصال (FAKE-CONNECTION-ENFORCES-NOTHING-01).

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
و``AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1`` يجعل كلّ تخطٍّ فشلاً.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""

if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL"
        " — الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً حيّة ودوراً مقيَّداً",
    )
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MISSING_ID = 2_000_000_000  # لا صفّ بهذا المعرّف: مرجعُ «غير موجود» للمقارنة


def _load_auth_main():
    """نمط ``test_mfa_hardening_integration_v29_5``: الراوترات تستورد ``main`` باسمه."""
    from tests_v9.service_module import purge_generic_modules

    auth_dir = os.path.join(ROOT, "services/auth")
    for p in (ROOT, auth_dir):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, auth_dir)
    purge_generic_modules()
    spec = importlib.util.spec_from_file_location(
        "auth_main_admin_scope", os.path.join(auth_dir, "main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_admin_scope"] = m
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


@pytest.fixture(scope="module")
def world():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        if _CERTIFICATION_REQUIRED:
            raise
        pytest.skip("fastapi غير مثبّتة — تطبيق auth لا يُبنى هنا")

    role = _q(
        "SELECT rolsuper OR rolbypassrls AS bypass FROM pg_roles WHERE rolname = $1", _app_role()
    )
    assert role and not role[0]["bypass"], "دور TEST_DATABASE_URL يتجاوز RLS ⇒ لا يقيس شيئاً"

    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", _APP_DSN)
    mp.setenv("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0"))
    mp.setenv("JWT_SECRET", os.getenv("JWT_SECRET") or "z" * 48)
    mp.setenv("SAHOOL_ENV", "development")
    mp.setenv("ENFORCE_ADMIN_STEPUP_MFA", "false")
    mp.setenv("ADMIN_PASSWORD", "Bootstrap-Admin-Pass!2026")
    mp.delenv("JWT_PRIVATE_KEY", raising=False)
    mp.delenv("JWT_PUBLIC_KEY", raising=False)

    marker = uuid.uuid4().hex[:10]
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    seed = [
        ("admin_a", "admin", tenant_a),
        ("owner_a", "owner", tenant_a),
        ("farmer_a", "farmer", tenant_a),
        ("farmer_a2", "farmer", tenant_a),
        ("admin_b", "admin", tenant_b),
        ("owner_b", "owner", tenant_b),
        ("farmer_b", "farmer", tenant_b),
    ]
    users = {}
    for key, r, tenant in seed:
        email = f"c01-{key}-{marker}@example.invalid"
        row = _q(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id) "
            "VALUES ($1, 'x', $2, $3, $4::uuid) RETURNING id",
            email,
            f"C-01 {key}",
            r,
            tenant,
        )[0]
        users[key] = {"id": row["id"], "email": email, "role": r, "tenant": tenant}

    m = _load_auth_main()

    def token(key, role_override=None):
        u = users[key]
        tok, _ = m.create_access_token(
            u["id"], u["email"], role_override or u["role"], "C-01", u["tenant"]
        )
        return {"Authorization": f"Bearer {tok}"}

    try:
        with TestClient(m.app, raise_server_exceptions=False) as client:
            yield {
                "client": client,
                "m": m,
                "users": users,
                "token": token,
                "tenants": (tenant_a, tenant_b),
            }
    finally:
        mp.undo()
        # لا DELETE: حذفُ المستخدم يمسّ ``audit_log`` الملحَق فقط (append-only يرفضه).
        # المستأجِران جديدان لكلّ تشغيل فلا يتداخلان مع غيرهما؛ نعطّل الصفوف للنظافة.
        ids = [u["id"] for u in users.values()]
        _q("UPDATE users SET active = FALSE WHERE id = ANY($1::int[])", ids)


def _app_role() -> str:
    from urllib.parse import urlsplit

    return urlsplit(_APP_DSN).username or ""


def _row(user_id):
    return dict(
        _q("SELECT role, active, tenant_id::text AS tenant FROM users WHERE id=$1", user_id)[0]
    )


def test_admin_lists_only_its_own_tenant(world):
    c, users = world["client"], world["users"]
    r = c.get("/v1/auth/users", headers=world["token"]("admin_a"))
    assert r.status_code == 200, r.text[:200]
    got = {u["id"] for u in r.json()}
    want = {u["id"] for u in users.values() if u["tenant"] == world["tenants"][0]}
    assert got == want, f"admin A رأى مستخدمين خارج مستأجِره: {sorted(got - want)}"
    assert {u["tenant_id"] for u in r.json()} == {world["tenants"][0]}


def test_cross_tenant_role_change_is_indistinguishable_from_not_found(world):
    c, users = world["client"], world["users"]
    target = users["farmer_b"]["id"]
    hdr = world["token"]("admin_a")
    cross = c.patch(f"/v1/auth/users/{target}/role", params={"role": "viewer"}, headers=hdr)
    missing = c.patch(f"/v1/auth/users/{_MISSING_ID}/role", params={"role": "viewer"}, headers=hdr)
    assert cross.status_code == 404, cross.text[:200]
    assert (cross.status_code, cross.json()) == (missing.status_code, missing.json())
    assert _row(target)["role"] == "farmer", "الدور كُتِب عبر المستأجرين"


def test_cross_tenant_deactivate_is_indistinguishable_from_not_found(world):
    c, users = world["client"], world["users"]
    target = users["admin_b"]["id"]
    hdr = world["token"]("admin_a")
    cross = c.patch(f"/v1/auth/users/{target}/deactivate", headers=hdr)
    missing = c.patch(f"/v1/auth/users/{_MISSING_ID}/deactivate", headers=hdr)
    assert cross.status_code == 404, cross.text[:200]
    assert (cross.status_code, cross.json()) == (missing.status_code, missing.json())
    assert _row(target)["active"] is True, "حسابٌ في مستأجِر آخر عُطِّل"


def test_admin_cannot_grant_platform_admin_or_a_tenant_owner_role(world):
    c, users = world["client"], world["users"]
    target = users["farmer_a"]["id"]
    hdr = world["token"]("admin_a")
    # platform_admin ليس دوراً في auth: النموذج يرفضه قبل أيّ منطق.
    r = c.patch(f"/v1/auth/users/{target}/role", params={"role": "platform_admin"}, headers=hdr)
    assert r.status_code == 422, r.text[:200]
    # قاعدة الدعوة نفسها: لا يُمنَح دورُ مالكٍ/مشرف إلّا بإجراءٍ خارج صلاحيّة المستأجِر.
    for role in ("admin", "owner"):
        r = c.patch(f"/v1/auth/users/{target}/role", params={"role": role}, headers=hdr)
        assert r.status_code == 403, (role, r.text[:200])
    assert _row(target)["role"] == "farmer"


def test_admin_cannot_demote_or_disable_a_peer_tenant_owner(world):
    c, users = world["client"], world["users"]
    peer = users["owner_a"]["id"]
    hdr = world["token"]("admin_a")
    r = c.patch(f"/v1/auth/users/{peer}/role", params={"role": "viewer"}, headers=hdr)
    assert r.status_code == 403, r.text[:200]
    r = c.patch(f"/v1/auth/users/{peer}/deactivate", headers=hdr)
    assert r.status_code == 403, r.text[:200]
    assert _row(peer) == {"role": "owner", "active": True, "tenant": world["tenants"][0]}


def test_admin_manages_users_of_its_own_tenant(world):
    c, users = world["client"], world["users"]
    hdr = world["token"]("admin_a")
    target = users["farmer_a"]["id"]
    r = c.patch(f"/v1/auth/users/{target}/role", params={"role": "viewer"}, headers=hdr)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["role"] == "viewer"
    assert _row(target)["role"] == "viewer"
    other = users["farmer_a2"]["id"]
    r = c.patch(f"/v1/auth/users/{other}/deactivate", headers=hdr)
    assert r.status_code == 200, r.text[:200]
    assert _row(other)["active"] is False


def test_non_admin_is_forbidden(world):
    c, users = world["client"], world["users"]
    hdr = world["token"]("farmer_b")
    target = users["admin_b"]["id"]
    assert c.get("/v1/auth/users", headers=hdr).status_code == 403
    r = c.patch(f"/v1/auth/users/{target}/role", params={"role": "viewer"}, headers=hdr)
    assert r.status_code == 403
    assert c.patch(f"/v1/auth/users/{target}/deactivate", headers=hdr).status_code == 403
    # platform_admin غير معروف في auth: لا يمنح أيّ وصولٍ ضمنيّ عابر للمستأجرين.
    pa = world["token"]("admin_b", role_override="platform_admin")
    assert c.get("/v1/auth/users", headers=pa).status_code == 403


def test_bootstrap_admin_is_scoped_to_its_own_tenant(world):
    """``_ensure_admin_user`` (lifespan) يُنشئ مالكَ مستأجِرٍ جديدٍ فارغ، لا مديراً عابراً."""
    c, m = world["client"], world["m"]
    row = _q(
        "SELECT id, role, tenant_id::text AS tenant FROM users WHERE email = $1", "admin@sahool.ye"
    )
    assert row, "lifespan لم يُنشئ المدير التأسيسيّ رغم ADMIN_PASSWORD"
    boot = dict(row[0])
    assert boot["role"] == "admin" and boot["tenant"], boot
    assert boot["tenant"] not in world["tenants"]
    tok, _ = m.create_access_token(boot["id"], "admin@sahool.ye", "admin", "boot", boot["tenant"])
    r = c.get("/v1/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text[:200]
    assert {u["tenant_id"] for u in r.json()} == {boot["tenant"]}
    seeded = {u["id"] for u in world["users"].values()}
    assert not seeded & {u["id"] for u in r.json()}


def test_tenant_provisioning_fails_closed_for_every_tenant_role(world):
    """C-35: POST /v1/auth/tenants is platform onboarding; no tenant role may call it.

    The owner and admin of each of two tenants, a farmer, and a forged ``platform_admin``
    claim all get 403 ``platform_admin_required``, and no user row is created. Without a
    token the caller is 401. Provisioning reopens only with a verifiable platform-admin
    identity (owner decision 2026-11-13).
    """
    c = world["client"]
    marker = uuid.uuid4().hex[:10]
    callers = [
        world["token"]("owner_a"),
        world["token"]("admin_a"),
        world["token"]("owner_b"),
        world["token"]("admin_b"),
        world["token"]("farmer_b"),
        world["token"]("admin_b", role_override="platform_admin"),
    ]
    for i, hdr in enumerate(callers):
        email = f"c35-{i}-{marker}@example.invalid"
        r = c.post(
            "/v1/auth/tenants",
            json={"owner_email": email, "owner_full_name": "C-35", "tenant_name": "c35"},
            headers=hdr,
        )
        assert r.status_code == 403, (i, r.status_code, r.text[:200])
        assert r.json()["detail"]["code"] == "platform_admin_required"
        assert not _q("SELECT 1 FROM users WHERE email = $1", email), "a tenant was provisioned"
    r = c.post(
        "/v1/auth/tenants",
        json={"owner_email": f"c35-anon-{marker}@example.invalid", "owner_full_name": "C-35"},
    )
    assert r.status_code == 401, r.text[:200]


def test_user_management_routes_are_the_three_scoped_ones(world):
    """أيّ مسارٍ جديد تحت ``/v1/auth/users`` يجب أن يمرّ بمراجعة النطاق قبل أن يُضاف هنا."""
    routes = {
        (method, r.path)
        for r in world["m"].app.routes
        if getattr(r, "path", "").startswith("/v1/auth/users")
        for method in getattr(r, "methods", ())
    }
    assert routes == {
        ("GET", "/v1/auth/users"),
        ("PATCH", "/v1/auth/users/{user_id}/role"),
        ("PATCH", "/v1/auth/users/{user_id}/deactivate"),
    }
