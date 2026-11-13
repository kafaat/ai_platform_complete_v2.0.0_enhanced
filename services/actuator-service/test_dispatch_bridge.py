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

# بعد تفكيك P2، المساعدات تعيش في actuator_runtime.py — main.py يعيد التصدير بـ`import *`
# الذي لا يشمل أسماء الشرطة السفليّة، فكان التحميل عبر main.py فشلاً كامناً لا يراه CI.
_MAIN_PATH = Path(__file__).resolve().parent / "actuator_runtime.py"
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


# ── حالة النتيجة (صدق: نُشِر≠نُفِّذ) — TRANSPORT-ACK-MISLABELED-AS-EXECUTED-01 ──
def test_no_helper_labels_a_broker_ack_as_executed():
    """إقرارُ الوسيط ليس تنفيذاً: لا دالّة تُرجِم نجاحَ النشر إلى ``executed``.

    كانت ``_dispatch_outcome_status`` تفعل ذلك بلا مستدعٍ إنتاجيّ، وهذا الاختبار كان
    يُثبِّت التسمية بدل أن يكذّبها. والإيصال الحيّ يبقى ``accepted``/``failed``.
    """
    assert not hasattr(main, "_dispatch_outcome_status")
    source = (Path(main.__file__)).read_text(encoding="utf-8")
    assert '"executed"' not in source
    assert 'receipt_status = "accepted" if sent else "failed"' in source


# ── مخطّط تنفيذ الطلب (ACTUATOR-DISPATCH-CONSUMER) — نقيّ بلا شبكة ──
def test_plan_dispatch_send_when_valid_and_risk_allowed():
    item = {
        "command_payload": {
            "device_id": "valve-7",
            "command": "open",
            "risk_level": "low",
            "payload": {"duration_sec": 600},
        }
    }
    plan = main._plan_dispatch_execution(item, allowlist={"low", "medium"})
    assert plan == ("send", "valve-7", "open", {"duration_sec": 600})


def test_plan_dispatch_refuses_an_open_without_duration():
    """ACTUATOR-OPEN-WITHOUT-DURATION-01: طلبُ فتحٍ بلا مدّة ⇒ إيصال failed بسببه، لا نشر.

    بلا مدّة يبقى الصمّام مفتوحاً حتّى سقف البرنامج الثابت (30 دقيقة) — والإغلاق يمرّ بلا مدّة.
    """
    item = {"command_payload": {"device_id": "valve-7", "command": "open", "risk_level": "low"}}
    plan = main._plan_dispatch_execution(item, allowlist={"low", "medium"})
    assert plan == ("unsupported_command", "open_command_requires_duration_sec")
    item = {"command_payload": {"device_id": "valve-7", "command": "close", "risk_level": "low"}}
    assert main._plan_dispatch_execution(item, allowlist={"low"}) == (
        "send",
        "valve-7",
        "close",
        {},
    )


def test_plan_dispatch_refuses_declared_high_risk():
    """مخاطرة مُعلَنة خارج المسموح ⇒ رفض بإيصال failed (لا إرسال أعمى)."""
    item = {"command_payload": {"device_id": "v1", "command": "open", "risk_level": "high"}}
    plan = main._plan_dispatch_execution(item, allowlist={"low", "medium"})
    assert plan == ("refused_risk", "high")


def test_plan_dispatch_invalid_command_is_terminal_failed():
    assert main._plan_dispatch_execution({"command_payload": "not json"}, allowlist={"low"}) == (
        "invalid_command",
    )
    assert main._plan_dispatch_execution({}, allowlist={"low"}) == ("invalid_command",)


def test_plan_dispatch_undeclared_risk_is_sendable():
    """السلسلة محكومة أصلاً (مراجعة + تفويض) — غياب إعلان المخاطرة لا يحجب، إعلانها خارج
    المسموح هو الذي يحجب."""
    item = {"command_payload": {"device_id": "v1", "command": "close"}}
    assert main._plan_dispatch_execution(item, allowlist={"low"})[0] == "send"


