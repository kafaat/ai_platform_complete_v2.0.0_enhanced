#!/usr/bin/env python3
"""Smoke test: يستورد تطبيق كل خدمة ويتحقّق من /healthz (و/readyz) عبر TestClient.

يميّز ثلاث حالات لكل خدمة:
  ✓ HEALTHY   — التطبيق يستورد و/healthz=200
  ~ SKIP(dep) — تبعيّة خارجيّة غير مثبّتة في هذه البيئة (ليست عيباً في الكود)
  ✗ FAIL      — استيراد مكسور أو /healthz ليس 200 (عيب حقيقي)

تشغيل مستقل: python3 tests_v9/smoke_services.py
"""

import importlib.util
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "smoke-token")
os.environ.setdefault("SAHOOL_ENV", "development")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (اسم العرض، مسار الوحدة، مجلّد إضافي للمسار)
SERVICES = [
    ("auth", "services/auth/main.py", "services/auth"),
    ("soil-service", "services/soil-service/main.py", "services/soil-service"),
    ("guardrails", "services/guardrails-engine/main.py", "services/guardrails-engine"),
    (
        "vegetation",
        "services/vegetation-analysis-service/main.py",
        "services/vegetation-analysis-service",
    ),
    ("supervisor", "services/supervisor-agent/main.py", "services/supervisor-agent"),
    ("raster-service", "services/raster-service/main.py", "services/raster-service"),
    ("weather-service", "services/weather-service/main.py", "services/weather-service"),
    ("indicators", "services/indicators-service/main.py", "services/indicators-service"),
    ("odoo-bridge", "services/odoo-bridge/main.py", "services/odoo-bridge"),
    ("agriai-engine", "services/agriai-engine/main.py", "services/agriai-engine"),
    ("actuator", "services/actuator-service/main.py", "services/actuator-service"),
    ("edge-inference", "services/edge-inference/main.py", "services/edge-inference"),
    ("local-ai-rag", "services/local-ai-rag/main.py", "services/local-ai-rag"),
    ("tts-service", "services/tts-service/main.py", "services/tts-service"),
    ("video-processor", "services/video-processor/main.py", "services/video-processor"),
    ("market-mcp", "services/mcp_servers/market_server.py", "services/mcp_servers"),
]

HEALTHY, SKIP, FAIL = [], [], []


def _load(modpath, extra):
    if extra and os.path.join(ROOT, extra) not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, extra))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location(
        f"smoke_{os.path.basename(modpath)}", os.path.join(ROOT, modpath)
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def smoke_one(name, modpath, extra):
    from fastapi.testclient import TestClient

    try:
        mod = _load(modpath, extra)
    except ModuleNotFoundError as e:
        missing = str(e).split("No module named")[-1].strip().strip("'\"")
        if missing.split(".")[0] not in {"shared"}:  # shared = packaging/path, not a true ext dep
            SKIP.append((name, f"dep: {missing}"))
            print(f"  ~ {name:16} SKIP (تبعيّة خارجيّة: {missing})")
            return
        FAIL.append((name, str(e)[:90]))
        print(f"  ✗ {name:16} FAIL import: {e}")
        return
    except Exception as e:
        FAIL.append((name, f"{type(e).__name__}: {str(e)[:80]}"))
        print(f"  ✗ {name:16} FAIL import: {type(e).__name__}: {str(e)[:80]}")
        return

    app = getattr(mod, "app", None)
    if app is None:
        FAIL.append((name, "no `app`"))
        print(f"  ✗ {name:16} FAIL: no FastAPI `app`")
        return
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/healthz")
            if r.status_code != 200:
                r = c.get("/health")
            ok = r.status_code == 200
            (HEALTHY if ok else FAIL).append((name, r.status_code))
            print(
                f"  {'✓' if ok else '✗'} {name:16} /healthz={r.status_code}"
                + ("" if ok else "  <-- FAIL")
            )
    except Exception as e:
        FAIL.append((name, f"{type(e).__name__}: {str(e)[:70]}"))
        print(f"  ✗ {name:16} FAIL health: {type(e).__name__}: {str(e)[:70]}")


def main():
    import subprocess

    # وضع الخدمة الواحدة: يُستدعى ضمن عمليّة فرعيّة معزولة
    if len(sys.argv) == 4 and sys.argv[1] == "--one":
        smoke_one(sys.argv[2], sys.argv[3], os.path.dirname(sys.argv[3]))
        if HEALTHY:
            print(f"RESULT:HEALTHY:/healthz={HEALTHY[0][1]}")
        elif SKIP:
            print(f"RESULT:SKIP:SKIP (تبعيّة: {SKIP[0][1]})")
        else:
            print(f"RESULT:FAIL:FAIL {FAIL[0][1] if FAIL else ''}")
        return 0 if not FAIL else 1

    print("\n══ Smoke test: health of importable services (عزل بعمليّة فرعيّة لكلّ خدمة) ══")
    h = s = f = 0
    for name, modpath, _extra in SERVICES:
        p = subprocess.run(
            [sys.executable, __file__, "--one", name, modpath],
            capture_output=True,
            text=True,
            env=os.environ,
        )
        # بروتوكول مخرجات نظيف: آخر سطر RESULT:<status>:<detail>
        res = next((ln for ln in reversed(p.stdout.splitlines()) if ln.startswith("RESULT:")), None)
        if res:
            _, status, detail = res.split(":", 2)
        else:
            status, detail = (
                "FAIL",
                ((p.stderr or p.stdout).strip().splitlines() or ["no output"])[-1][:90],
            )
        sym = {"HEALTHY": "✓", "SKIP": "~", "FAIL": "✗"}.get(status, "✗")
        print(f"  {sym} {name:16} {detail}")
        h += status == "HEALTHY"
        s += status == "SKIP"
        f += status == "FAIL"
    print("\n────────────────────────────────────────────")
    print(f"  SMOKE: {h} HEALTHY | {s} skip(dep) | {f} FAIL")
    print("────────────────────────────────────────────")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
