"""Behavioural regression coverage for the opt-in, device-bound MQTT profile."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/actuator-service"
TENANT = "11111111-1111-1111-1111-111111111111"
NOW = 1_795_280_000_000
TOPIC = f"sahool/{TENANT}/field-9/telemetry/sensor-1/mesh"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


telemetry = _load("mesh_device_contract_tested", SERVICE / "device_telemetry.py")
transport = _load("mesh_mqtt_transport_tested", SERVICE / "mqtt_transport.py")
acl = _load("mesh_device_acl_tested", ROOT / "mosquitto/device_acl.py")


def _payload(**changes):
    value = {
        "v": 1,
        "tenant_id": TENANT,
        "field_id": "field-9",
        "device_id": "sensor-1",
        "source": "device_local",
        "measured_at_ms": NOW,
        "soil_calibrated": True,
        "data": {
            "air_temp_c": 28.5,
            "air_humidity_pct": 62,
            "soil_moisture_pct": 24.5,
            "soil_raw": 1599,
            "relay_state": True,
            "mesh_nodes": 3,
        },
        "units": {"air_temp_c": "degC", "air_humidity_pct": "%", "soil_moisture_pct": "%"},
    }
    value.update(changes)
    return json.dumps(value).encode()


def test_normalizes_only_named_measurements_and_preserves_scope_time_and_units():
    sample = telemetry.parse_mesh_sample(TOPIC, _payload(), now_ms=NOW)
    assert (sample.tenant_id, sample.field_id, sample.device_id, sample.measured_at_ms) == (
        TENANT,
        "field-9",
        "sensor-1",
        NOW,
    )
    assert [(r.sensor_type, r.value, r.unit) for r in sample.readings] == [
        ("air_temperature", 28.5, "degC"),
        ("air_humidity", 62.0, "%"),
        ("soil_moisture", 24.5, "%"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "other"},
        {"field_id": "other"},
        {"device_id": "peer"},
        {"source": "mesh_forwarded"},
        {"source": None},
        {"v": True},
        {"measured_at_ms": NOW - 120_001},
        {"measured_at_ms": NOW + 30_001},
        {"measured_at_ms": 120_000},
        {"measured_at_ms": True},
        {"measured_at_ms": float(NOW)},
        {"data": []},
        {"units": []},
    ],
)
def test_rejects_identity_time_or_envelope_ambiguity(change):
    assert telemetry.parse_mesh_sample(TOPIC, _payload(**change), now_ms=NOW) is None


@pytest.mark.parametrize("segment", ["+", "#", "a/b", "a\nuser evil", " bad", "", "a" * 64])
def test_rejects_wildcard_and_path_injection(segment):
    for index in (1, 2, 4):
        parts = TOPIC.split("/")
        parts[index] = segment
        assert telemetry.parse_mesh_sample("/".join(parts), _payload(), now_ms=NOW) is None


@pytest.mark.parametrize("raw", [b"\xff", b"[]", b"null", b"{}" * 3000, b'{"v":1,"v":1}'])
def test_rejects_invalid_json_or_oversized_payload(raw):
    assert telemetry.parse_mesh_sample(TOPIC, raw, now_ms=NOW) is None


@pytest.mark.parametrize(
    "value", [None, False, "23", float("nan"), float("inf"), -999, -1, 101, 10**1000]
)
def test_invalid_humidity_never_turns_into_zero(value):
    raw = _payload(data={"air_humidity_pct": value})
    assert telemetry.parse_mesh_sample(TOPIC, raw, now_ms=NOW) is None


def test_wrong_units_and_uncalibrated_adc_are_not_rule_inputs():
    assert (
        telemetry.parse_mesh_sample(
            TOPIC, _payload(data={"air_temp_c": 35}, units={"air_temp_c": "degF"}), now_ms=NOW
        )
        is None
    )
    assert (
        telemetry.parse_mesh_sample(
            TOPIC, _payload(data={"soil_moisture_pct": 24}, soil_calibrated=False), now_ms=NOW
        )
        is None
    )


def test_replay_window_is_bounded_and_rejects_duplicates_or_backward_samples():
    cache = telemetry.MeshReplayWindow(max_devices=1)
    sample = telemetry.parse_mesh_sample(TOPIC, _payload(), now_ms=NOW)
    assert cache.accept(sample, now_ms=NOW)
    assert not cache.accept(sample, now_ms=NOW)
    older = telemetry.parse_mesh_sample(TOPIC, _payload(measured_at_ms=NOW - 1), now_ms=NOW)
    assert not cache.accept(older, now_ms=NOW)
    other = telemetry.parse_mesh_sample(
        TOPIC.replace("sensor-1", "sensor-2"), _payload(device_id="sensor-2"), now_ms=NOW
    )
    assert not cache.accept(other, now_ms=NOW)
    later = telemetry.parse_mesh_sample(
        TOPIC.replace("sensor-1", "sensor-2"),
        _payload(device_id="sensor-2", measured_at_ms=NOW + 120_001),
        now_ms=NOW + 120_001,
    )
    assert cache.accept(later, now_ms=NOW + 120_001)


def test_legacy_mesh_envelope_cannot_gain_automation_authority():
    assert (
        telemetry.parse_mesh_sample(
            f"sahool/{TENANT}/field-9/telemetry/mesh", _payload(), now_ms=NOW
        )
        is None
    )


@pytest.fixture
def act(monkeypatch):
    # Isolate service-local imports; another service's routers must not be reused.
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    names = [
        name
        for name in sys.modules
        if name == "actuator_runtime"
        or name == "router_registry"
        or name == "routers"
        or name.startswith("routers.")
    ]
    saved = {name: sys.modules.pop(name) for name in names}
    module = _load("actuator_runtime", SERVICE / "actuator_runtime.py")
    monkeypatch.setattr(module, "FEATURE_DEVICE_MESH_TELEMETRY", "true")
    monkeypatch.setattr(module, "MQTT_BROKER_URL", "mqtts://device-broker:8883")
    monkeypatch.setattr(module, "MQTT_USERNAME", "sahool-actuator-service")
    monkeypatch.setattr(module, "MQTT_PASSWORD", "test-only-password")
    monkeypatch.setattr(module, "MQTT_TLS_CA_FILE", "/test-only/ca.crt")
    monkeypatch.setattr(module.time, "time", lambda: NOW / 1000)
    module._registry_device = AsyncMock(
        return_value={
            "tenant_id": TENANT,
            "field_id": "field-9",
            "device_id": "sensor-1",
        }
    )
    module.evaluate_rules = AsyncMock(return_value=[])
    try:
        yield module
    finally:
        for name in list(sys.modules):
            if (
                name == "actuator_runtime"
                or name == "router_registry"
                or name == "routers"
                or name.startswith("routers.")
            ):
                sys.modules.pop(name)
        sys.modules.update(saved)


async def test_rules_receive_registry_bound_values_only_once(act):
    assert await act._handle_telemetry_message(TOPIC, _payload()) == []
    assert [call.args for call in act.evaluate_rules.await_args_list] == [
        ("air_temperature", 28.5, TENANT, "field-9"),
        ("air_humidity", 62.0, TENANT, "field-9"),
        ("soil_moisture", 24.5, TENANT, "field-9"),
    ]
    await act._handle_telemetry_message(TOPIC, _payload())
    assert act.evaluate_rules.await_count == 3


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"tenant_id": "other", "field_id": "field-9", "device_id": "sensor-1"},
        {"tenant_id": TENANT, "field_id": "other", "device_id": "sensor-1"},
        {"tenant_id": TENANT, "field_id": "field-9", "device_id": "peer"},
    ],
)
async def test_registry_rejects_cross_scope_or_wrong_device(act, record):
    act._registry_device.return_value = record
    assert await act._handle_telemetry_message(TOPIC, _payload()) is None
    act.evaluate_rules.assert_not_awaited()


@pytest.mark.parametrize(
    "record, reason",
    [
        (None, "device_not_registered"),
        (
            {"tenant_id": "other", "field_id": "field-9", "device_id": "sensor-1"},
            "topic_tenant_mismatch",
        ),
        (
            {"tenant_id": TENANT, "field_id": "other", "device_id": "sensor-1"},
            "topic_field_mismatch",
        ),
        (
            {"tenant_id": TENANT, "field_id": "field-9", "device_id": "peer"},
            "registry_device_id_mismatch",
        ),
    ],
)
async def test_a_refused_mesh_sample_logs_its_reason_once_per_interval(
    act, monkeypatch, caplog, record, reason
):
    clock = [1000.0]
    monkeypatch.setattr(act, "_monotonic", lambda: clock[0])
    act._mesh_reject_logged.clear()
    act._registry_device.return_value = record
    caplog.set_level("WARNING", logger="actuator-service")

    def rejections():
        return [
            r.getMessage() for r in caplog.records if "mesh telemetry rejected" in r.getMessage()
        ]

    for _ in range(3):
        assert await act._handle_telemetry_message(TOPIC, _payload()) is None
    assert len(rejections()) == 1
    assert reason in rejections()[0] and "'sensor-1'" in rejections()[0]

    clock[0] += act._MESH_REJECT_LOG_INTERVAL_S
    assert await act._handle_telemetry_message(TOPIC, _payload()) is None
    assert len(rejections()) == 2
    act.evaluate_rules.assert_not_awaited()


def test_a_full_throttle_table_keeps_live_throttles_and_stays_bounded(act, monkeypatch, caplog):
    clock = [5.0]
    monkeypatch.setattr(act, "_monotonic", lambda: clock[0])
    act._mesh_reject_logged.clear()
    act._mesh_reject_overflow.update(last=None, suppressed=0)
    caplog.set_level("WARNING", logger="actuator-service")
    limit = act._MESH_REJECT_LOG_MAX_KEYS

    def warnings():
        return [r.getMessage() for r in caplog.records if "mesh telemetry reject" in r.getMessage()]

    # Two passes over limit + 1 distinct keys at a fixed clock: each tracked key logs once,
    # the overflow logs one summary, and the second pass logs nothing (no throttle reset).
    for _ in range(2):
        for index in range(limit + 1):
            act._log_mesh_rejection(TENANT, f"device-{index}", "device_not_registered")
    assert len(warnings()) == limit + 1
    assert "not logged individually" in warnings()[-1]
    assert len(act._mesh_reject_logged) == limit

    # After the interval the expired keys make room, so new keys log individually again.
    clock[0] += act._MESH_REJECT_LOG_INTERVAL_S
    assert act._log_mesh_rejection(TENANT, "device-new", "device_not_registered")
    assert len(act._mesh_reject_logged) <= limit


async def test_retained_and_unbound_mesh_are_not_replayed(act):
    await act._handle_telemetry_message(TOPIC, _payload(), retained=True)
    await act._handle_telemetry_message(TOPIC.replace("/sensor-1/", "/"), _payload())
    act._registry_device.assert_not_awaited()
    act.evaluate_rules.assert_not_awaited()


@pytest.mark.parametrize(
    "setting,value",
    [
        ("FEATURE_DEVICE_MESH_TELEMETRY", ""),
        ("MQTT_BROKER_URL", "mqtt://legacy:1883"),
        ("MQTT_TLS_CA_FILE", ""),
        ("MQTT_USERNAME", "shared"),
        ("MQTT_PASSWORD", ""),
    ],
)
async def test_profile_is_opt_in_and_requires_tls_identity_and_ca(act, monkeypatch, setting, value):
    monkeypatch.setattr(act, setting, value)
    await act._handle_telemetry_message(TOPIC, _payload())
    act._registry_device.assert_not_awaited()
    act.evaluate_rules.assert_not_awaited()


async def test_legacy_scalar_remains_compatible(act):
    raw = json.dumps({"device_id": "sensor-1", "value": "24.5"})
    await act._handle_telemetry_message(f"sahool/{TENANT}/field-9/telemetry/soil_moisture", raw)
    act.evaluate_rules.assert_awaited_once_with("soil_moisture", 24.5, TENANT, "field-9")


@pytest.mark.parametrize("listener", ["mqtt_sensor_listener", "mqtt_ack_listener"])
async def test_listeners_use_aiomqtt_two_messages_iterator(act, monkeypatch, listener):
    subscriptions = []
    client_options = []
    message = SimpleNamespace(topic=SimpleNamespace(value=TOPIC), payload=_payload(), retain=False)

    class Client:
        def __init__(self, *args, **kwargs):
            client_options.append((args, kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def subscribe(self, topic, qos):
            subscriptions.append((topic, qos))

        @property
        def messages(self):
            async def iterate():
                yield message
                raise asyncio.CancelledError

            return iterate()

    monkeypatch.setattr(act, "MQTTClient", Client)
    monkeypatch.setattr(act, "ACTUATOR_MODE", "real")
    monkeypatch.setattr(act, "FEATURE_AUTOMATION_RULES_ACTUATION", "true")
    monkeypatch.setattr(act, "_mqtt_transport_kwargs", lambda: {"tls_context": "verified-context"})
    monkeypatch.setattr(act, "handle_device_ack", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await getattr(act, listener)()
    assert client_options[0][1]["tls_context"] == "verified-context"
    if listener == "mqtt_sensor_listener":
        assert ("sahool/+/+/telemetry/+/mesh", 1) in subscriptions
        assert act.evaluate_rules.await_count == 3
    else:
        act.handle_device_ack.assert_awaited_once_with(TOPIC, _payload())


def test_mqtts_uses_verified_context_and_correct_default_port():
    assert transport.mqtt_endpoint("mqtts://broker") == ("broker", 8883)
    assert transport.mqtt_endpoint("mqtt://broker") == ("broker", 1883)
    context = transport.mqtt_tls_kwargs("mqtts://broker")["tls_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert transport.mqtt_tls_kwargs("mqtt://broker") == {}
    with pytest.raises(FileNotFoundError):
        transport.mqtt_tls_kwargs("mqtts://broker", "/nonexistent/ca.crt")


@pytest.mark.parametrize(
    "url",
    [
        "https://broker",
        "broker",
        "mqtt://",
        "mqtt://u:p@broker",
        "mqtt://broker/path",
        "mqtt://broker?x=y",
        "mqtt://broker:0",
        "mqtt://broker:99999",
    ],
)
def test_malformed_endpoint_never_falls_back(url):
    with pytest.raises(ValueError):
        transport.mqtt_tls_kwargs(url)


def test_acl_device_grants_bind_one_tenant_field_and_device():
    text = acl.render_device_acl(
        [{"tenant_id": TENANT, "field_id": "field-9", "device_id": "sensor-1"}]
    )
    grants = text.split("user sensor-1\n")[1].splitlines()
    assert grants == [
        "topic read sahool/actuator/sensor-1/command",
        f"topic write sahool/{TENANT}/field-9/telemetry/sensor-1/mesh",
        f"topic write sahool/{TENANT}/actuator/sensor-1/ack",
    ]
    assert all("+" not in grant and "#" not in grant for grant in grants)


@pytest.mark.parametrize(
    "key,value",
    [
        ("field_id", "+"),
        ("field_id", "#"),
        ("device_id", "a\nuser evil"),
        ("tenant_id", "other"),
        ("device_id", "sahool-actuator-service"),
        ("device_id", "a/b"),
    ],
)
def test_acl_rejects_registry_export_injection(key, value):
    record = {"tenant_id": TENANT, "field_id": "field-9", "device_id": "sensor-1", key: value}
    with pytest.raises(ValueError):
        acl.render_device_acl([record])


def test_acl_rejects_shared_device_username_and_empty_inventory():
    record = {"tenant_id": TENANT, "field_id": "field-9", "device_id": "sensor-1"}
    with pytest.raises(ValueError):
        acl.render_device_acl([record, {**record, "field_id": "field-other"}])
    with pytest.raises(ValueError):
        acl.render_device_acl([])
