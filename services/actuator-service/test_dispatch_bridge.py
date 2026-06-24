#!/usr/bin/env python3
"""اختبارات نقيّة لجسر القرار→التنفيذ (Shard 3) في خدمة المُشغّلات.

نختبر دوالّ القرار النقيّة فقط (العلم · قائمة المخاطر · فكّ الأمر · حالة النتيجة)
بلا لمس MQTT/DB — نفس فلسفة test_dedup_compensation.py: مسار MQTT/DB غير قابل
للاختبار وحدويّاً بسهولة، فالقرار مفصول في دوالّ نقيّة ونُختبرها هي. المطالبة الذرّيّة
(queued→dispatched عبر FOR UPDATE SKIP LOCKED) ضمان قاعدة، يُتحقَّق منه تكامليّاً.

ملاحظة صدق: استيراد main.py يستلزم aiomqtt (قد يغيب)، فنُموّهه قبل الاستيراد.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

if "aiomqtt" not in sys.modules:
    try:
        import aiomqtt  # noqa: F401
    except ImportError:
        _stub = types.ModuleType("aiomqtt")
        _stub.Client = object
        sys.modules["aiomqtt"] = _stub

os.environ.setdefault("ACTUATOR_DEDUP_WINDOW_SEC", "60")

_MAIN_PATH = Path(__file__).resolve().parent / "main.py"
_spec = importlib.util.spec_from_file_location("actuator_main_dispatch_test", _MAIN_PATH)
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)


# ── العلم default-OFF (الحارس الأوّل) ─────────────────────────────
def test_flag_off_by_default():
    """غياب العلم / قيمة مجهولة ⇒ معطّل (fail-closed) — مسار الإنسان يبقى المستهلك."""
    for off in (None, "", "0", "off", "no", "false", "nope", " "):
        assert main._dispatch_consumer_enabled(off) is False


def test_flag_on_explicit():
    """قيم التفعيل الصريحة فقط ⇒ مُفعَّل."""
    for on in ("1", "true", "TRUE", "yes", "on", " on "):
        assert main._dispatch_consumer_enabled(on) is True


# ── قائمة المخاطر (الحارس الثالث: HIGH/CRITICAL لا تُؤتمت) ──────────
def test_risk_allowlist_default_excludes_high_critical():
    """الافتراضيّ low,medium — HIGH/CRITICAL مستبعَدتان (تبقيان للإنسان)."""
    allow = main._parse_risk_allowlist(None)
    assert allow == {"low", "medium"}
    assert main._is_risk_allowed("low", allow) is True
    assert main._is_risk_allowed("MEDIUM", allow) is True
    assert main._is_risk_allowed("high", allow) is False
    assert main._is_risk_allowed("critical", allow) is False
    assert main._is_risk_allowed(None, allow) is False  # risk مجهول ⇒ لا يُؤتمت


def test_risk_allowlist_custom_and_blank():
    """CSV مخصّص يُحترَم؛ فارغ ⇒ يعود للافتراضيّ."""
    assert main._parse_risk_allowlist("low") == {"low"}
    assert main._parse_risk_allowlist("low, high ") == {"low", "high"}
    assert main._parse_risk_allowlist("   ") == {"low", "medium"}


# ── فكّ الأمر (fail-safe: فاسد ⇒ None ⇒ failed) ───────────────────
def test_parse_command_valid_dict_and_json():
    """dict صالح أو JSON نصّيّ ⇒ (device, cmd, payload)؛ المفاتيح متسامحة."""
    out = main._parse_dispatch_command(
        {"device_id": "valve-1", "command": "open_valve", "payload": {"duration_sec": 600}}
    )
    assert out == ("valve-1", "open_valve", {"duration_sec": 600})
    # JSON نصّيّ (asyncpg يُعيد JSONB كنصّ) + أسماء بديلة device/cmd
    out2 = main._parse_dispatch_command('{"device": "pump-2", "cmd": "start"}')
    assert out2 == ("pump-2", "start", {})


def test_parse_command_malformed_returns_none():
    """أمر فاسد/ناقص ⇒ None (⇐ failed، لا إطلاق أعمى)."""
    assert main._parse_dispatch_command(None) is None
    assert main._parse_dispatch_command("not json") is None
    assert main._parse_dispatch_command(42) is None
    assert main._parse_dispatch_command({}) is None  # لا device/cmd
    assert main._parse_dispatch_command({"device_id": "v1"}) is None  # لا cmd
    assert main._parse_dispatch_command({"command": "open"}) is None  # لا device
    assert main._parse_dispatch_command({"device_id": "", "command": "open"}) is None


def test_parse_command_payload_defaults_to_empty():
    """payload غير-قاموس/غائب ⇒ {} (لا رمي)."""
    assert main._parse_dispatch_command({"device_id": "v1", "command": "open"}) == (
        "v1",
        "open",
        {},
    )
    assert main._parse_dispatch_command(
        {"device_id": "v1", "command": "open", "payload": "bad"}
    ) == ("v1", "open", {})


# ── حالة النتيجة (صدق: نُشِر≠نُفِّذ) ───────────────────────────────
def test_outcome_status():
    """نجاح النشر ⇒ executed (نُشِر للوسيط، لا تأكيد فيزيائيّ)؛ فشل ⇒ failed."""
    assert main._dispatch_outcome_status(True) == "executed"
    assert main._dispatch_outcome_status(False) == "failed"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
