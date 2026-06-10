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
