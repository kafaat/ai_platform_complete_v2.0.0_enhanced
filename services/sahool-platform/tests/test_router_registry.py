"""حارس: استخراج تسجيل الراوترات إلى api/router_registry.register_routers.

يؤكّد أنّ التسجيل المركزيّ (المُستخرَج من main.py لتقليص الوحدة الأحاديّة) يحفظ
السلوك: main.py يفوّض عبر register_routers(app)، والوحدة تُصدّر الدالّة + مجموعة
الاستثناء، وكلّ راوترات api/routers/ (+ مراحل 9-12 + service_proxy) تُضمَّن في app.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..")
if CORE not in sys.path:
    sys.path.insert(0, CORE)


def test_main_delegates_registration_to_registry():
    main_src = open(os.path.join(CORE, "api", "main.py"), encoding="utf-8").read()
    assert "from api.router_registry import register_routers" in main_src
    assert "register_routers(app)" in main_src
    # لم يعد main.py يحوي حلقة التسجيل التلقائيّ نفسها (انتقلت إلى router_registry).
    assert "iter_modules(" not in main_src, "auto-reg loop must live in router_registry, not main"


def test_registry_module_contract():
    from api import router_registry

    assert callable(router_registry.register_routers)
    assert router_registry.ROUTER_AUTOREG_EXCLUDE == {"service_proxy"}


def test_registry_mounts_all_routers_including_excluded_and_phases():
    pytest.importorskip("fastapi")
    from api.main import app  # تشغيل register_routers(app) فعليّاً

    paths = {getattr(r, "path", "") for r in app.routes}
    # service_proxy (مُستثنى من الحلقة، يُسجَّل صراحةً) — نقطة وكيل داخليّة حاضرة.
    assert any(p.startswith("/api/v1/edge") or "service" in p or "/internal" in p for p in paths)
    # مراحل 9-12 مُضمَّنة.
    assert any(p.startswith("/v1/phase9/") for p in paths)
    assert any(p.startswith("/v1/ecosystem") for p in paths)
    # راوتر اعتياديّ من api/routers/ مُضمَّن آليّاً (gis_cloud_native ذو البادئة).
    assert any("/api/v1/gis/cloud-native" in p for p in paths)
