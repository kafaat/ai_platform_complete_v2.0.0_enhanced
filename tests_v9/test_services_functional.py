"""اختبار functional للخدمات المفردة ضد Postgres حقيقي (جوانب لم تُختبَر سابقاً).

يركّز على:
  • soil-service: تحقّق end-to-end من إصلاح H5 (محاذاة الأعمدة + NPK) — إدخال
    قراءة بـNPK واسترجاعها عبر المخطّط الفعلي (temperature_c/nitrogen_mg_kg…).
  • guardrails-engine: إنفاذ توكن الخدمة على /validate (إصلاح L5 + fail-closed).

يعمل بطريقتين:
  • pytest -m integration   (يتخطّى تلقائيّاً إن لم تتوفّر قاعدة البيانات)
  • python3 tests_v9/test_services_functional.py   (تشغيل مستقل)
"""
import importlib.util
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-svc-token-xyz")
os.environ.setdefault("SAHOOL_ENV", "development")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pytest


def _db_available() -> bool:
    try:
        import asyncio

        import asyncpg
        async def _ping():
            c = await asyncpg.connect(os.environ["DATABASE_URL"]); await c.close()
        asyncio.run(_ping()); return True
    except Exception:
        return False


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m


def _run_checks():
    from fastapi.testclient import TestClient
    P, F = [], []
    def ck(n, c, d=""):
        (P if c else F).append(n); print(f"  {'✓' if c else '✗'} {n}" + (f" — {d}" if d and not c else ""))

    print("\n══ soil-service: H5 end-to-end (NPK + schema alignment) ══")
    sys.path.insert(0, os.path.join(ROOT, "services/soil-service")); sys.path.insert(0, ROOT)
    soil = _load("services/soil-service/main.py", "soil_main")
    TOK = {"x-agent-token": os.environ["SAHOOL_AGENT_TOKEN"]}
    with TestClient(soil.app) as c:
        payload = {
            "field_id": "rls_func_fieldH5", "sensor_id": "sensorH5",
            "temperature": 24.5, "moisture_pct": 31.0, "ph_level": 6.8,
            "ec_level": 1.4, "n_ppm": 45.0, "p_ppm": 12.5, "k_ppm": 88.0,
            "tenant_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        }
        r = c.post("/soil/ingest", json=payload, headers=TOK)
        ck("ingest قراءة تربة بـNPK = 200 [H5]", r.status_code == 200, f"{r.status_code}: {r.text[:160]}")
        ck("ingest يُرجع status=ingested", r.json().get("status") == "ingested" if r.status_code == 200 else False)

        r = c.get("/soil/readings/rls_func_fieldH5")
        ck("read القراءات = 200 (SELECT بالأعمدة الفعليّة) [H5]", r.status_code == 200, f"{r.status_code}: {r.text[:160]}")
        rows = r.json() if r.status_code == 200 else []
        row = rows[0] if isinstance(rows, list) and rows else {}
        ck("القراءة المُسترجَعة تحوي حقول NPK", all(k in row for k in ("n_ppm", "p_ppm", "k_ppm")), f"keys={list(row)[:9]}")
        ck("NPK تدور كاملةً (n=45,p=12.5,k=88) [H5]",
           float(row.get("n_ppm") or -1) == 45.0 and float(row.get("p_ppm") or -1) == 12.5 and float(row.get("k_ppm") or -1) == 88.0,
           f"n={row.get('n_ppm')} p={row.get('p_ppm')} k={row.get('k_ppm')}")
        ck("الحقول الأساسيّة تدور (temperature/ph/ec/moisture)",
           float(row.get("temperature") or -1) == 24.5 and float(row.get("ph_level") or -1) == 6.8,
           f"temp={row.get('temperature')} ph={row.get('ph_level')}")
        r = c.post("/soil/ingest", json=payload)
        ck("ingest بلا توكن خدمة مرفوض (401/403/422)", r.status_code in (401, 403, 422), f"{r.status_code}")

    print("\n══ guardrails-engine: إنفاذ توكن /validate (L5 + fail-closed) ══")
    sys.path.insert(0, os.path.join(ROOT, "services/guardrails-engine"))
    gr = _load("services/guardrails-engine/main.py", "gr_main")
    with TestClient(gr.app, raise_server_exceptions=False) as c:
        r = c.get("/healthz")
        ck("guardrails /healthz = 200", r.status_code == 200, f"{r.status_code}")
        r = c.post("/validate", json={}, headers={})
        ck("/validate بلا توكن خدمة مرفوض (401/422)", r.status_code in (401, 422), f"{r.status_code}")
        r = c.post("/validate", json={}, headers={"x-agent-token": "wrong"})
        ck("/validate بتوكن خاطئ ⇒ 401 [L5]", r.status_code in (401, 422), f"{r.status_code}")
    return P, F


@pytest.mark.integration
def test_services_functional():
    if not _db_available():
        pytest.skip("DATABASE_URL غير متاح — اختبار تكامل")
    P, F = _run_checks()
    assert not F, f"فشل: {F}"


if __name__ == "__main__":
    P, F = _run_checks()
    print("\n────────────────────────────────────────────")
    print(f"  SERVICES FUNCTIONAL: {len(P)} نجاح | {len(F)} فشل")
    for n in F: print(f"    ✗ {n}")
    print("────────────────────────────────────────────")
    sys.exit(1 if F else 0)
