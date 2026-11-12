#!/usr/bin/env python3
"""انحدارات حزمة سلامة المشغّلات A1–A5/A7 (تدقيق 2026-11-01، ② السلامة الفيزيائيّة).

كلّ اختبار يُشغّل الدالّة الحقيقيّة ويقيس **ما كان سيصل إلى MQTT** (أو ما نُشِر فعلاً عبر
عميلٍ مُموَّه في وضع real) — لا فحصاً نصّيّاً:

* A1 — ``ACTUATOR_MODE=real`` وحده لا يُطلق أتمتة القواعد: ``FEATURE_AUTOMATION_RULES_ACTUATION``.
* A2 — القاعدة لا تحرّك صمّاماً خارج حقل المستشعر، والمفتاح يُستشار بحقل **الصمّام** من السجلّ.
* A3 — المستأجر/الحقل من السجلّ لا من الموضوع؛ ``value`` مفقودة تُتجاهَل؛ ``trigger_duration_sec`` يُطبَّق.
* A4 — مفردات أوامر واحدة تُترجَم إلى OPEN/CLOSE عند حدّ MQTT؛ المجهول يُرفَض قبل النشر.
* A5 — إعادة نشر الاسترداد تحمل نفس ``ts``/``id`` فيكشفها البرنامج الثابت مكرّرة.
* A7 — النشر QoS 1 بلا retain.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

SERVICE = Path(__file__).resolve().parent
ROOT = SERVICE.parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"


def _stub_missing_dependencies() -> list[str]:
    inserted: list[str] = []
    for name, build in (
        ("asyncpg", lambda m: setattr(m, "Pool", object)),
        ("jwt", lambda m: setattr(m, "decode", lambda *_a, **_k: {})),
        ("aiomqtt", lambda m: setattr(m, "Client", object)),
    ):
        if name in sys.modules:
            continue
        try:
            __import__(name)
            continue
        except ImportError:
            pass
        stub = types.ModuleType(name)
        build(stub)
        sys.modules[name] = stub
        inserted.append(name)
    return inserted


@pytest.fixture
def act(monkeypatch):
    """``actuator_runtime`` محمَّلاً بنسخةٍ معزولة (لا تلوّث sys.modules للأجنحة الشقيقة)."""
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    saved = {k: sys.modules.get(k) for k in ("actuator_runtime", "routers", "routers.commands")}
    for name in saved:
        sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        mod._dedup_last_fired.clear()
        getattr(mod, "_trigger_since", {}).clear()
        monkeypatch.setattr(mod, "ACTUATOR_IDEMPOTENCY_MODE", "local")
        yield mod
    finally:
        for name in ("actuator_runtime", "routers", "routers.commands"):
            sys.modules.pop(name, None)
        for name, value in saved.items():
            if value is not None:
                sys.modules[name] = value
        for name in stubbed:
            sys.modules.pop(name, None)


# ── قاعدة بيانات صناعيّة: قواعد + سجلّ أجهزة (iot_devices) ────────────────
class _Conn:
    def __init__(self, db: _DB) -> None:
        self._db = db
        self._tenant: str | None = None

    def transaction(self):
        class _Tx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

        return _Tx()

    async def execute(self, sql, *args):
        if "set_config('app.current_tenant'" in sql:
            self._tenant = args[0]
        return "OK"

    async def fetch(self, sql, *args):
        self._db.rule_queries.append((sql, args))
        tenant, sensor = args[0], args[1]
        field = args[2] if len(args) > 2 else None
        out = []
        for r in self._db.rules:
            if r["_tenant"] != tenant or r["_sensor"] != sensor:
                continue
            if "field_id IS NULL OR field_id = $3" in sql and r["_field"] not in (None, field):
                continue
            out.append(r)
        return out

    async def fetchrow(self, sql, *args):
        row = self._db.devices.get(args[0])
        # RLS محاكى: سياق المستأجر يُخفي صفوف غيره (كما تفعل السياسة الحقيقيّة).
        if row is not None and self._tenant is not None and row["tenant_id"] != self._tenant:
            return None
        return row

    async def fetchval(self, *_a, **_k):
        return None


class _DB:
    def __init__(self) -> None:
        self.rules: list[dict] = []
        self.devices: dict[str, dict] = {}
        self.rule_queries: list = []

    def acquire(self):
        db = self

        class _Ctx:
            async def __aenter__(self):
                return _Conn(db)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()


def _rule(device="valve-a", *, field=None, duration=0, threshold=10, tenant=TENANT):
    return {
        "_tenant": tenant,
        "_sensor": "soil_moisture",
        "_field": field,
        "rule_id": f"rule-{device}",
        "trigger_operator": ">",
        "trigger_threshold": threshold,
        "trigger_duration_sec": duration,
        "action_device": device,
        "action_command": "open",
        "action_payload": {},
        "max_daily_runs": None,
        "cooldown_sec": 0,
        "last_triggered": None,
        "today_run_count": 0,
        "last_reset_date": None,
        "time_window_start": None,
        "time_window_end": None,
        "days_of_week": None,
    }


def _device(device_id, *, tenant=TENANT, field="field-9", kind="actuator"):
    return {"device_id": device_id, "tenant_id": tenant, "type": kind, "field_id": field}


class _Trace:
    def __init__(self) -> None:
        self.mqtt: list[tuple] = []
        self.killswitch: list[tuple] = []
        self.logs: list[tuple] = []
        self.halts: dict = {}

    async def send(self, device_id, command, payload, **kw):
        self.mqtt.append((device_id, command, kw))
        return True

    async def ks(self, _conn, tenant_id, *, field_id=None, valve_id=None):
        self.killswitch.append((tenant_id, field_id, valve_id))
        return self.halts.get((field_id, valve_id), (False, None))

    async def log(self, **kw):
        self.logs.append((kw["device_id"], kw["command"], kw["status"]))


@pytest.fixture
def wired(act, monkeypatch):
    db = _DB()
    trace = _Trace()
    db.devices["valve-a"] = _device("valve-a")
    db.devices["sensor-1"] = _device("sensor-1", kind="soil_moisture")
    db.rules.append(_rule())
    monkeypatch.setattr(act, "_pool", db)
    monkeypatch.setattr(act, "send_mqtt_command", trace.send)
    monkeypatch.setattr(act, "is_actuation_halted", trace.ks)
    monkeypatch.setattr(act, "log_command", trace.log)
    monkeypatch.setattr(act, "FEATURE_AUTOMATION_RULES_ACTUATION", "true")
    return act, db, trace


def _telemetry(device_id="sensor-1", value=42.0, **extra):
    body = {"device_id": device_id, **extra}
    if value is not None:
        body["value"] = value
    return json.dumps(body).encode()


# ══ A1 ═══════════════════════════════════════════════════════════════════
def test_a1_rules_do_not_fire_without_the_automation_flag_even_in_real_mode(wired, monkeypatch):
    act, _db, trace = wired
    monkeypatch.setattr(act, "ACTUATOR_MODE", "real")
    monkeypatch.setattr(act, "FEATURE_AUTOMATION_RULES_ACTUATION", None)

    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))

    assert trace.mqtt == [], "ACTUATOR_MODE=real وحده أطلق أتمتة القواعد"


def test_a1_listener_does_not_subscribe_without_the_flag(act, monkeypatch):
    class _Boom:
        def __init__(self, *_a, **_k):
            raise AssertionError("المستمع اتّصل بالوسيط والعلم معطّل")

    monkeypatch.setattr(act, "ACTUATOR_MODE", "real")
    monkeypatch.setattr(act, "FEATURE_AUTOMATION_RULES_ACTUATION", None)
    monkeypatch.setattr(act, "MQTTClient", _Boom)

    # محدودٌ زمنيّاً: المستمع بلا بوّابة يدخل حلقة إعادة اتّصال لا تنتهي.
    assert asyncio.run(asyncio.wait_for(act.mqtt_sensor_listener(), timeout=2)) is None


def test_a1_flag_on_lets_a_legitimate_rule_fire(wired):
    act, _db, trace = wired
    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    assert [(d, c) for d, c, _ in trace.mqtt] == [("valve-a", "open")]


# ══ A2 ═══════════════════════════════════════════════════════════════════
def test_a2_rule_query_is_scoped_by_the_sensor_field(wired):
    act, db, trace = wired
    db.rules[:] = [_rule(field="field-other")]

    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))

    assert trace.mqtt == []
    sql, args = db.rule_queries[-1]
    assert "field_id IS NULL OR field_id = $3" in sql and args[2] == "field-9"


def test_a2_rule_cannot_open_a_valve_in_another_field(wired):
    act, db, trace = wired
    db.devices["valve-a"] = _device("valve-a", field="field-B")

    out = asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))

    assert trace.mqtt == [], "مستشعر حقل field-9 فتح صمّاماً في field-B"
    assert out[0]["rejected"] == "device_field_mismatch"
    assert trace.logs == [("valve-a", "open", "rejected")]


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (None, "device_not_found"),
        (_device("valve-a", tenant=OTHER_TENANT), "device_tenant_mismatch"),
        (_device("valve-a", kind="water_meter"), "device_not_actuator"),
        (_device("valve-a", field=None), "device_field_mismatch"),
    ],
)
def test_a2_valve_gate_fails_closed(act, record, reason):
    assert act._rule_valve_gate(record, tenant_id=TENANT, sensor_field_id="field-9") == (
        False,
        reason,
    )


def test_a2_killswitch_is_consulted_with_the_valves_registry_field(wired):
    act, _db, trace = wired
    trace.halts[("field-9", "valve-a")] = (True, "إيقاف الحقل")

    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))

    assert trace.killswitch == [(TENANT, "field-9", "valve-a")]
    assert trace.mqtt == []


def test_a2_registry_failure_blocks_the_rule(wired, monkeypatch):
    act, _db, trace = wired

    async def _down(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(act, "_registry_device", _down)
    out = asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    assert trace.mqtt == [] and out[0]["rejected"] == "device_registry_error"


# ══ A3 ═══════════════════════════════════════════════════════════════════
def test_a3_spoofed_topic_tenant_cannot_trigger_another_tenants_rules(wired):
    """عميلٌ على الوسيط ينشر على موضوع مستأجر آخر بجهازٍ ليس له ⇒ رفض، لا ريّ."""
    act, db, trace = wired
    db.rules.append(_rule("valve-b", tenant=OTHER_TENANT))
    db.devices["valve-b"] = _device("valve-b", tenant=OTHER_TENANT)

    topic = f"sahool/{OTHER_TENANT}/field-9/telemetry/soil_moisture"
    asyncio.run(act._handle_telemetry_message(topic, _telemetry("sensor-1")))

    assert trace.mqtt == [], "موضوعٌ مزوَّر أطلق ريّاً لمستأجر آخر"
    assert db.rule_queries == []


def test_a3_topic_field_mismatch_is_rejected(wired):
    act, db, trace = wired
    topic = f"sahool/{TENANT}/field-other/telemetry/soil_moisture"
    asyncio.run(act._handle_telemetry_message(topic, _telemetry("sensor-1")))
    assert trace.mqtt == [] and db.rule_queries == []


def test_a3_unregistered_or_anonymous_source_is_rejected(wired):
    act, db, trace = wired
    topic = f"sahool/{TENANT}/field-9/telemetry/soil_moisture"
    asyncio.run(act._handle_telemetry_message(topic, _telemetry("ghost")))
    asyncio.run(act._handle_telemetry_message(topic, json.dumps({"value": 42}).encode()))
    assert trace.mqtt == [] and db.rule_queries == []


def test_a3_registry_attested_reading_fires_with_registry_scope(wired):
    act, db, trace = wired
    topic = f"sahool/{TENANT}/field-9/telemetry/soil_moisture"
    asyncio.run(act._handle_telemetry_message(topic, _telemetry("sensor-1")))
    assert [(d, c) for d, c, _ in trace.mqtt] == [("valve-a", "open")]
    assert db.rule_queries[-1][1] == (TENANT, "soil_moisture", "field-9")


def test_a3_missing_value_is_ignored_not_treated_as_zero(wired):
    """قاعدة «< 20 ⇒ ريّ»: قيمةٌ مفقودة كانت تُقرأ 0 فتُطلِق الريّ."""
    act, db, trace = wired
    db.rules[:] = [{**_rule(), "trigger_operator": "<", "trigger_threshold": 20}]
    topic = f"sahool/{TENANT}/field-9/telemetry/soil_moisture"

    for raw in (_telemetry(value=None), _telemetry(value="n/a"), _telemetry(value=True)):
        asyncio.run(act._handle_telemetry_message(topic, raw))

    assert trace.mqtt == []
    assert act._reading_value({"value": float("nan")}) is None
    assert act._reading_value({"value": "12.5"}) == 12.5


def test_a3_trigger_duration_requires_a_sustained_condition(wired, monkeypatch):
    act, db, trace = wired
    db.rules[:] = [_rule(duration=600)]
    clock = {"t": 1000.0}
    monkeypatch.setattr(act.time, "monotonic", lambda: clock["t"])

    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    assert trace.mqtt == [], "أُطلِق قبل أن يدوم الشرط trigger_duration_sec"

    clock["t"] += 300
    asyncio.run(act.evaluate_rules("soil_moisture", 5.0, TENANT, "field-9"))  # ينقض الشرط
    clock["t"] += 400
    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    assert trace.mqtt == [], "قراءةٌ ناقضة لم تُصفّر نافذة الاستمرار"

    clock["t"] += 600
    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    assert [(d, c) for d, c, _ in trace.mqtt] == [("valve-a", "open")]


# ══ A4 ═══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("command", "payload", "wire"),
    [
        ("open", {"duration_sec": 60}, "OPEN"),
        ("open_valve", {"duration_sec": 600}, "OPEN"),
        ("irrigate", {"duration_sec": 900}, "OPEN"),
        ("start", {"duration_sec": 60}, "OPEN"),
        ("close", {}, "CLOSE"),
        ("CLOSE_VALVE", {}, "CLOSE"),
        ("stop", {}, "CLOSE"),
    ],
)
def test_a4_platform_commands_map_to_the_firmware_vocabulary(act, command, payload, wire):
    assert act._to_firmware_wire(command, payload) == (wire, "ok")


@pytest.mark.parametrize(
    ("command", "payload", "reason"),
    [
        ("pulse", {}, "unknown_command:pulse"),
        ("", {}, "unknown_command:-"),
        ("irrigate", {"amount_mm": 12.0}, "dose_command_requires_duration_sec"),
        # ACTUATOR-OPEN-WITHOUT-DURATION-01: كلُّ OPEN بلا مدّة — لا `irrigate` وحده.
        ("open", {}, "open_command_requires_duration_sec"),
        ("open_valve", {}, "open_command_requires_duration_sec"),
        ("on", {}, "open_command_requires_duration_sec"),
        ("start", {}, "open_command_requires_duration_sec"),
        ("start_irrigation", None, "open_command_requires_duration_sec"),
        ("open", {"duration_sec": None}, "open_command_requires_duration_sec"),
        ("open_valve", {"duration_sec": 0}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": 0.0}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": float("nan")}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": -5}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": "abc"}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": "600"}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": float("inf")}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": True}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": 7200}, "duration_exceeds_device_max"),
        # `duration_sec` كنسيّ: الدقائق وحدها لا تُخمَّن ثوانيها ولا تصير سقف 30 دقيقة.
        ("open", {"duration_minutes": 10}, "non_canonical_duration_field:duration_minutes"),
        ("open_valve", {"duration_min": 30}, "non_canonical_duration_field:duration_min"),
        ("start", {"durationMinutes": 5}, "non_canonical_duration_field:durationMinutes"),
        ("irrigate", {"minutes": 5}, "non_canonical_duration_field:minutes"),
        ("on", {"duration_seconds": 60}, "non_canonical_duration_field:duration_seconds"),
        # مدّتان متعارضتان ⇒ رفضٌ بسببٍ مميَّز، لا اختيارُ إحداهما.
        ("open", {"duration_sec": 60, "duration_minutes": 10}, "conflicting_duration_fields"),
        ("open_valve", {"duration_sec": 600, "duration_min": "10"}, "conflicting_duration_fields"),
        ("open", {"duration_sec": 60, "duration_seconds": 61}, "conflicting_duration_fields"),
        # An invalid duration_sec beside a non-canonical field is refused as invalid,
        # never accepted because the second field happens to be well formed.
        ("open", {"duration_sec": "abc", "duration_minutes": 10}, "invalid_duration_sec"),
        ("open_valve", {"duration_sec": True, "duration_min": 1}, "invalid_duration_sec"),
        # NaN is a float, so it reaches the comparison and equals nothing: still refused,
        # with the conflict reason (the OPEN never reaches the firmware either way).
        (
            "start",
            {"duration_sec": float("nan"), "duration_seconds": 60},
            "conflicting_duration_fields",
        ),
    ],
)
def test_a4_unmappable_commands_are_rejected(act, command, payload, reason):
    assert act._to_firmware_wire(command, payload) == (None, reason)


@pytest.mark.parametrize(
    ("command", "payload", "wire"),
    [
        # مدّةٌ ثانيةٌ تطابق `duration_sec` تماماً ليست تعارضاً.
        ("open_valve", {"duration_sec": 600, "duration_minutes": 10}, "OPEN"),
        ("open", {"duration_sec": 90, "duration_min": 1.5}, "OPEN"),
        # الإغلاق لا يُحجَب بحقل مدّةٍ زائد: هو الحالة الآمنة.
        ("close", {"duration_minutes": 10}, "CLOSE"),
        ("stop_irrigation", {"duration_sec": 60, "duration_minutes": 99}, "CLOSE"),
    ],
)
def test_matching_or_irrelevant_duration_fields_are_not_refused(act, command, payload, wire):
    assert act._to_firmware_wire(command, payload) == (wire, "ok")


class _FakeMQTT:
    published: list[tuple] = []
    opened = 0

    def __init__(self, *_a, **_k):
        type(self).opened += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def publish(self, topic, message, qos=0, retain=False):
        type(self).published.append((topic, json.loads(message), qos, retain))


@pytest.fixture
def real_mqtt(act, monkeypatch):
    _FakeMQTT.published = []
    _FakeMQTT.opened = 0
    monkeypatch.setattr(act, "ACTUATOR_MODE", "real")
    monkeypatch.setattr(act, "MQTTClient", _FakeMQTT)
    # R-C2: these cases measure the A4/A5/A7 wire vocabulary on a **legacy v1** unit, which is
    # only signed while listed in ACTUATOR_LEGACY_V1_DEVICES. v2 is covered by
    # test_cmd_signing_v2.py (a device not listed gets nothing without CMD_HMAC_MASTER_KEY).
    monkeypatch.setenv("CMD_HMAC_SECRET", "s" * 32)
    monkeypatch.setenv("ACTUATOR_LEGACY_V1_DEVICES", "valve-a")
    monkeypatch.delenv("CMD_HMAC_MASTER_KEY", raising=False)
    return act


def test_a4_real_publish_carries_the_firmware_command_signed_on_the_wire(real_mqtt):
    import hashlib
    import hmac

    act = real_mqtt
    assert asyncio.run(act.send_mqtt_command("valve-a", "open_valve", {"duration_sec": 600}))
    topic, msg, qos, retain = _FakeMQTT.published[0]
    assert topic == "sahool/actuator/valve-a/command"
    assert msg["cmd"] == "OPEN"
    assert msg["payload"]["duration_ms"] == 600_000
    expected = hmac.new(b"s" * 32, f"OPEN|{msg['ts']}|600000".encode(), hashlib.sha256).hexdigest()
    assert msg["sig"] == expected, "التوقيع ليس على صيغة السلك التي يتحقّق منها البرنامج الثابت"
    # A7: QoS 1 بلا retain.
    assert (qos, retain) == (1, False)


def test_a4_unknown_command_never_reaches_the_broker(real_mqtt):
    act = real_mqtt
    assert asyncio.run(act.send_mqtt_command("valve-a", "irrigate", {"amount_mm": 10})) is False
    assert asyncio.run(act.send_mqtt_command("valve-a", "pulse", {})) is False
    assert _FakeMQTT.opened == 0 and _FakeMQTT.published == []


def test_a4_simulation_does_not_claim_success_for_an_unknown_command(act):
    assert asyncio.run(act.send_mqtt_command("valve-a", "pulse", {})) is False
    assert asyncio.run(act.send_mqtt_command("valve-a", "open", {"duration_sec": 60})) is True


def test_an_open_without_duration_is_refused_before_any_publish_in_every_mode(act, real_mqtt):
    """ACTUATOR-OPEN-WITHOUT-DURATION-01: فتحٌ بلا مدّة لا يُنشَر ولا يُحاكى نجاحاً.

    كان يُقبَل (عدا ``irrigate``) فيبقى الصمّام مفتوحاً حتّى سقف البرنامج الثابت
    ``VALVE_MAX_OPEN_MS`` (30 دقيقة). والإغلاق — الحالة الآمنة — يُنشَر بلا مدّة.
    """
    for mode in ("real", "simulation"):
        _FakeMQTT.published = []
        act.ACTUATOR_MODE = mode
        for cmd in ("open", "open_valve", "on", "start", "start_irrigation"):
            assert asyncio.run(act.send_mqtt_command("valve-a", cmd, {})) is False, (mode, cmd)
        assert _FakeMQTT.published == [], mode
    act.ACTUATOR_MODE = "real"
    assert asyncio.run(act.send_mqtt_command("valve-a", "close", {})) is True
    assert _FakeMQTT.published[0][1]["cmd"] == "CLOSE"


def test_a_minutes_only_or_conflicting_open_is_refused_on_publish_and_dispatch(act, real_mqtt):
    """`duration_sec` كنسيّ: دقائق وحدها أو مدّتان متعارضتان ⇒ لا نشر ولا محاكاة ولا إرسال.

    المساران اللذان لا يمرّان بالموجّه اليدويّ — القواعد والتعويض (``send_mqtt_command``)
    وطلبُ التنفيذ المحكوم (``_plan_dispatch_execution``) — يرفضان بنفس السبب.
    """
    cases = (
        ({"duration_minutes": 10}, "non_canonical_duration_field:duration_minutes"),
        ({"duration_sec": 60, "duration_minutes": 10}, "conflicting_duration_fields"),
    )
    for payload, reason in cases:
        for mode in ("real", "simulation"):
            _FakeMQTT.published = []
            act.ACTUATOR_MODE = mode
            assert asyncio.run(act.send_mqtt_command("valve-a", "open_valve", payload)) is False
            assert _FakeMQTT.published == [], (mode, payload)
        item = {
            "command_payload": {
                "device_id": "valve-1",
                "command": "open_valve",
                "payload": payload,
                "risk_level": "low",
            }
        }
        assert act._plan_dispatch_execution(item, allowlist={"low"}) == (
            "unsupported_command",
            reason,
        )
    act.ACTUATOR_MODE = "real"
    _FakeMQTT.published = []
    payload = {"duration_sec": 600, "duration_minutes": 10}
    assert asyncio.run(act.send_mqtt_command("valve-a", "open_valve", payload)) is True
    assert _FakeMQTT.published[0][1]["payload"]["duration_ms"] == 600_000


def test_a4_dispatch_plan_refuses_unmappable_command_with_its_reason(act):
    item = {
        "command_payload": {
            "device_id": "valve-1",
            "command": "irrigate",
            "payload": {"amount_mm": 12.0},
            "risk_level": "low",
        }
    }
    assert act._plan_dispatch_execution(item, allowlist={"low"}) == (
        "unsupported_command",
        "dose_command_requires_duration_sec",
    )


def test_a4_manual_endpoint_rejects_unknown_command_before_any_work(act, monkeypatch):
    from fastapi import HTTPException

    sys.modules.pop("routers.commands", None)
    sys.modules.pop("routers", None)
    import routers.commands as router_mod

    touched: list[str] = []

    async def _auth(*_a, **_k):
        touched.append("authorize")
        return "field-9"

    monkeypatch.setattr(act, "FEATURE_MANUAL_ACTUATOR_COMMANDS", "true")
    monkeypatch.setattr(act, "_authorize_device_control", _auth)
    claims = {"tenant_id": TENANT, "role": "owner", "sub": "u1"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            router_mod.send_command(act.CommandRequest(device_id="v", command="pulse"), claims)
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["reason"] == "unknown_command:pulse"
    assert touched == []


# ══ A5 ═══════════════════════════════════════════════════════════════════
def test_a5_republished_command_keeps_its_original_ts_and_id(real_mqtt):
    act = real_mqtt
    item = {
        "execution_request_id": "req-1",
        "requested_at": "2026-11-01T08:00:00.123456+00:00",
        "command_payload": {
            "device_id": "valve-a",
            "command": "open_valve",
            "payload": {"duration_sec": 600, "idempotency_key": "wtrcmd_1"},
        },
    }
    payload = item["command_payload"]["payload"]
    first = act._dispatch_wire_identity(item, payload, "req-1")
    # الاسترداد بعد إعادة تشغيل: نفس الطلب يعود من feed الاسترداد.
    again = act._dispatch_wire_identity(dict(item, claimed_at="later"), payload, "req-1")
    tag = __import__("hashlib").sha256(b"wtrcmd_1").hexdigest()[:12]
    assert first == again == ("wtrcmd_1", f"2026-11-01T08:00:00.123456+00:00~{tag}")

    for _ in range(2):
        asyncio.run(
            act.send_mqtt_command(
                "valve-a", "open_valve", payload, command_id=first[0], issued_at=first[1]
            )
        )
    (_, m1, _, _), (_, m2, _, _) = _FakeMQTT.published
    assert m1 == m2, "إعادة النشر غيّرت ts/التوقيع فلن يكشفها البرنامج الثابت مكرّرة"
    assert m1["ts"] == first[1] and m1["id"] == "wtrcmd_1"


def test_a5_dispatch_consumer_passes_the_stable_identity_to_the_publisher(act, monkeypatch):
    captured: list[dict] = []

    async def _send(device_id, command, payload, **kw):
        captured.append(kw)
        return True

    async def _halt(*_a, **_k):
        return False, None

    async def _device_ok(*_a, **_k):
        return True, "ok"

    item = {
        "execution_request_id": "req-9",
        "requested_at": "2026-11-01T09:00:00+00:00",
        "target_id": "valve-a",
        "command_payload": {"device_id": "valve-a", "command": "close", "risk_level": "low"},
    }

    class _Resp:
        def __init__(self, code, body=None):
            self.status_code = code
            self._body = body or {}

        def json(self):
            return self._body

    async def _request(_client, method, path, _tenant, json_body=None):
        if "recovery" in path:
            return _Resp(200, {"items": [item]})
        if "state=queued" in path:
            return _Resp(200, {"items": []})
        return _Resp(200)

    class _P:
        def acquire(self):
            class _C:
                async def __aenter__(self):
                    return object()

                async def __aexit__(self, *_e):
                    return False

            return _C()

    monkeypatch.setattr(act, "_pool", _P())
    monkeypatch.setattr(act, "is_actuation_halted", _halt)
    monkeypatch.setattr(act, "_validate_dispatch_device", _device_ok)
    monkeypatch.setattr(act, "_decision_request", _request)
    monkeypatch.setattr(act, "send_mqtt_command", _send)
    monkeypatch.setattr(act, "ACTUATOR_DELIVERY_TOKEN_KEY", "k" * 32)

    asyncio.run(act.run_dispatch_consumer_once(None, TENANT, allowlist={"low"}))
    asyncio.run(act.run_dispatch_consumer_once(None, TENANT, allowlist={"low"}))

    tag = __import__("hashlib").sha256(b"req-9").hexdigest()[:12]
    # R-C2: the tenant is passed so the v2 signature binds it; the payload names no field, so
    # the publisher reads the device's field from the registry (field_id=None here).
    assert (
        captured
        == [
            {
                "command_id": "req-9",
                "issued_at": f"2026-11-01T09:00:00+00:00~{tag}",
                "tenant_id": TENANT,
                "field_id": None,
            }
        ]
        * 2
    )


def test_two_commands_from_one_transaction_get_distinct_firmware_ts(act):
    """A5 review: requested_at is the transaction start, shared by every row of that transaction.

    The firmware dedups on ts alone, so a CLOSE sharing the OPEN's ts was dropped as a
    duplicate. The ts now carries a per-command suffix, stays stable across a republish and
    fits the firmware's 96-byte HMAC buffer.
    """
    same_tx = "2026-11-01 09:00:00.123456+00:00"
    open_item = {"requested_at": same_tx, "command_payload": {"idempotency_key": "k-open"}}
    close_item = {"requested_at": same_tx, "command_payload": {"idempotency_key": "k-close"}}
    _, ts_open = act._dispatch_wire_identity(open_item, {}, "req-a")
    _, ts_close = act._dispatch_wire_identity(close_item, {}, "req-b")
    assert ts_open != ts_close
    assert act._dispatch_wire_identity(open_item, {}, "req-a")[1] == ts_open  # republish
    assert len("CLOSE|" + ts_close) < 96


def test_compensation_can_close_a_valve_opened_with_the_canonical_vocabulary(act):
    """A4 review: open_valve/start_irrigation/irrigate actuate now, so the saga must invert them."""
    for opened, wire in (
        ("open_valve", "OPEN"),
        ("start_irrigation", "OPEN"),
        ("irrigate", "OPEN"),
    ):
        assert act._to_firmware_wire(opened, {"duration_sec": 60})[0] == wire
        inverse = act._inverse_command(opened)
        assert inverse is not None, opened
        assert act._to_firmware_wire(inverse, {})[0] == "CLOSE", (opened, inverse)


def test_a7_the_signature_binds_the_duration_so_an_edit_invalidates_it(act):
    """مدّةٌ مُعدَّلة على الطريق تُبطِل التوقيع (كانت خارجه فتُمدَّد إلى سقف الأمان)."""
    import json as _json

    short = _json.loads(
        act._build_wire_message("OPEN", {"duration_sec": 60}, ts="t1", secret="s" * 32)
    )
    longer = _json.loads(
        act._build_wire_message("OPEN", {"duration_sec": 1800}, ts="t1", secret="s" * 32)
    )
    assert short["payload"]["duration_ms"] == 60_000
    assert longer["payload"]["duration_ms"] == 1_800_000
    assert short["sig"] != longer["sig"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"duration_sec": 0.0004}, 1),  # دون الملّي ثانية ⇒ 1 لا 0 (0 يُعطِّل المؤقّت)
        ({"duration_sec": 0.0011}, 2),  # تقريبٌ لأعلى لا اقتطاع
        ({"duration_sec": 60}, 60_000),
        ({}, 0),
        ({"duration_sec": True}, 0),
        ({"duration_sec": "60"}, 0),
        ({"duration_sec": float("nan")}, 0),
    ],
)
def test_a7_wire_duration_is_whole_milliseconds_never_truncated_to_zero(act, payload, expected):
    assert act._wire_duration_ms(payload) == expected


# ══ تكرارُ OPEN لا يُعيد التشغيل ولا يُمدِّد المدّة (idempotency) ═══════════════
def test_a_repeated_rule_open_with_a_longer_duration_is_not_refired(wired, monkeypatch):
    """مفتاحُ إزالة التكرار (مستأجِر، حقل، جهاز، أمر) لا يحمل المدّة عمداً.

    فإعادةُ إطلاق القاعدة نفسها ضمن النافذة — ولو بمدّةٍ أطول — لا تُنشَر: لا تُعيد
    التشغيل ولا تُمدِّده. ولو دخلت المدّةُ المفتاحَ لصار كلُّ تعديلٍ للمدّة إطلاقاً جديداً.
    """
    act, db, trace = wired
    monkeypatch.setattr(act, "ACTUATOR_DEDUP_WINDOW_SEC", 60.0)
    db.rules[0]["action_payload"] = {"duration_sec": 60}
    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))
    db.rules[0]["action_payload"] = {"duration_sec": 1200}
    asyncio.run(act.evaluate_rules("soil_moisture", 42.0, TENANT, "field-9"))

    assert [(d, c) for d, c, _ in trace.mqtt] == [("valve-a", "open")]


def test_a_republished_dispatch_open_is_a_duplicate_on_the_wire(act):
    """إعادةُ نشر طلب التنفيذ نفسه (استرداد) تحمل الـ``ts`` نفسَه — ولو تغيّرت المدّة.

    والبرنامجُ الثابت يُسقِط المكرّرَ بـ``ts`` **قبل** فرع OPEN، فلا يصل التكرارُ إلى
    ``valveRequestedMs``: لا إعادة تشغيل ولا تمديد. والمدّة داخل التوقيع، فلا تُمدَّد
    رسالةٌ منشورة بتعديلها على السلك.
    """
    item = {"requested_at": "2026-11-09T10:00:00+00:00", "command_payload": {}}
    first = act._dispatch_wire_identity(item, {"idempotency_key": "k-1"}, "req-1")
    again = act._dispatch_wire_identity(item, {"idempotency_key": "k-1"}, "req-1")
    assert first == again and first[1]

    ts = first[1]
    original = json.loads(
        act._build_wire_message("OPEN", {"duration_sec": 60}, ts=ts, secret="s" * 32)
    )
    longer = json.loads(
        act._build_wire_message("OPEN", {"duration_sec": 1200}, ts=ts, secret="s" * 32)
    )
    assert original["ts"] == longer["ts"] == ts
    assert original["sig"] != longer["sig"], "المدّة خارج التوقيع ⇒ تُمدَّد بلا كسره"

    # R-C2: the v2 firmware drops a replay by its persisted counter (``ctr <= last_ctr``) in
    # ``verify_command`` — before ``valveRequestedMs`` — and the republish keeps its ``ctr``
    # (test_cmd_signing_v2.py::test_a_republished_dispatch_command_keeps_its_counter).
    fw = (ROOT / "firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino").read_text("utf-8")
    callback = fw[fw.index("void mqttCallback(") :]
    assert callback.index("cmdauth::verify_command(") < callback.index("valveRequestedMs =")
    assert callback.index("persistLastCtr(m.ctr)") < callback.index("valveRequestedMs =")