def test_dispatch_tenants_csv_and_empty_means_idle():
    assert main._dispatch_tenants("t1, t2 ,,t3") == ["t1", "t2", "t3"]
    assert main._dispatch_tenants("") == []
    assert main._dispatch_tenants(None) == []


def test_dispatch_consumer_loop_is_wired_in_lifespan():
    """حارس توصيل ساكن: الحلقة موجودة ومربوطة خلف FEATURE_DISPATCH_ACTUATOR."""
    src = (Path(__file__).resolve().parent / "actuator_runtime.py").read_text()
    assert "async def dispatch_consumer_loop" in src
    assert "async def run_dispatch_consumer_once" in src
    assert "app.state.dispatch_task" in src
    assert "_dispatch_consumer_enabled(FEATURE_DISPATCH_ACTUATOR)" in src
    assert "/v1/execution-requests" in src
    assert "is_actuation_halted" in src


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))


def test_delivery_token_and_receipt_are_deterministic(monkeypatch):
    monkeypatch.setattr(main, "ACTUATOR_DELIVERY_TOKEN_KEY", "test-secret")
    t1 = main._delivery_token("tenant-1", "req-1")
    t2 = main._delivery_token("tenant-1", "req-1")
    assert t1 == t2 and len(t1) == 64
    assert main._delivery_token("tenant-1", "req-2") != t1
    assert main._receipt_id("req-1") == main._receipt_id("req-1")


def test_recovery_feed_is_polled_before_queued_feed():
    src = (Path(__file__).resolve().parent / "actuator_runtime.py").read_text()
    assert "/v1/execution-requests/recovery" in src
    assert src.index("/v1/execution-requests/recovery") < src.index(
        "/v1/execution-requests?state=queued"
    )
    assert "_delivery_token(tenant_id, req_id)" in src
    assert "_receipt_id(req_id)" in src


def test_plan_dispatch_rejects_target_device_mismatch():
    item = {
        "target_id": "pivot-expected",
        "command_payload": {"device_id": "pivot-other", "command": "irrigate", "risk_level": "low"},
    }
    assert main._plan_dispatch_execution(item, allowlist={"low"}) == (
        "target_mismatch",
        "pivot-expected",
        "pivot-other",
    )


def test_device_gate_accepts_only_fresh_online_actuator_for_same_tenant_and_field():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    record = {
        "tenant_id": "tenant-1",
        "type": "actuator",
        "field_id": "field-1",
        "status": "online",
        "last_seen_at": now - timedelta(seconds=30),
    }
    assert main._device_dispatch_gate(
        record,
        tenant_id="tenant-1",
        field_id="field-1",
        now=now,
        stale_seconds=900,
    ) == (True, "ok")


def test_device_gate_fails_closed_for_wrong_tenant_field_type_status_or_stale():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    base = {
        "tenant_id": "tenant-1",
        "type": "actuator",
        "field_id": "field-1",
        "status": "online",
        "last_seen_at": now - timedelta(seconds=30),
    }
    cases = [
        (None, "device_not_found"),
        ({**base, "tenant_id": "tenant-2"}, "device_tenant_mismatch"),
        ({**base, "field_id": "field-2"}, "device_field_mismatch"),
        ({**base, "type": "water_meter"}, "device_not_actuator"),
        ({**base, "status": "offline"}, "device_not_online"),
        ({**base, "last_seen_at": None}, "device_last_seen_missing"),
        ({**base, "last_seen_at": now - timedelta(seconds=901)}, "device_telemetry_stale"),
    ]
    for record, reason in cases:
        assert main._device_dispatch_gate(
            record,
            tenant_id="tenant-1",
            field_id="field-1",
            now=now,
            stale_seconds=900,
        ) == (False, reason)


