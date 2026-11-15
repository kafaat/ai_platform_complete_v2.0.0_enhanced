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
import command_delivery as cd
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
    # A4: أمرٌ لا يفهمه البرنامج الثابت ⇒ 422 صريح قبل أيّ عمل، لا 200 بـsent=false.
    wire_cmd, wire_reason = main._to_firmware_wire(req.command, req.payload)
    if wire_cmd is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "unsupported_actuator_command", "reason": wire_reason},
        )
    # حارس السلامة الفيزيائيّة + العزل: فحص الدور + ملكيّة الجهاز للمستأجِر (fail-closed).
    device_field_id = await main._authorize_device_control(claims, req.device_id)
    # مفتاح إيقاف طوارئ التشغيل (v133، fail-closed): استشِر قبل النشر. مفتاح مُشتبَك
    # (نطاق مستأجِر أو **حقل** أو صمّام هذا الجهاز) ⇒ 423 Locked بالسبب العربيّ، لا تنفيذ
    # فيزيائيّ. و`field_id` يأتي من المُصرِّح الذي استعلمه أصلاً — بدونه كان مفتاحُ
    # الحقل يحجب مسارَي القواعد والإرسال ويترك هذا الباب مفتوحاً، بلا أثرٍ في الاستجابة.
    # (يصل هنا فقط بعد _authorize_device_control الذي يضمن وجود main._pool أو 503.)
    async with main._pool.acquire() as ks_conn:
        # ACTUATOR-KILLSWITCH-BLOCKS-CLOSE-01: CLOSE/OFF (is_safe_direction) is never held by the
        # kill-switch nor by its fail-closed answer — closing is what the switch exists for.
        halted, halt_reason = await is_actuation_halted(
            ks_conn,
            tenant_id,
            field_id=device_field_id,
            valve_id=req.device_id,
            command=req.command,
        )
    if halted:
        raise HTTPException(423, halt_reason or "التشغيل مُوقَف بمفتاح إيقاف الطوارئ")
    # v238: حالة تسليم صريحة. الأمر يُسجَّل queued ويحمل command_id على السلك؛ النشر الناجح
    # (real) يجعله published فقط — device_acked لا يأتي إلّا من إقرار الجهاز الموقَّع.
    command_id = cd.new_command_id()
    await main.record_command_queued(
        tenant_id=tenant_id,
        device_id=req.device_id,
        command=req.command,
        payload=req.payload,
        command_id=command_id,
        triggered_by="manual",
    )
    success = await main.send_mqtt_command(
        req.device_id,
        req.command,
        req.payload,
        command_id=command_id,
        tenant_id=tenant_id,
        field_id=device_field_id,
    )
    delivery_state = cd.state_after_publish(success, main.ACTUATOR_MODE)
    await main.log_command(
        rule_id=None,
        device_id=req.device_id,
        command=req.command,
        payload=req.payload,
        status="sent" if success else "failed",
        tenant_id=tenant_id,
        command_id=command_id,
        delivery_state=delivery_state,
        triggered_by="manual",
    )
    return {
        "device_id": req.device_id,
        "command": req.command,
        "sent": success,
        "command_id": command_id,
        "delivery_state": delivery_state,
        "tenant_id": tenant_id,
        "issued_by": user_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


_COMMAND_COLUMNS = (
    "log_id, device_id, command, status, sent_at, triggered_by, " + main._DELIVERY_COLUMNS
)


def _command_view(row: dict, now: datetime) -> dict:
    """سجلّ الأمر + حالة تسليمه الفعّالة وطوابعها (v238)."""
    base = {k: row.get(k) for k in ("log_id", "device_id", "command", "status", "triggered_by")}
    sent_at = row.get("sent_at")
    base["sent_at"] = sent_at.isoformat() if isinstance(sent_at, datetime) else sent_at
    base.update(cd.delivery_view(row, now))
    return base


@router.get("/v1/commands")
async def list_commands(
    limit: int = Query(50, ge=1, le=500), claims: dict = Depends(main._verify_token)
):
    # الأمان: tenant_id من التوكن المُتحقَّق لا من المعامل (منع قراءة سجلّ مستأجر آخر)
    tenant_id = str(claims["tenant_id"])
    if not main._pool:
        return {"commands": []}
    # v238: الجدول FORCE RLS — بلا سياق مستأجر لا صفوف (fail-closed)، فيُضبط داخل معاملة،
    # وتُطبَّق انتهاءات المهلة قبل القراءة كي لا يُعرَض أمرٌ منتهٍ كأنّه ما زال published.
    async with main._pool.acquire() as conn:
        async with conn.transaction():
            await main._set_tenant(conn, tenant_id)
            await main.expire_overdue_commands(conn, tenant_id)
            rows = await conn.fetch(
                f"""SELECT {_COMMAND_COLUMNS}
                   FROM device_commands_log
                   WHERE tenant_id = $1::uuid
                   ORDER BY sent_at DESC LIMIT $2""",
                tenant_id,
                limit,
            )
    now = datetime.now(UTC)
    return {"commands": [_command_view(dict(r), now) for r in rows]}


@router.get("/v1/commands/{command_id}")
async def get_command(command_id: str, claims: dict = Depends(main._verify_token)):
    """حالة تسليم أمر واحد: queued/published/device_acked/device_rejected/expired/…

    أمرٌ لمستأجر آخر أو غير موجود ⇒ 404 موحّد (RLS + شرط المستأجر، لا تسريب وجود).
    """
    tenant_id = str(claims["tenant_id"])
    if not main._pool:
        raise HTTPException(503, "سجلّ الأوامر غير متاح")
    async with main._pool.acquire() as conn:
        async with conn.transaction():
            await main._set_tenant(conn, tenant_id)
            await main.expire_overdue_commands(conn, tenant_id)
            row = await conn.fetchrow(
                f"""SELECT {_COMMAND_COLUMNS}
                   FROM device_commands_log
                   WHERE tenant_id = $1::uuid AND command_id = $2""",
                tenant_id,
                command_id,
            )
    if row is None:
        raise HTTPException(404, "الأمر غير موجود")
    return _command_view(dict(row), datetime.now(UTC))
