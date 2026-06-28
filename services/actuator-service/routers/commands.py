"""routers/commands.py — أوامر التحكّم بالأجهزة (Actuator commands)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المعاملات/
الأجسام/المخرجات والتبعيّات الأمنيّة مطابقة بايت-ببايت. هذه الوحدة **حسّاسة أمنيّاً**:
``/command`` يُشغّل أجهزة فيزيائيّة — تبقى تبعيّة ``Depends(main._verify_token)`` وحارس
``main._authorize_device_control`` ومسارات الأوامر كما هي تماماً. الرموز المشتركة
(الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import main
from fastapi import APIRouter, Depends, Query

router = APIRouter()


@router.post("/command")
async def send_command(req: main.CommandRequest, claims: dict = Depends(main._verify_token)):
    # الأمان: tenant_id يُشتقّ من التوكن المُتحقَّق، لا من جسم الطلب (منع انتحال).
    tenant_id = str(claims["tenant_id"])
    user_id = claims.get("sub")
    # حارس السلامة الفيزيائيّة + العزل: فحص الدور + ملكيّة الجهاز للمستأجِر (fail-closed).
    await main._authorize_device_control(claims, req.device_id)
    success = await main.send_mqtt_command(req.device_id, req.command, req.payload)
    await main.log_command(
        rule_id=None,
        device_id=req.device_id,
        command=req.command,
        payload=req.payload,
        status="sent" if success else "failed",
        tenant_id=tenant_id,
    )
    return {
        "device_id": req.device_id,
        "command": req.command,
        "sent": success,
        "tenant_id": tenant_id,
        "issued_by": user_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/commands")
async def list_commands(
    limit: int = Query(50, ge=1, le=500), claims: dict = Depends(main._verify_token)
):
    # الأمان: tenant_id من التوكن المُتحقَّق لا من المعامل (منع قراءة سجلّ مستأجر آخر)
    tenant_id = str(claims["tenant_id"])
    if not main._pool:
        return {"commands": []}
    async with main._pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT log_id, device_id, command, status, sent_at, triggered_by
               FROM device_commands_log
               WHERE tenant_id = $1::uuid
               ORDER BY sent_at DESC LIMIT $2""",
            tenant_id,
            limit,
        )
    return {"commands": [dict(r) for r in rows]}
