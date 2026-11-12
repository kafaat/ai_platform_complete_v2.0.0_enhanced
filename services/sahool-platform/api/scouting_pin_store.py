"""إدامة دبابيس التفتيش في ``scouting_pins`` تحت سياق المستأجِر (RLS) — best-effort.

انتقلت من ``api/routers/fields.py`` كي لا يكبر الراوتر فوق سقف
``tests/architecture/test_router_size_ratchet.py``. يبقى في الراوتر غلافٌ رفيع يمرّر
``tenant_connection`` وحالة المسبح وقت النداء، فتبقى نقاط الاستبدال في الاختبارات كما هي.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import HTTPException


async def persist_scouting_pin(
    user: Any, pin: Any, *, pool_ready: bool, connect: Callable[[Any], Any]
) -> bool:
    """يُثبّت الدبّوس؛ ``True`` لو ثُبِّت (أو كان موجوداً مطابقاً)، ``False`` لو تعذّرت القاعدة.

    * حقلٌ ليس ضمن مستأجِر المستدعي ⇒ 404 (فحصٌ تحت RLS قبل الإدراج).
    * إعادة إرسال مطابقة ⇒ تُرجَع القيمة المخزَّنة (``created_at`` الأصليّ).
    * المُعرِّف نفسه بمحتوى مختلف ⇒ 409.
    * ``created_at`` يُمرَّر قيمة datetime إلى ``::timestamptz`` (النصّ كان يُرفَض بصمت).
    SQL بارامتريّ بالكامل.
    """
    if not pool_ready:
        return False
    try:
        async with connect(user) as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM fields WHERE field_id=$1 AND tenant_id=$2::uuid",
                pin.field_id,
                str(user.tenant_id),
            )
            if not exists:
                raise HTTPException(404, "الحقل غير موجود ضمن هذا المستأجر")
            result = await conn.execute(
                "INSERT INTO scouting_pins "
                "(pin_id, tenant_id, field_id, lat, lng, issue_category, severity, "
                " status, persistence, crop, issue_code, note_ar, photo_uri, color, "
                " created_by, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                " $13, $14, $15, $16::timestamptz) "
                "ON CONFLICT (pin_id) DO NOTHING",
                pin.pin_id,
                str(user.tenant_id),
                pin.field_id,
                pin.lat,
                pin.lng,
                pin.issue_category.value,
                pin.severity.value,
                pin.status.value,
                pin.persistence.value,
                pin.crop,
                pin.issue_code,
                pin.note_ar,
                pin.photo_uri,
                pin.color,
                pin.created_by,
                datetime.fromisoformat(pin.created_at),
            )
            if result == "INSERT 0 0":
                previous = await conn.fetchrow(
                    "SELECT * FROM scouting_pins WHERE pin_id=$1 AND tenant_id=$2::uuid",
                    pin.pin_id,
                    str(user.tenant_id),
                )
                if previous is None or any(
                    previous[key] != value
                    for key, value in pin.to_dict().items()
                    if key != "created_at"
                ):
                    raise HTTPException(409, "معرّف الدبوس مستخدم لمشاهدة مختلفة")
                pin.created_at = previous["created_at"].isoformat()
        return True
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — إدامة best-effort: تعذّر القاعدة ⇒ persisted=false
        logging.warning("scouting pin persistence failed for pin %s", pin.pin_id)
        return False
