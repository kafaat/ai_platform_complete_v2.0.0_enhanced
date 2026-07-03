"""modbus_decoder.py — فكّ إطارات Modbus-RTU لحسّاسات RS485 منخفضة التكلفة (نقيّ).

يسدّ فجوة حقيقيّة (مُستلهَمة من kundian-iot): لا دعم Modbus/RS485 في المنصّة رغم
شيوع حسّاسات التربة/الرطوبة/الحرارة الصينيّة الرخيصة (RS485/Modbus-RTU) في السوق
الصغير/المتوسّط. هذه الوحدة **نقيّة** (بلا شبكة/عتاد) تفكّ ردّ «قراءة السجلّات» إلى
قيم — فتُختبَر بالكامل بإطارات معروفة دون جهاز.

بروتوكول Modbus-RTU (ردّ الدالّة 0x03/0x04):
  [عنوان(1)] [دالّة(1)] [عدد البايتات(1)] [بيانات(2×n)] [CRC منخفض(1)] [CRC مرتفع(1)]
  • السجلّات 16-بت big-endian. CRC-16/MODBUS (بذرة 0xFFFF، حدّ 0xA001) يُلحَق
    little-endian. الصدق: CRC فاسد/دالّة غير مدعومة/طول شاذّ ⇒ ValueError (لا تخمين).
"""

from __future__ import annotations

# دوالّ القراءة المدعومة (سجلّات الاحتفاظ 0x03 / سجلّات الإدخال 0x04).
_READ_FUNCS = (0x03, 0x04)


def crc16_modbus(data: bytes) -> int:
    """CRC-16/MODBUS القياسيّ (بذرة 0xFFFF، حدّ 0xA001، LSB أوّلاً). يُرجِع 16-بت.

    متجه تحقّق معياريّ: CRC للنصّ ``b"123456789"`` = 0x4B37.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def verify_frame_crc(frame: bytes) -> bool:
    """يتحقّق أنّ آخر بايتين هما CRC (little-endian) لبقيّة الإطار."""
    if len(frame) < 4:
        return False
    body, crc_bytes = frame[:-2], frame[-2:]
    expected = crc_bytes[0] | (crc_bytes[1] << 8)  # little-endian (منخفض ثمّ مرتفع)
    return crc16_modbus(body) == expected


def decode_registers(frame: bytes) -> list[int]:
    """يفكّ ردّ «قراءة السجلّات» (0x03/0x04) → قائمة قيم سجلّات 16-بت.

    يرفع ValueError على: إطار قصير · CRC فاسد · دالّة غير مدعومة · عدد بايتات
    غير متّسق. الصدق: لا نُرجِع قيماً من إطار غير موثوق.
    """
    if len(frame) < 5:
        raise ValueError("إطار Modbus قصير جدّاً")
    if not verify_frame_crc(frame):
        raise ValueError("CRC غير مطابق — إطار Modbus فاسد")
    func = frame[1]
    if func not in _READ_FUNCS:
        raise ValueError(f"دالّة Modbus غير مدعومة: 0x{func:02X} (المدعوم 0x03/0x04)")
    byte_count = frame[2]
    data = frame[3:-2]
    if byte_count != len(data) or byte_count % 2 != 0:
        raise ValueError("عدد بايتات Modbus غير متّسق مع البيانات")
    return [(data[i] << 8) | data[i + 1] for i in range(0, byte_count, 2)]


def registers_to_readings(registers: list[int], mapping: dict[str, dict]) -> dict[str, float]:
    """يحوّل السجلّات إلى قيم حسّاس عبر خريطة موثّقة {name: {index, scale, offset}}.

    ``scale`` (قسمة، افتراضي 1) و``offset`` (طرح، افتراضي 0): value = reg/scale − offset.
    (نمط شائع: الحرارة والرطوبة تُرسَل ×10 كأعداد صحيحة.) يتخطّى فهرساً خارج المدى
    (صدق: لا يخترع قيمة لسجلّ غائب).
    """
    out: dict[str, float] = {}
    for name, spec in mapping.items():
        idx = int(spec.get("index", -1))
        if idx < 0 or idx >= len(registers):
            continue
        scale = float(spec.get("scale", 1.0)) or 1.0
        offset = float(spec.get("offset", 0.0))
        out[name] = round(registers[idx] / scale - offset, 4)
    return out
