"""test_modbus_decoder_20260703.py — فكّ Modbus-RTU لحسّاسات RS485 الرخيصة.

يسدّ فجوة حقيقيّة (kundian-iot): لا دعم Modbus/RS485 في المنصّة. يغطّي:
  • ``modbus_decoder`` (نقيّ): CRC-16/MODBUS (متجه معياريّ) + فكّ سجلّات + رفض صادق.
  • نقطة ``POST /v1/soil/decode/modbus`` (importorskip fastapi/asyncpg).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SVC = Path(__file__).resolve().parents[1] / "services" / "soil-service"


def _load_isolated(unique_name: str, filename: str):
    """يحمّل وحدة قائمة بذاتها من مجلّد الخدمة باسم فريد **دون لمس sys.path**.

    يتفادى تصادم أسماء الوحدات العامّة (main/db_persist/routers) عبر الخدمات في
    التشغيل الكامل — لا نُدخِل soil-service في المسار وقت الجمع (لئلّا نُظلِّل استيراد
    خدمة أخرى). الوحدات هنا قائمة بذاتها (stdlib فقط) فتُحمَّل مباشرةً من الملفّ."""
    spec = importlib.util.spec_from_file_location(unique_name, _SVC / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load_isolated("soil_modbus_decoder_under_test", "modbus_decoder.py")


@pytest.fixture(autouse=True)
def _preserve_sibling_main():
    """يستعيد أيّ وحدة عامّة الاسم (main/routers لخدمة أخرى) بعد كلّ اختبار.

    ``_load_soil_main`` يستبدل ``sys.modules['main']`` بـmain الخاصّ بـsoil؛ فلو جرى
    قبل اختبار خدمة أخرى (raster) يكتسح main المُخبَّأ لتلك الخدمة فتفشل. نلتقط الحالة
    قبل الاختبار ونعيدها بعده — عزلٌ صادق لا يُفسد جيران أسماء الوحدات العامّة.
    """

    def _keys():
        return [
            k
            for k in sys.modules
            if k in ("main", "router_registry", "routers", "db_persist") or k.startswith("routers.")
        ]

    saved = {k: sys.modules[k] for k in _keys()}
    yield
    for k in _keys():
        sys.modules.pop(k, None)
    sys.modules.update(saved)
    while str(_SVC) in sys.path:  # لا نُبقِ soil-service في المسار (يُظلِّل خدمات أخرى)
        sys.path.remove(str(_SVC))


def _frame(slave, func, regs):
    """يبني إطار ردّ صالحاً (سجلّات 16-بت big-endian + CRC little-endian)."""
    data = b"".join(bytes([(r >> 8) & 0xFF, r & 0xFF]) for r in regs)
    body = bytes([slave, func, len(data)]) + data
    c = m.crc16_modbus(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


# ── نقيّ ──────────────────────────────────────────────────────────────────────
def test_crc16_standard_vector():
    # متجه CRC-16/MODBUS المعياريّ.
    assert m.crc16_modbus(b"123456789") == 0x4B37


def test_decode_valid_frame():
    frame = _frame(0x01, 0x03, [250, 65])
    assert m.decode_registers(frame) == [250, 65]


def test_decode_input_registers_func04():
    frame = _frame(0x01, 0x04, [123])
    assert m.decode_registers(frame) == [123]


def test_bad_crc_rejected():
    frame = bytearray(_frame(0x01, 0x03, [250, 65]))
    frame[-1] ^= 0xFF  # إفساد CRC
    with pytest.raises(ValueError, match="CRC"):
        m.decode_registers(bytes(frame))


def test_unsupported_function_rejected():
    body = bytes([0x01, 0x06, 0x02, 0x00, 0x01])
    c = m.crc16_modbus(body)
    with pytest.raises(ValueError, match="غير مدعومة"):
        m.decode_registers(body + bytes([c & 0xFF, (c >> 8) & 0xFF]))


def test_short_frame_rejected():
    with pytest.raises(ValueError):
        m.decode_registers(b"\x01\x03")


def test_registers_to_readings_scale_offset():
    regs = [250, 655, 70]
    mapping = {
        "temperature": {"index": 0, "scale": 10},  # 25.0
        "moisture_pct": {"index": 1, "scale": 10},  # 65.5
        "ph_level": {"index": 2, "scale": 10},  # 7.0
    }
    out = m.registers_to_readings(regs, mapping)
    assert out == {"temperature": 25.0, "moisture_pct": 65.5, "ph_level": 7.0}


def test_readings_skip_out_of_range_index():
    # فهرس خارج المدى ⇒ يُتخطّى (لا يخترع قيمة).
    assert m.registers_to_readings([100], {"x": {"index": 5}}) == {}


# ── نقطة HTTP (importorskip fastapi + asyncpg) ──────────────────────────────────
def _load_soil_main(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("asyncpg")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-token")
    # ثبّت مجلّد soil-service في مقدّمة المسار وقت التحميل (قد يكون ملفّ خدمة آخر
    # أزاحه) كي يُحلّ ``main`` إلى soil لا خدمة أخرى — ثمّ أخلِ المُخبَّأ العامّ الاسم.
    while str(_SVC) in sys.path:
        sys.path.remove(str(_SVC))
    sys.path.insert(0, str(_SVC))
    for name in ("main", "router_registry", "routers", "routers.modbus", "routers.soil_profile"):
        sys.modules.pop(name, None)
    import main

    return main


def test_decode_endpoint_returns_registers_and_readings(monkeypatch):
    main = _load_soil_main(monkeypatch)
    from fastapi.testclient import TestClient

    frame = _frame(0x01, 0x03, [250, 65])
    client = TestClient(main.app)
    r = client.post(
        "/v1/soil/decode/modbus",
        json={"frame_hex": frame.hex(), "mapping": {"temperature": {"index": 0, "scale": 10}}},
        headers={"X-Agent-Token": "test-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["registers"] == [250, 65]
    assert body["readings"]["temperature"] == 25.0


def test_decode_endpoint_422_on_bad_crc(monkeypatch):
    main = _load_soil_main(monkeypatch)
    from fastapi.testclient import TestClient

    frame = bytearray(_frame(0x01, 0x03, [250]))
    frame[-1] ^= 0xFF
    client = TestClient(main.app)
    r = client.post(
        "/v1/soil/decode/modbus",
        json={"frame_hex": bytes(frame).hex()},
        headers={"X-Agent-Token": "test-token"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "bad_modbus_frame"


def test_decode_endpoint_requires_token(monkeypatch):
    main = _load_soil_main(monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    # إطار صالح الطول (يتجاوز تحقّق النموذج) كي نصل لفحص التوكن → 401 لا 422.
    frame = _frame(0x01, 0x03, [10])
    r = client.post("/v1/soil/decode/modbus", json={"frame_hex": frame.hex()})
    assert r.status_code == 401


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
