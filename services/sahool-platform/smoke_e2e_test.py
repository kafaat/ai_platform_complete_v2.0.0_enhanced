"""smoke + e2e للمنصّة الحيّة (قاعدة Postgres حقيقيّة عبر TestClient)."""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
os.environ.setdefault("SAHOOL_ENV", "development")
os.environ.setdefault("SAHOOL_JWT_SECRET", "x"*48)
_SVC = os.path.dirname(os.path.abspath(__file__))           # services/sahool-platform
_ROOT = os.path.dirname(os.path.dirname(_SVC))              # repo root (for `shared`)
sys.path.insert(0, _SVC); sys.path.insert(0, _ROOT)

from fastapi.testclient import TestClient
from api.main import app

P, F = [], []
def ck(n, cond, d=""):
    (P if cond else F).append(n); print(f"  {'✓' if cond else '✗'} {n}" + (f" — {d}" if d and not cond else ""))

with TestClient(app, raise_server_exceptions=False) as c:
    print("\n── SMOKE ──")
    r = c.get("/healthz"); ck("GET /healthz = 200", r.status_code == 200, f"{r.status_code}")
    ck("healthz body is dict", isinstance(r.json(), dict))
    r = c.get("/readyz"); ck("GET /readyz = 200 (DB pool ready)", r.status_code == 200, f"{r.status_code}")

    print("\n── E2E: auth (dev) → token → protected ──")
    r = c.post("/api/v1/auth/login", json={"user_id":"u-e2e","tenant_id":"11111111-1111-1111-1111-111111111111","role":"owner","name_ar":"مختبِر"})
    ck("login (dev) = 200", r.status_code == 200, f"{r.status_code}: {r.text[:120]}")
    tok = r.json().get("access_token") if r.status_code == 200 else None
    ck("login returns JWT", bool(tok))
    H = {"Authorization": f"Bearer {tok}"}

    r = c.get("/api/v1/confidence/ndvi", headers=H)  # GET on POST route → 405
    ck("protected route rejects no-body/ wrong method (405)", r.status_code in (405, 422))
    r = c.post("/api/v1/confidence/ndvi", headers=H, json={
        "ndvi_value":0.62,"observation_date":"2026-02-01","field_area_ha":3.0,
        "cloud_pct":5,"cloud_shadow_pct":0,"cirrus_pct":0,"has_ground_truth":False})
    ck("POST /confidence/ndvi (naive date) = 200 [H8 fix: no 500]", r.status_code == 200, f"{r.status_code}: {r.text[:160]}")
    if r.status_code == 200:
        ck("confidence returns a score", "confidence" in r.text or "score" in r.text or "level" in r.text)

    print("\n── E2E: no-token rejected (authz) ──")
    r = c.post("/api/v1/confidence/ndvi", json={"ndvi_value":0.5,"observation_date":"2026-02-01","field_area_ha":1.0,"cloud_pct":0,"cloud_shadow_pct":0,"cirrus_pct":0,"has_ground_truth":False})
    ck("no Authorization → 401/403", r.status_code in (401, 403), f"{r.status_code}")

    print("\n── E2E: H8 malformed date → 422 (not 500) ──")
    r = c.post("/api/v1/confidence/ndvi", headers=H, json={
        "ndvi_value":0.5,"observation_date":"not-a-date","field_area_ha":1.0,
        "cloud_pct":0,"cloud_shadow_pct":0,"cirrus_pct":0,"has_ground_truth":False})
    ck("malformed date → 422 (H8 fix)", r.status_code == 422, f"{r.status_code}")

    print("\n── E2E: DB-backed endpoint (real Postgres pool) ──")
    r = c.get("/api/v1/onboarding/questions", headers=H)
    ck("DB/compute endpoint reachable (not 503 pool-missing)", r.status_code in (200, 404, 422), f"{r.status_code}: {r.text[:120]}")

print("\n────────────────────────────────────────────")
print(f"  SMOKE+E2E: {len(P)} نجاح | {len(F)} فشل")
if F: [print(f"    ✗ {n}") for n in F]
print("────────────────────────────────────────────")
sys.exit(1 if F else 0)