def test_envelope_field_reaches_device_and_scoped_halt_checks():
    raw = {"device_id": "valve", "command": "close", "field_id": "pivot"}
    assert main._plan_dispatch_execution({"command_payload": raw}, allowlist={"low"}) == (
        "send",
        "valve",
        "close",
        {"field_id": "pivot"},
    )
    raw["payload"] = {"field_id": "east"}
    assert main._plan_dispatch_execution({"command_payload": raw}, allowlist={"low"}) == (
        "command_field_mismatch",
    )


def test_envelope_cannot_hide_nested_high_risk_even_as_json():
    import json

    raw = {
        "device_id": "valve",
        "command": "close",
        "risk_level": "low",
        "payload": {"risk_level": "high"},
    }
    for envelope in (raw, json.dumps(raw)):
        assert main._plan_dispatch_execution({"command_payload": envelope}, allowlist={"low"}) == (
            "refused_risk",
            "high",
        )


def test_consumer_halts_only_the_addressed_field(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    @asynccontextmanager
    async def acquire():
        yield object()

    # OPEN is used here. Whether a CLOSE should pass a halted field is pending the owner's ruling
    # on #1386; on this branch no caller passes command=, so a CLOSE is held like an OPEN.
    rows = [
        {
            "execution_request_id": field,
            "target_id": device,
            "command_payload": {
                "field_id": field,
                "command": "open_valve",
                "device_id": device,
                "payload": {"duration_sec": 60},
            },
        }
        for field, device in (("pivot-1", "valve-1"), ("pivot-2", "valve-2"))
    ]
    receipts = []

    async def decision(client, method, path, tenant, json_body=None):
        if method == "GET":
            return SimpleNamespace(
                status_code=200, json=lambda: {"items": [] if "recovery" in path else rows}
            )
        if path.endswith("/receipt"):
            receipts.append(json_body["receipt_status"])
        return SimpleNamespace(status_code=200)

    async def halted(conn, tenant, *, field_id=None, valve_id=None, **_kwargs):
        return field_id == "pivot-1", "field-stop"

    publish = AsyncMock(return_value=True)
    validate = AsyncMock(side_effect=lambda tenant, device, field: (True, "ok", field))
    monkeypatch.setattr(main, "_pool", SimpleNamespace(acquire=acquire))
    monkeypatch.setattr(main, "_decision_request", decision)
    monkeypatch.setattr(main, "_validate_dispatch_device", validate)
    monkeypatch.setattr(main, "is_actuation_halted", halted)
    monkeypatch.setattr(main, "send_mqtt_command", publish)
    monkeypatch.setattr(main, "ACTUATOR_DELIVERY_TOKEN_KEY", "fixture")
    assert asyncio.run(main.run_dispatch_consumer_once(None, "tenant", allowlist={"low"})) == 2
    assert [call.args[2] for call in validate.await_args_list] == ["pivot-1", "pivot-2"]
    assert receipts == ["failed", "accepted"]
    publish.assert_awaited_once()
    assert publish.await_args.args[:2] == ("valve-2", "open_valve")


def test_a_command_without_a_field_is_held_by_its_device_s_registered_field(monkeypatch):
    # Review HIGH: decision without field_id + device-only plan + command without field_id.
    # The consumer used to pass field_id=None to the scoped kill switch, so an OPEN was
    # published to a valve installed in a halted field.
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    @asynccontextmanager
    async def acquire():
        yield object()

    rows = [
        {
            "execution_request_id": "r1",
            "target_id": "valve-1",
            "command_payload": {
                "command": "open_valve",
                "device_id": "valve-1",
                "payload": {"duration_sec": 60},
            },
        }
    ]
    receipts = []

    async def decision(client, method, path, tenant, json_body=None):
        if method == "GET":
            return SimpleNamespace(
                status_code=200, json=lambda: {"items": [] if "recovery" in path else rows}
            )
        if path.endswith("/receipt"):
            receipts.append(json_body["receipt_payload"].get("device_validation"))
        return SimpleNamespace(status_code=200)

    scopes = []

    async def halted(conn, tenant, *, field_id=None, valve_id=None, **_kwargs):
        scopes.append(field_id)
        return field_id == "pivot-1", "field-stop"

    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "_pool", SimpleNamespace(acquire=acquire))
    monkeypatch.setattr(main, "_decision_request", decision)
    monkeypatch.setattr(
        main, "_validate_dispatch_device", AsyncMock(return_value=(True, "ok", "pivot-1"))
    )
    monkeypatch.setattr(main, "is_actuation_halted", halted)
    monkeypatch.setattr(main, "send_mqtt_command", publish)
    monkeypatch.setattr(main, "ACTUATOR_DELIVERY_TOKEN_KEY", "fixture")
    asyncio.run(main.run_dispatch_consumer_once(None, "tenant", allowlist={"low"}))
    assert scopes[-1] == "pivot-1"
    assert receipts == ["killswitch:field-stop"]
    publish.assert_not_awaited()


