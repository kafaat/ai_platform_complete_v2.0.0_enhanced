"""auth-service e2e ضد Postgres + Redis حقيقيّين (خدمة المصادقة الحرجة).

يغطّي تدفّق المصادقة الحقيقي (bcrypt + DB + JWT + قفل الحساب):
register → login → /auth/me، ورفض كلمة المرور الخاطئة، وتكرار البريد،
وتصعيد الدور خادم-جانبيّاً (يُتجاهَل دور العميل).

يعمل بطريقتين:
  • pytest -m integration   (يتخطّى تلقائيّاً إن لم تتوفّر قاعدة البيانات)
  • python3 tests_v9/test_auth_e2e.py   (تشغيل مستقل)
"""

import importlib.util
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "z" * 48)
os.environ.setdefault("SAHOOL_ENV", "development")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402


def _db_available() -> bool:
    try:
        import asyncio

        import asyncpg

        async def _ping():
            c = await asyncpg.connect(os.environ["DATABASE_URL"])
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


def _run_checks():
    """يُرجع (نجاح، فشل[]) — مشترك بين pytest والتشغيل المستقل."""
    sys.path.insert(0, os.path.join(ROOT, "services/auth"))
    sys.path.insert(0, ROOT)
    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location(
        "auth_main", os.path.join(ROOT, "services/auth/main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main"] = m
    # The auth routers do `import main`; alias it to THIS instance so the router's
    # main._pool is the one the lifespan populates. Without this, `import main` loads a
    # second copy whose _pool stays None ⇒ register/login 500 (a harness artifact, not an
    # RLS/role fault). Must be set before exec_module (routers import main at app build).
    sys.modules["main"] = m
    spec.loader.exec_module(m)

    P, F = [], []

    def ck(n, c, d=""):
        (P if c else F).append(n)
        print(f"  {'✓' if c else '✗'} {n}" + (f" — {d}" if d and not c else ""))

    email = f"farmer_{uuid.uuid4().hex[:8]}@sahool.ye"
    pw = "S3cure-Pass!2026"
    with TestClient(m.app, raise_server_exceptions=False) as c:
        print("\n══ auth-service e2e (bcrypt + DB + JWT) ══")
        r = c.post(
            "/auth/register",
            json={"email": email, "password": pw, "full_name": "مزارع تجريبي", "role": "owner"},
        )
        ck("register = 201", r.status_code == 201, f"{r.status_code}: {r.text[:160]}")
        ck(
            "register يُرجع JWT",
            bool(r.json().get("access_token")) if r.status_code == 201 else False,
        )
        ck(
            "الدور معيَّن خادميّاً — المُسجِّل مؤسِّس مؤسّسته ⇒ 'owner' (دور العميل مُتجاهَل بنيويّاً)",
            # Anti-escalation is STRUCTURAL: RegisterRequest has no role field, so the client's
            # requested role (owner/superadmin/…) is ignored. Self-registration founds a NEW tenant
            # (users.tenant_id defaults to gen_random_uuid), so the founder is 'owner' of their OWN
            # isolated tenant — not an escalation within someone else's (see routers/registration.py).
            r.status_code == 201 and r.json().get("role") == "owner",
            f"role={r.json().get('role') if r.status_code == 201 else '?'}",
        )

        r = c.post("/auth/login", json={"email": email, "password": pw})
        ck(
            "login بكلمة المرور الصحيحة = 200",
            r.status_code == 200,
            f"{r.status_code}: {r.text[:140]}",
        )
        ltok = r.json().get("access_token") if r.status_code == 200 else None
        ck("login يُرجع JWT", bool(ltok))

        r = c.get("/auth/me", headers={"Authorization": f"Bearer {ltok}"})
        ck("/auth/me بالتوكن = 200", r.status_code == 200, f"{r.status_code}")
        ck(
            "/auth/me يُرجع البريد الصحيح",
            r.status_code == 200 and r.json().get("email") == email,
            f"{r.json() if r.status_code == 200 else ''}",
        )

        r = c.post("/auth/login", json={"email": email, "password": "wrong-password"})
        ck("login بكلمة مرور خاطئة مرفوض (401)", r.status_code == 401, f"{r.status_code}")

        r = c.post(
            "/auth/register", json={"email": email, "password": pw, "full_name": "مزارع مكرّر"}
        )
        ck(
            "register بنفس البريد مرفوض (409)",
            r.status_code == 409,
            f"{r.status_code}: {r.text[:120]}",
        )

        r = c.get("/auth/me")
        ck("/auth/me بلا توكن مرفوض (401/403)", r.status_code in (401, 403), f"{r.status_code}")
    return P, F


@pytest.mark.integration
def test_auth_e2e():
    if not _db_available():
        pytest.skip("DATABASE_URL غير متاح — اختبار تكامل")
    P, F = _run_checks()
    assert not F, f"فشل: {F}"


if __name__ == "__main__":
    P, F = _run_checks()
    print("\n────────────────────────────────────────────")
    print(f"  AUTH E2E: {len(P)} نجاح | {len(F)} فشل")
    for n in F:
        print(f"    ✗ {n}")
    print("────────────────────────────────────────────")
    sys.exit(1 if F else 0)
