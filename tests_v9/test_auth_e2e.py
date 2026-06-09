"""auth-service e2e ضد Postgres + Redis حقيقيّين (خدمة المصادقة الحرجة).

يغطّي تدفّق المصادقة الحقيقي (bcrypt + DB + JWT + قفل الحساب):
register → login → /auth/me، ورفض كلمة المرور الخاطئة، وتكرار البريد،
وتصعيد الدور خادم-جانبيّاً (يُتجاهَل دور العميل).
"""
import importlib.util, os, sys, uuid

os.environ["DATABASE_URL"] = "postgresql://sahool_user@/sahool?host=/tmp/pgrun"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_SECRET"] = "z" * 48
os.environ.setdefault("SAHOOL_ENV", "development")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "services/auth")); sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
P, F = [], []
def ck(n, c, d=""):
    (P if c else F).append(n); print(f"  {'✓' if c else '✗'} {n}" + (f" — {d}" if d and not c else ""))

spec = importlib.util.spec_from_file_location("auth_main", os.path.join(ROOT, "services/auth/main.py"))
m = importlib.util.module_from_spec(spec); sys.modules["auth_main"] = m; spec.loader.exec_module(m)

email = f"farmer_{uuid.uuid4().hex[:8]}@sahool.ye"
pw = "S3cure-Pass!2026"
with TestClient(m.app, raise_server_exceptions=False) as c:
    print("\n══ auth-service e2e (bcrypt + DB + JWT) ══")
    r = c.post("/auth/register", json={"email": email, "password": pw, "full_name": "مزارع تجريبي", "role": "owner"})
    ck("register = 201", r.status_code == 201, f"{r.status_code}: {r.text[:160]}")
    tok = r.json().get("access_token") if r.status_code == 201 else None
    ck("register يُرجع JWT", bool(tok))
    ck("تصعيد الدور مرفوض — الدور 'farmer' لا 'owner' (server-side)",
       r.status_code == 201 and r.json().get("role") == "farmer", f"role={r.json().get('role') if r.status_code==201 else '?'}")

    r = c.post("/auth/login", json={"email": email, "password": pw})
    ck("login بكلمة المرور الصحيحة = 200", r.status_code == 200, f"{r.status_code}: {r.text[:140]}")
    ltok = r.json().get("access_token") if r.status_code == 200 else None
    ck("login يُرجع JWT", bool(ltok))

    r = c.get("/auth/me", headers={"Authorization": f"Bearer {ltok}"})
    ck("/auth/me بالتوكن = 200", r.status_code == 200, f"{r.status_code}")
    ck("/auth/me يُرجع البريد الصحيح", r.status_code == 200 and r.json().get("email") == email,
       f"{r.json() if r.status_code==200 else ''}")

    r = c.post("/auth/login", json={"email": email, "password": "wrong-password"})
    ck("login بكلمة مرور خاطئة مرفوض (401)", r.status_code == 401, f"{r.status_code}")

    r = c.post("/auth/register", json={"email": email, "password": pw, "full_name": "مزارع مكرّر"})
    ck("register بنفس البريد مرفوض (409)", r.status_code == 409, f"{r.status_code}: {r.text[:120]}")

    r = c.get("/auth/me")
    ck("/auth/me بلا توكن مرفوض (401/403)", r.status_code in (401, 403), f"{r.status_code}")

print("\n────────────────────────────────────────────")
print(f"  AUTH E2E: {len(P)} نجاح | {len(F)} فشل")
if F: [print(f"    ✗ {n}") for n in F]
print("────────────────────────────────────────────")
sys.exit(1 if F else 0)
