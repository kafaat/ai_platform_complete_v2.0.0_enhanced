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


def _load(path, name):
    """يُحمّل main.py لخدمة بمسارها، بعد تنظيف الوحدات العامّة.

    بدون التنظيف يلتقط `from routers.x import ...` حزمة `routers` الخاصّة بخدمة أخرى
    استُوردت قبله في العمليّة نفسها — ٢٤ خدمة تتشارك الاسم. النتيجة ليست فشلاً واضحاً
    دائماً بل قد تكون **نجاحاً كاذباً**؛ هنا ظهرت كـModuleNotFoundError: routers.readings
    أثناء تحميل soil-service بينما كانت `routers` هي حزمة auth.
    """
    from tests_v9.service_module import purge_generic_modules

    purge_generic_modules()
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    # تدقيق 2026-11-02: الراوترات تستورد ``main`` باسمه؛ بلا هذا الربط تُحمَّل نسخةٌ ثانية
    # لها ``_REQ_TENANT`` و``_pool`` خاصّان بها، فلا ترى ما ضبطه وسيطُ هذه النسخة ⇒
    # ``X-Tenant-Id required`` رغم إرسال الترويسة. العطلُ نفسُه الذي أُصلِح في Q5 (#1323).
    sys.modules["main"] = m
    spec.loader.exec_module(m)
    return m


def _run_checks():
    from fastapi.testclient import TestClient

    P, F = [], []

    def ck(n, c, d=""):
        (P if c else F).append(n)
        print(f"  {'✓' if c else '✗'} {n}" + (f" — {d}" if d and not c else ""))

    print("\n══ soil-service: H5 end-to-end (NPK + schema alignment) ══")
    sys.path.insert(0, os.path.join(ROOT, "services/soil-service"))
    sys.path.insert(0, ROOT)
    soil = _load("services/soil-service/main.py", "soil_main")
    tenant = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    # تدقيق 2026-11-02: الخدمة لا تأخذ المستأجِرَ من الجسم (قابلٌ للتزوير) بل من ترويسة
    # ``X-Tenant-Id`` التي تحقنها البوّابة، والقراءةُ تطلب توكن الخدمة كالاستيعاب. كان
    # الاختبار يُرسل الجسمَ وحده فيُرفَض بـ400/401 — فشلٌ ابتلعه ``xfail(strict=False)``.
    TOK = {"x-agent-token": os.environ["SAHOOL_AGENT_TOKEN"], "X-Tenant-Id": tenant}
    with TestClient(soil.app) as c:
        payload = {
            "field_id": "rls_func_fieldH5",
            "sensor_id": "sensorH5",
            "temperature": 24.5,
            "moisture_pct": 31.0,
            "ph_level": 6.8,
            "ec_level": 1.4,
            "n_ppm": 45.0,
            "p_ppm": 12.5,
            "k_ppm": 88.0,
            "tenant_id": tenant,
        }
        r = c.post("/v1/soil/ingest", json=payload, headers=TOK)
        ck(
            "ingest قراءة تربة بـNPK = 200 [H5]",
            r.status_code == 200,
            f"{r.status_code}: {r.text[:160]}",
        )
        ck(
            "ingest يُرجع status=ingested",
            r.json().get("status") == "ingested" if r.status_code == 200 else False,
        )

        r = c.get("/v1/soil/readings/rls_func_fieldH5", headers=TOK)
        ck(
            "read القراءات = 200 (SELECT بالأعمدة الفعليّة) [H5]",
            r.status_code == 200,
            f"{r.status_code}: {r.text[:160]}",
        )
        rows = r.json() if r.status_code == 200 else []
        row = rows[0] if isinstance(rows, list) and rows else {}
        ck(
            "القراءة المُسترجَعة تحوي حقول NPK",
            all(k in row for k in ("n_ppm", "p_ppm", "k_ppm")),
            f"keys={list(row)[:9]}",
        )
        ck(
            "NPK تدور كاملةً (n=45,p=12.5,k=88) [H5]",
            float(row.get("n_ppm") or -1) == 45.0
            and float(row.get("p_ppm") or -1) == 12.5
            and float(row.get("k_ppm") or -1) == 88.0,
            f"n={row.get('n_ppm')} p={row.get('p_ppm')} k={row.get('k_ppm')}",
        )
        ck(
            "الحقول الأساسيّة تدور (temperature/ph/ec/moisture)",
            float(row.get("temperature") or -1) == 24.5 and float(row.get("ph_level") or -1) == 6.8,
            f"temp={row.get('temperature')} ph={row.get('ph_level')}",
        )
        r = c.post("/v1/soil/ingest", json=payload)
        ck(
            "ingest بلا توكن خدمة مرفوض (401/403/422)",
            r.status_code in (401, 403, 422),
            f"{r.status_code}",
        )

    print("\n══ guardrails-engine: إنفاذ توكن /validate (L5 + fail-closed) ══")
    sys.path.insert(0, os.path.join(ROOT, "services/guardrails-engine"))
    gr = _load("services/guardrails-engine/main.py", "gr_main")
    with TestClient(gr.app, raise_server_exceptions=False) as c:
        r = c.get("/healthz")
        ck("guardrails /healthz = 200", r.status_code == 200, f"{r.status_code}")
        r = c.post("/v1/validate", json={}, headers={})
        ck(
            "/validate بلا توكن خدمة مرفوض (401/422)",
            r.status_code in (401, 422),
            f"{r.status_code}",
        )
        r = c.post("/v1/validate", json={}, headers={"x-agent-token": "wrong"})
        ck("/validate بتوكن خاطئ ⇒ 401 [L5]", r.status_code in (401, 422), f"{r.status_code}")
    return P, F


