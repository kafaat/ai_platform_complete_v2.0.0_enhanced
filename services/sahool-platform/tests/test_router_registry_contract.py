"""عقد استخراج تسجيل الراوترات إلى api/router_registry.register_routers (Track C).

العقد (يحفظ السلوك ويمنع الانحدار بعد تقليص main.py):
  ١) main.py لم يعد مركز تسجيل النطاقات: لا ``app.include_router`` ولا حلقة auto-reg فيه.
  ٢) main.py يفوّض عبر ``register_routers(app)``.
  ٣) router_registry موجود ويُصدّر الدالّة + مجموعة الاستثناء الصحيحة.
  ٤) عدد المسارات المُسجَّلة لم ينقص (أرضيّة انحدار) ووحدات api/routers/ مُمثَّلة.
  ٥) راوترات phase9-12 الحسّاسة ما زالت محميّة بتوكن خدمة على مستوى الراوتر.

ملاحظة موضع: وُضِع تحت services/sahool-platform/tests/ (تجمعه بوّابة Platform Unit
Tests فعليّاً) لا tests/api/ (لا تجمعها أيّ بوّابة دون تعديل ملفّ CI).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

API = os.path.join(CORE, "api")

# أرضيّة انحدار: المنصّة تُسجِّل مئات المسارات (٤٩٣ وقت الاستخراج). هبوط حادّ ⇒ كسر.
_MIN_ROUTES = 450
_PHASE_FILES = (
    "phase9_autonomous_farm_os.py",
    "phase10_continuous_learning.py",
    "phase11_federated_agents.py",
    "phase12_marketplace_ecosystem.py",
)


def _main_src() -> str:
    return open(os.path.join(API, "main.py"), encoding="utf-8").read()


def test_main_is_not_router_registration_center():
    src = _main_src()
    # ١) لا تضمين نطاقات مباشر ولا حلقة auto-reg في main.py.
    assert "app.include_router(" not in src, "main.py must not include routers directly anymore"
    assert "iter_modules(" not in src, "auto-reg loop must live in router_registry, not main.py"
    # ٢) التفويض عبر register_routers.
    assert "from api.router_registry import register_routers" in src
    assert "register_routers(app)" in src


def test_registry_module_contract():
    from api import router_registry

    assert callable(router_registry.register_routers)
    assert router_registry.ROUTER_AUTOREG_EXCLUDE == {"service_proxy"}


def test_registry_mounts_all_routers_without_regression():
    pytest.importorskip("fastapi")
    from api.main import app  # ينفّذ register_routers(app) فعليّاً

    paths = {getattr(r, "path", "") for r in app.routes}
    non_null = {p for p in paths if p}
    # ٤) عدد المسارات لم ينقص (أرضيّة) + النطاقات الأساسيّة حاضرة.
    assert len(non_null) >= _MIN_ROUTES, f"route regression: {len(non_null)} < {_MIN_ROUTES}"
    assert any("/api/v1/gis/cloud-native" in p for p in non_null), "auto-reg router (gis) missing"
    assert any(p.startswith("/v1/phase9/") for p in non_null), "phase9 not mounted"
    assert any(p.startswith("/v1/ecosystem") for p in non_null), "phase12 ecosystem not mounted"
    # service_proxy (مُستثنى من الحلقة، يُسجَّل صراحةً) — حاضر عبر نقاطه الداخليّة.
    assert any("/api/v1/edge" in p or "/internal" in p or "service" in p for p in non_null)


def test_phase9_12_routers_remain_service_token_protected():
    # ٥) لم يُضعِف الاستخراج أمن phase9-12: ما زالت محميّة بتوكن خدمة على مستوى الراوتر.
    for fname in _PHASE_FILES:
        src = open(os.path.join(API, fname), encoding="utf-8").read()
        assert "dependencies=[Depends(_require_service_token)]" in src, (
            f"{fname}: phase router lost router-level service-token guard"
        )
