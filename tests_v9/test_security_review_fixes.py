"""حُرّاس إصلاحات المراجعة الأمنيّة (تعاقُد على المصدر) — تُنفَّذ في CI بلا خدمات.

تثبّت ثلاثة إصلاحات حرجة/عالية من المراجعة الأمنيّة، بقراءة المصدر مباشرةً (لا استيراد
الخدمات الثقيلة) كي تُنفَّذ في بوّابة `-m unit` الخفيفة:

  #1 (🔴) actuator /command: فحص الدور + ملكيّة الجهاز للمستأجِر (fail-closed).
  #2 (🟠) raster prescription/change: توكن خدمة إلزاميّ (مطابقة الشقيقات).
  #3 (🟠) RLS: سياسة tenant_isolation صارت بـWITH CHECK (عزل الكتابة) + نشرها v70.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _func_body(src: str, name: str) -> str:
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    return src[start : (start + 1 + nxt.start()) if nxt else len(src)]


# ── #1 actuator: تحكّم بالأجهزة محروس بالدور + الملكيّة ──
def test_actuator_command_authorizes_device_control():
    from actuator_route_source import actuator_combined_source

    # مُعالِج /command نُقل إلى routers/ بالتفكيك المحفوظ-السلوك — امسح main.py + routers/.
    src = actuator_combined_source(ROOT)
    body = _func_body(src, "send_command")
    assert "_authorize_device_control(claims, req.device_id)" in body, (
        "/command لا يستدعي حارس التحكّم بالأجهزة"
    )


def test_actuator_guard_checks_role_and_ownership():
    from actuator_route_source import actuator_combined_source

    # P1 decomposition: الحارس انتقل إلى actuator_runtime.py — نمسح main.py + الشقيقات.
    src = actuator_combined_source(ROOT)
    guard = _func_body(src, "_authorize_device_control")
    # فحص الدور (owner/manager فقط) ⇒ 403
    assert "_DEVICE_CONTROL_ROLES" in guard and "403" in guard, "لا يفحص الدور"
    # ملكيّة الجهاز عبر iot_devices.tenant_id ⇒ 404 عند عدم التطابق
    assert "FROM iot_devices WHERE device_id" in guard, "لا يتحقّق من ملكيّة الجهاز"
    assert "404" in guard, "لا يردّ 404 للجهاز غير المملوك"
    # fail-closed عند تعذّر التحقّق (لا pool/خطأ) ⇒ 503
    assert "503" in guard, "لا يفشل مغلقاً عند تعذّر التحقّق"


def test_actuator_control_roles_are_owner_manager_only():
    from actuator_route_source import actuator_combined_source

    # P1 decomposition: الأدوار انتقلت إلى actuator_runtime.py — نمسح main.py + الشقيقات.
    src = actuator_combined_source(ROOT)
    m = re.search(r"_DEVICE_CONTROL_ROLES\s*=\s*\{([^}]*)\}", src)
    assert m, "_DEVICE_CONTROL_ROLES غير معرّف"
    roles = m.group(1)
    assert '"owner"' in roles and '"manager"' in roles
    for low in ("viewer", "worker", "agronomist"):
        assert f'"{low}"' not in roles, f"{low} يجب ألّا يملك تحكّماً فيزيائيّاً"


# ── #2 raster: نقطتان كانتا بلا توكن صارتا محروستين ──
def _signature(body: str) -> str:
    """جزء التوقيع قبل أوّل docstring/سطر منطقيّ (يحوي البارامترات)."""
    return body.split('"""')[0]


def test_raster_prescription_requires_service_token():
    from raster_route_source import raster_combined_source

    src = raster_combined_source(ROOT)  # main.py + routers/ (بعد التفكيك)
    body = _func_body(src, "field_prescription")
    assert "x_agent_token" in _signature(body), "التوقيع لا يقبل x_agent_token"
    # متسامح مع التفاف ruff للنداء على أسطر: ``main._require_service_token(\n x_agent_token )``.
    assert re.search(r"_require_service_token\(\s*x_agent_token", body), (
        "prescription بلا فرض توكن خدمة"
    )


def test_raster_change_requires_service_token():
    from raster_route_source import raster_combined_source

    src = raster_combined_source(ROOT)  # main.py + routers/ (بعد التفكيك)
    body = _func_body(src, "field_change")
    assert "x_agent_token" in _signature(body), "التوقيع لا يقبل x_agent_token"
    assert re.search(r"_require_service_token\(\s*x_agent_token", body), "change بلا فرض توكن خدمة"


# ── #3 RLS: WITH CHECK لعزل الكتابة ──
def test_rls_helper_has_with_check():
    src = _read("migrations/v9_rls_tenant_isolation.sql")
    # السياسة الموحّدة في الدالّة المساعدة صارت بـWITH CHECK
    assert "WITH CHECK" in src, "سياسة tenant_isolation بلا WITH CHECK (عزل الكتابة مفقود)"
    # تبقى USING للقراءة فشل-مغلق
    assert "USING (" in src


def test_v70_propagates_with_check():
    src = _read("migrations/v70_rls_with_check_propagate.sql")
    assert "_sahool_apply_tenant_rls" in src, "v70 لا يُعيد تطبيق الدالّة المساعدة"
    assert "tenant_isolation" in src, "v70 لا يستهدف جداول سياسة العزل"
    # مُدرَج في MANIFEST
    manifest = _read("migrations/MANIFEST.txt")
    assert "v70_rls_with_check_propagate.sql" in manifest, "v70 غير مُدرَج في MANIFEST"


# ── #1 سلوكيّ: حارس التحكّم بالأجهزة (يتخطّى إن غابت تبعيّات actuator) ──
@pytest.fixture(scope="module")
def actuator():
    pytest.importorskip("aiomqtt")
    pytest.importorskip("asyncpg")
    pytest.importorskip("jwt")
    pytest.importorskip("fastapi")
    import importlib.util
    import sys

    path = os.path.join(ROOT, "services/actuator-service/main.py")
    # P1 decomposition: main.py يستورد وحدة شقيقة (actuator_runtime) — يجب أن يكون
    # مجلّد الخدمة على sys.path قبل exec_module.
    svc_dir = os.path.dirname(path)
    if svc_dir not in sys.path:
        sys.path.insert(0, svc_dir)
    stale = sys.modules.get("actuator_runtime")
    if stale is not None and os.path.dirname(getattr(stale, "__file__", "") or "") != svc_dir:
        sys.modules.pop("actuator_runtime", None)
    spec = importlib.util.spec_from_file_location("actuator_main_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # الحارس و_pool يعيشان في actuator_runtime — الحقن على وحدة الواجهة لا يصل
    # globals المنطق؛ نُرجِع وحدة الـruntime نفسها.
    return sys.modules["actuator_runtime"]


async def test_guard_rejects_low_role(actuator):
    from fastapi import HTTPException

    # viewer ⇒ 403 قبل أيّ وصول للقاعدة (فحص الدور أوّلاً).
    with pytest.raises(HTTPException) as e:
        await actuator._authorize_device_control({"role": "viewer", "tenant_id": "t1"}, "dev1")
    assert e.value.status_code == 403


async def test_guard_fails_closed_without_pool(actuator):
    from fastapi import HTTPException

    # owner لكن لا pool ⇒ 503 (لا تشغيل بلا تحقّق ملكيّة).
    actuator._pool = None
    with pytest.raises(HTTPException) as e:
        await actuator._authorize_device_control({"role": "owner", "tenant_id": "t1"}, "dev1")
    assert e.value.status_code == 503
