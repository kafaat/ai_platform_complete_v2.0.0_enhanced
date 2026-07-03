"""routers/modbus.py — فكّ إطار Modbus-RTU لحسّاسات RS485 منخفضة التكلفة.

يسدّ فجوة حقيقيّة (kundian-iot): حسّاسات التربة/الرطوبة/الحرارة الصينيّة الرخيصة
تتكلّم Modbus-RTU عبر RS485/DTU. هذه النقطة تفكّ إطار ردّ «قراءة السجلّات» (سلسلة
سُداسيّة عشريّة، كما تصل من بوّابة DTU) إلى قيم حسّاس مُفكَّكة — دون كتابة محرّك لكلّ
حسّاس. المنطق النقيّ في ``modbus_decoder`` (مُختبَر بإطارات معروفة).

الصدق: CRC فاسد/دالّة غير مدعومة/سلسلة سُداسيّة غير صالحة ⇒ 422 صريح (لا تخمين قيمة).
قراءة/فكّ فقط — لا يكتب سجلّات (يُمرَّر الناتج إلى ``/soil/ingest`` القائم إن أُريد الحفظ).
"""

from __future__ import annotations

import main
import modbus_decoder
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class RegisterSpec(BaseModel):
    index: int = Field(ge=0)
    scale: float = 1.0
    offset: float = 0.0


class ModbusDecodeRequest(BaseModel):
    """إطار Modbus-RTU سُداسيّ + خريطة سجلّات → قيم حسّاس."""

    frame_hex: str = Field(min_length=10, max_length=512)
    mapping: dict[str, RegisterSpec] = Field(default_factory=dict)


@router.post("/soil/decode/modbus")
async def decode_modbus(req: ModbusDecodeRequest, x_agent_token: str = Header(None)):
    """يفكّ إطار Modbus-RTU (0x03/0x04) → سجلّات + قيم حسّاس مُخطَّطة (صدق: 422 عند الفساد)."""
    main._require_service_token(x_agent_token)
    cleaned = req.frame_hex.replace(" ", "").replace(":", "")
    try:
        frame = bytes.fromhex(cleaned)
    except ValueError as e:
        raise HTTPException(
            422, detail={"error": "bad_hex", "note_ar": "سلسلة سُداسيّة غير صالحة"}
        ) from e
    try:
        registers = modbus_decoder.decode_registers(frame)
    except ValueError as e:
        raise HTTPException(422, detail={"error": "bad_modbus_frame", "note_ar": str(e)}) from e
    mapping = {name: spec.model_dump() for name, spec in req.mapping.items()}
    readings = modbus_decoder.registers_to_readings(registers, mapping)
    return {"registers": registers, "readings": readings}