def _run_consumer_with(monkeypatch, command, device_field, halted_field=None):
    """Drive run_dispatch_consumer_once with one queued request; returns (receipts, publish)."""
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    @asynccontextmanager
    async def acquire():
        yield object()

    rows = [
        {
            "execution_request_id": "r1",
            "target_id": "valve-1",
            "command_payload": {
                "command": command,
                "device_id": "valve-1",
                "payload": {"duration_sec": 60},
            },
        }
    ]
    receipts = []

    async def decision(client, method, path, tenant, json_body=None):
        if method == "GET":
            return SimpleNamespace(
                status_code=200, json=lambda: {"items": [] if "recovery" in path else rows}
            )
        if path.endswith("/receipt"):
            receipts.append(json_body["receipt_payload"].get("device_validation"))
        return SimpleNamespace(status_code=200)

    async def halted(conn, tenant, *, field_id=None, valve_id=None, **_kwargs):
        return (halted_field is not None and field_id == halted_field), "field-stop"

    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "_pool", SimpleNamespace(acquire=acquire))
    monkeypatch.setattr(main, "_decision_request", decision)
    monkeypatch.setattr(
        main, "_validate_dispatch_device", AsyncMock(return_value=(True, "ok", device_field))
    )
    monkeypatch.setattr(main, "is_actuation_halted", halted)
    monkeypatch.setattr(main, "send_mqtt_command", publish)
    monkeypatch.setattr(main, "ACTUATOR_DELIVERY_TOKEN_KEY", "fixture")
    asyncio.run(main.run_dispatch_consumer_once(None, "tenant", allowlist={"low"}))
    return receipts, publish


def test_an_opening_command_to_a_device_with_no_registered_field_is_refused(monkeypatch):
    # Independent re-check (SAHOOL session), gap 1: neither the command nor the registry named
    # a field, so no field kill switch could hold the OPEN; it was accepted and published.
    receipts, publish = _run_consumer_with(monkeypatch, "open_valve", device_field=None)
    assert receipts == ["dispatch_field_unbound"]
    publish.assert_not_awaited()


def test_a_close_to_a_device_with_no_registered_field_is_still_published(monkeypatch):
    receipts, publish = _run_consumer_with(monkeypatch, "close_valve", device_field=None)
    assert receipts == ["ok"]
    publish.assert_awaited_once()


def test_field_ids_that_differ_only_by_whitespace_match_the_gate_and_the_kill_switch():
    # Independent re-check, gap 2: a registry value "pivot-1 " and a halt on "pivot-1 " let an
    # OPEN through because the gate and match_killswitch compared raw strings.
    from datetime import UTC, datetime

    from shared.actuation_killswitch import match_killswitch

    now = datetime.now(UTC)
    record = {
        "tenant_id": "t",
        "type": "actuator",
        "field_id": "pivot-1 ",
        "status": "online",
        "last_seen_at": now,
    }
    ok, reason = main._device_dispatch_gate(
        record, tenant_id="t", field_id="pivot-1", now=now, stale_seconds=600
    )
    assert (ok, reason) == (True, "ok")
    halted, _ = match_killswitch(
        [{"scope": "field", "field_id": "pivot-1 ", "active": True}], field_id="pivot-1"
    )
    assert halted
