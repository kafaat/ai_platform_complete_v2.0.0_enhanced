"""routers/commands.py — أوامر التحكّم بالأجهزة (Actuator commands)
======================================================================
شريحة من تفكيك ``actuator_runtime.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المعاملات/
الأجسام/المخرجات والتبعيّات الأمنيّة مطابقة بايت-ببايت. هذه الوحدة **حسّاسة أمنيّاً**:
``/command`` يُشغّل أجهزة فيزيائيّة — تبقى تبعيّة ``Depends(main._verify_token)`` وحارس
``main._authorize_device_control`` ومسارات الأوامر كما هي تماماً. الرموز المشتركة
(الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import actuator_runtime as main
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.actuation_killswitch import is_actuation_halted

router = APIRouter()


@router.post("/v1/command")
async def send_command(req: main.CommandRequest, claims: dict = Depends(main._verify_token)):
    # الأمان: tenant_id يُشتقّ من التوكن المُتحقَّق، لا من جسم الطلب (منع انتحال).
    tenant_id = str(claims["tenant_id"])
    user_id = claims.get("sub")
    # حراسة per-path (Safety Hardening #481): التحكّم اليدويّ معطّل افتراضيّاً ⇒ 403 صريح
    # **قبل** أيّ عمل (DB/ملكيّة/نشر). فعّله FEATURE_MANUAL_ACTUATOR_COMMANDS صراحةً.
    # يسبق فحص الملكيّة (503 بلا DB) كي تُرفَض الأوامر بأمان حتّى بلا قاعدة.
    if not main._manual_commands_enabled(main.FEATURE_MANUAL_ACTUATOR_COMMANDS):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "manual_actuator_commands_disabled_by_safety_policy",
                "message_ar": "التحكّم اليدويّ بالمُشغّلات معطّل بسياسة السلامة "
                "(فعّل FEATURE_MANUAL_ACTUATOR_COMMANDS)",
            },
        )
    # حارس السلامة الفيزيائيّة + العزل: فحص الدور + ملكيّة الجهاز للمستأجِر (fail-closed).
    device_field_id = await main._authorize_device_control(claims, req.device_id)
    # مفتاح إيقاف طوارئ التشغيل (v133، fail-closed): استشِر قبل النشر. مفتاح مُشتبَك
    # (نطاق مستأجِر أو **حقل** أو صمّام هذا الجهاز) ⇒ 423 Locked بالسبب العربيّ، لا تنفيذ
    # فيزيائيّ. و`field_id` يأتي من المُصرِّح الذي استعلمه أصلاً — بدونه كان مفتاحُ
    # الحقل يحجب مسارَي القواعد والإرسال ويترك هذا الباب مفتوحاً، بلا أثرٍ في الاستجابة.
    # (يصل هنا فقط بعد _authorize_device_control الذي يضمن وجود main._pool أو 503.)
    async with main._pool.acquire() as ks_conn:
        halted, halt_reason = await is_actuation_halted(
            ks_conn, tenant_id, field_id=device_field_id, valve_id=req.device_id
        )
    if halted:
        raise HTTPException(423, halt_reason or "التشغيل مُوقَف بمفتاح إيقاف الطوارئ")
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


@router.get("/v1/commands")
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