# SOIL_FUNCTIONAL_CERTIFICATION_REQUIRED=1 (خطوة CI المخصَّصة بالدور المقيَّد): كلّ تخطٍّ فشلٌ.
_CERTIFICATION_REQUIRED = os.getenv("SOIL_FUNCTIONAL_CERTIFICATION_REQUIRED") == "1"


def _skip_or_fail(message: str) -> None:
    if _CERTIFICATION_REQUIRED:
        pytest.fail(message)
    pytest.skip(message)


def _role_bypasses_rls() -> bool:
    """دورُ الاتّصال superuser أو BYPASSRLS؟ — حارس soil-service يرفض الإقلاع عليه بحقّ."""
    import asyncio

    import asyncpg

    async def _q():
        conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
        try:
            return await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        finally:
            await conn.close()

    return bool(asyncio.run(_q()))


# كان هنا ``xfail(strict=False)`` باسم AUTH-E2E-UNDER-RESTRICTED-ROLE (مُغلَقة): تحت الدور
# المقيَّد كان الاختبار يفشل بعطلَي حزامٍ لا بالدور — ``sys.modules['main']`` غير مربوط
# ونقصُ ترويسة ``X-Tenant-Id``/التوكن على القراءة — فيُقرأ «xfailed» أخضر. صار يُشغَّل فعلاً
# في خطوة CI مخصَّصة بالدور المقيَّد ``sahool_app_test``؛ وعلى دورٍ يتجاوز RLS يتخطّى مُعلِناً
# لأنّ ``assert_db_role_rls_safe`` يرفض الإقلاع — وهو السلوك الصحيح لا العيب.
@pytest.mark.integration
def test_services_functional():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        _skip_or_fail("fastapi غير مثبّتة — تطبيقا soil/guardrails لا يُبنيان هنا")
    if not _db_available():
        _skip_or_fail("DATABASE_URL غير متاح — اختبار تكامل")
    if _role_bypasses_rls():
        _skip_or_fail(
            "دور DATABASE_URL يتجاوز RLS (superuser/BYPASSRLS) ⇒ حارس soil-service يرفض "
            "الإقلاع بحقّ. شغّله بدورٍ مقيَّد (خطوة CI: soil-service functional, restricted role)."
        )
    P, F = _run_checks()
    assert not F, f"فشل: {F}"


if __name__ == "__main__":
    P, F = _run_checks()
    print("\n────────────────────────────────────────────")
    print(f"  SERVICES FUNCTIONAL: {len(P)} نجاح | {len(F)} فشل")
    for n in F:
        print(f"    ✗ {n}")
    print("────────────────────────────────────────────")
    sys.exit(1 if F else 0)
