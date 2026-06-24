#!/usr/bin/env python3
"""اختبارات نقيّة لإحكام سلامة طبقة التنفيذ الفيزيائيّ (Actuator Safety Hardening).

يقفل: **آمن افتراضيّاً** — بلا متغيّرات بيئة ⇒ ACTUATOR_MODE=simulation وكلّ أعلام المسارات
معطّلة (لا نشر فيزيائيّ). الأعلام تُفعَّل بتعيين صريح فقط. /safety-status لا يكشف أسراراً.
نفس فلسفة test_dispatch_bridge: دوالّ قرار نقيّة + تحميل main.py عبر importlib مع تمويه aiomqtt.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

if "asyncpg" not in sys.modules:
    _asyncpg_stub = types.ModuleType("asyncpg")
    _asyncpg_stub.Pool = object

    async def _create_pool(*_args, **_kwargs):  # pragma: no cover - import stub only
        raise RuntimeError("asyncpg is stubbed in actuator safety unit tests")

    _asyncpg_stub.create_pool = _create_pool
    sys.modules["asyncpg"] = _asyncpg_stub

if "jwt" not in sys.modules:
    _jwt_stub = types.ModuleType("jwt")

    def _decode(*_args, **_kwargs):  # pragma: no cover - dependency override avoids this
        return {}

    _jwt_stub.decode = _decode
    sys.modules["jwt"] = _jwt_stub

if "aiomqtt" not in sys.modules:
    try:
        import aiomqtt  # noqa: F401
    except ImportError:
        _stub = types.ModuleType("aiomqtt")
        _stub.Client = object
        sys.modules["aiomqtt"] = _stub

# حاسم: لا نضبط ACTUATOR_MODE كي نختبر الافتراضيّ الآمن (simulation).
os.environ.pop("ACTUATOR_MODE", None)
os.environ.pop("FEATURE_AUTOMATION_RULES_ACTUATION", None)
os.environ.pop("FEATURE_MANUAL_ACTUATOR_COMMANDS", None)
os.environ.pop("FEATURE_DISPATCH_ACTUATOR", None)

_MAIN_PATH = Path(__file__).resolve().parent / "main.py"
_spec = importlib.util.spec_from_file_location("actuator_main_safety_test", _MAIN_PATH)
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)


# ── الادّعاء المركزيّ: آمن افتراضيّاً ────────────────────────────────
def test_default_mode_is_simulation_not_real():
    """بلا ACTUATOR_MODE ⇒ simulation (لا real مُستنتَج من وجود الوسيط) — fail-safe."""
    assert main.ACTUATOR_MODE == "simulation"


def test_all_path_flags_default_off():
    """كلّ أعلام المسارات معطّلة افتراضيّاً (لا تنفيذ بلا تفعيل صريح)."""
    for off in (None, "", "0", "off", "false", "no", "nope", " "):
        assert main._automation_actuation_enabled(off) is False
        assert main._manual_commands_enabled(off) is False
        assert main._dispatch_consumer_enabled(off) is False


def test_path_flags_require_explicit_opt_in():
    """التفعيل بقيم صريحة فقط."""
    for on in ("1", "true", "TRUE", "yes", "on", " on "):
        assert main._automation_actuation_enabled(on) is True
        assert main._manual_commands_enabled(on) is True


# ── /safety-status: حالة فقط، لا أسرار ──────────────────────────────
def test_safety_status_default_all_off():
    """الافتراضيّ: simulation + كلّ المسارات معطّلة + physical_execution_enabled=false."""
    s = main._safety_status("simulation", False, False, False)
    assert s["actuator_mode"] == "simulation"
    assert s["physical_execution_enabled"] is False
    assert s["dispatch_bridge_enabled"] is False
    assert s["automation_rules_enabled"] is False
    assert s["manual_command_enabled"] is False
    assert "warning" not in s  # لا تحذير ما لم يكن real


def test_safety_status_real_sets_physical_and_warning():
    """real ⇒ physical_execution_enabled=true + تحذير صاخب صريح."""
    s = main._safety_status("real", True, True, True)
    assert s["physical_execution_enabled"] is True
    assert "PHYSICAL ACTUATION ENABLED" in s["warning"]


def test_safety_status_exposes_no_secrets():
    """صدق أمنيّ: لا يكشف broker/tokens/tenant/secrets — حالة فقط."""
    s = main._safety_status("real", True, False, True)
    allowed = {
        "actuator_mode",
        "physical_execution_enabled",
        "dispatch_bridge_enabled",
        "automation_rules_enabled",
        "manual_command_enabled",
        "warning",
    }
    assert set(s).issubset(allowed)
    blob = repr(s).lower()
    for leak in ("mqtt://", "broker", "token", "secret", "tenant", "password"):
        assert leak not in blob


def test_health_does_not_expose_mqtt_broker_url():
    """/health يعلن أن MQTT مُهيّأ فقط، ولا يكشف broker URL."""
    import asyncio

    payload = asyncio.run(main.health())
    assert payload["mqtt_configured"] is True
    assert "mqtt" not in payload
    assert "mqtt://" not in repr(payload).lower()


def test_command_endpoint_flag_off_returns_explicit_safety_403():
    """POST /command بلا FEATURE_MANUAL_ACTUATOR_COMMANDS ⇒ 403 صريح قبل أي تشغيل."""
    from fastapi.testclient import TestClient

    async def _claims_override():
        return {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "sub": "u1",
            "role": "owner",
            "iss": "sahool-auth",
        }

    main.app.dependency_overrides[main._verify_token] = _claims_override
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/command",
                json={"device_id": "pump-1", "command": "start", "payload": {}},
            )
        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["error"] == "manual_actuator_commands_disabled_by_safety_policy"
    finally:
        main.app.dependency_overrides.clear()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
