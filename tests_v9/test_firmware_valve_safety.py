"""Guard: ESP32 firmware valve fail-safe (auto-close on max valve-open).

حماية فيزيائيّة حرجة: لو وصل أمر OPEN ثم انقطع الاتصال قبل CLOSE (شبكة متقطّعة)
يجب أن يُغلق الصمّام محلّيّاً بعد مدّة قصوى — وإلّا إغراق الحقل/إهدار ماء نادر.
هذه الحراسات نصّيّة (لا تترجم Arduino) لمنع انتكاس الإصلاح بصمت.
"""

from __future__ import annotations

import os
import re

import pytest

FW = os.path.join(
    os.path.dirname(__file__), "..", "firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino"
)


def _src() -> str:
    with open(FW, encoding="utf-8") as f:
        return f.read()


# R-C2: command verification lives in a pure header the sketch includes (host-tested with g++).
HEADER = os.path.join(os.path.dirname(FW), "cmd_auth_v2.h")


def _header() -> str:
    with open(HEADER, encoding="utf-8") as f:
        return f.read()


@pytest.mark.unit
def test_valve_max_open_constant_defined():
    assert re.search(r"#define\s+VALVE_MAX_OPEN_MS\s+\d+UL", _src()), (
        "ثابت المدّة القصوى لفتح الصمّام (VALVE_MAX_OPEN_MS) مفقود"
    )


@pytest.mark.unit
def test_open_time_tracked_via_set_relay():
    s = _src()
    assert "void setRelay(bool on)" in s, "دالّة setRelay المركزيّة مفقودة"
    assert "valveOpenedAt = on ? millis() : 0;" in s, "تتبّع وقت فتح الصمّام مفقود"
    assert "setRelay(true)" in s and "setRelay(false)" in s, "أمر الصمّام لا يمرّ عبر setRelay"


@pytest.mark.unit
def test_loop_auto_closes_after_timeout():
    s = _src()
    assert re.search(
        r"valveOpenedAt\s*!=\s*0\s*&&\s*\(millis\(\)\s*-\s*valveOpenedAt\)\s*>=\s*VALVE_MAX_OPEN_MS",
        s,
    ), "فحص الإغلاق التلقائي في loop() مفقود"
    assert "valve_auto_closed" in s, "تنبيه الإغلاق التلقائي (broadcast) مفقود"


@pytest.mark.unit
def test_no_untracked_relay_open():
    # فتح الصمّام يجب أن يمرّ عبر setRelay (يسجّل الوقت)؛ لا digitalWrite HIGH مباشر
    # خارجها — وإلّا يبقى الصمّام بلا مؤقّت fail-safe.
    assert "digitalWrite(RELAY_PIN, HIGH)" not in _src(), (
        "فتح مباشر للصمّام بلا تتبّع وقت — يكسر الـfail-safe"
    )


# ── عقد المنصّة↔البرنامج الثابت (تدقيق 2026-11-01: A4/A7) ──────────────────
_PLATFORM = os.path.join(
    os.path.dirname(__file__), "..", "services/actuator-service/actuator_runtime.py"
)


def _platform_wire_vocabulary() -> set[str]:
    import ast

    tree = ast.parse(open(_PLATFORM, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_FIRMWARE_WIRE_COMMANDS" for t in node.targets
        ):
            return {v.value for v in node.value.values}
    raise AssertionError("_FIRMWARE_WIRE_COMMANDS مفقودة في actuator_runtime.py")


@pytest.mark.unit
def test_every_platform_wire_command_is_understood_by_the_firmware():
    """A4: ما تنشره المنصّة يجب أن يطابق ما يقارنه البرنامج الثابت بـstrcmp — وإلّا لا حركة."""
    understood = set(re.findall(r'strcmp\((?:m\.)?cmd,\s*"([A-Z]+)"\)', _src() + _header()))
    wire = _platform_wire_vocabulary()
    assert wire and wire <= understood, f"أوامر لا يفهمها البرنامج الثابت: {wire - understood}"


@pytest.mark.unit
def test_firmware_accepts_platform_sized_commands():
    """A4: رسالة المنصّة تتجاوز حدّ PubSubClient الافتراضيّ (256) ومستند JSON بسعة 256."""
    s = _src()
    assert re.search(r"mqttClient\.setBufferSize\((\d+)\)", s), "حدّ حزمة MQTT الافتراضيّ 256"
    doc = re.search(r"void mqttCallback\([\s\S]*?StaticJsonDocument<(\d+)> doc;", s)
    assert doc and int(doc.group(1)) >= 512, "مستند أمر MQTT أصغر من رسالة المنصّة"


@pytest.mark.unit
def test_firmware_honours_requested_duration_and_does_not_renew_the_cap():
    """A7: المدّة المطلوبة تُغلق الصمّام محلّيّاً، وOPEN متكرّر لا يجدّد سقف الأمان."""
    s = _src()
    assert 'doc["payload"]["duration_ms"]' in s
    # المدّة الموقَّعة وحدها تُغلِق: لا قراءة لـduration_sec غير الموقَّعة في الجهاز.
    assert 'doc["payload"]["duration_sec"]' not in s
    assert "valveRequestedMs = (unsigned long)m.duration_ms;" in s
    assert re.search(r"\(millis\(\)\s*-\s*valveOpenedAt\)\s*>=\s*valveRequestedMs", s)
    assert "if (valveOpenedAt == 0) setRelay(true);" in s


@pytest.mark.unit
def test_firmware_subscribes_to_commands_at_qos1():
    """A7: الاشتراك الافتراضيّ QoS 0 يُسقط الأمر بصمت."""
    assert re.search(r"mqttClient\.subscribe\(cmdTopic\.c_str\(\),\s*1\)", _src())


@pytest.mark.unit
def test_firmware_signature_binds_the_requested_duration():
    """المدّة داخل الرسالة الموقَّعة (v2: v2|tenant|device|field|id|cmd|duration_ms|iat|exp|ctr)،
    وتُتحقَّق قبل أيّ تشغيل."""
    s, h = _src(), _header()
    assert '"v2|%s|%s|%s|%s|%s|%llu|%llu|%llu|%llu", tenant, device, field, id,' in h
    assert "cmd, (unsigned long long)duration_ms" in h
    assert "else ok = ok && jsonUint(dur, &m.duration_ms);" in s
    callback = s[s.index("void mqttCallback(") :]
    assert callback.index("cmdauth::verify_command(") < callback.index("setRelay(")
    # الرسالة المقتطَعة تُرفَض لا تُوقَّع ناقصة.
    assert "if (n < 0 || n >= (int)sizeof(msg)) return false;  // truncated" in h
