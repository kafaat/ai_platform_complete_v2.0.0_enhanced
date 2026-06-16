"""api/routers/alerts.py — التنبيهات الزراعيّة (Alerts)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسارات/الأذونات/المخرجات/الأحداث المُصدَرة/مخطّط OpenAPI
مطابقة تماماً لما كان في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app``
إلى ``@router`` (بما فيها إصدار ALERT_CREATED/ALERT_ACKNOWLEDGED/FIELD_STATE_CHANGED
حرفيّاً عبر ``_emit_domain_event``).

الطبقة النقيّة (AlertSummary/AlertCreateRequest/_ALERT_*/_row_to_alert) نُقِلت إلى
``api.alert_models`` (تفكيك B1) وتُستورَد من هناك. محرّك التسليم ``_log_alert_deliveries``
وبقيّة المساعِدات (_idem_key/_idempotent/_assert_field_in_tenant/_emit_domain_event …)
تبقى في ``api.main`` وتُستورَد من هنا. ``CommandStore`` من وحدتها ``api.command_store``
مباشرةً. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.alert_models import (
    _ALERT_SEVERITIES,
    _ALERT_STATUSES,
    _ALERT_TYPES,
    AlertCreateRequest,
    AlertSummary,
    _row_to_alert,
)

# CommandStore تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان main يستورده).
from api.command_store import CommandStore
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _clamp_list_window,
    _db_unavailable,
    _emit_domain_event,
    _idem_key,
    _idempotent,
    _log_alert_deliveries,
    get_pool,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/alerts", response_model=list[AlertSummary])
async def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int | None = Query(default=None, ge=0),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تنبيهات المستأجِر (الأحدث أولاً) — مُرشَّحة بالمستأجِر (RLS) + حالة/خطورة اختياريّة.

    تُتحقَّق قيم الترشيح (422 على قيمة غير معروفة) قبل الاستعلام. مُرقَّمة (limit/offset)
    بسقف أمان يمنع over-fetch على قائمة غير محدودة — الافتراضيّ أحدث 100. 503 عند تعذّر القاعدة.
    """
    if status is not None and status not in _ALERT_STATUSES:
        raise HTTPException(status_code=422, detail="حالة تنبيه غير معروفة")
    if severity is not None and severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    lim, off = _clamp_list_window(limit, offset)
    conds = ["tenant_id = $1::uuid"]
    args: list = [str(user.tenant_id)]
    if status is not None:
        args.append(status)
        conds.append(f"status = ${len(args)}")
    if severity is not None:
        args.append(severity)
        conds.append(f"severity = ${len(args)}")
    where = " AND ".join(conds)
    args.append(lim)
    limit_ph = f"${len(args)}"
    args.append(off)
    offset_ph = f"${len(args)}"
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at "
                f"FROM alerts WHERE {where} ORDER BY created_at DESC "
                f"LIMIT {limit_ph} OFFSET {offset_ph}",
                *args,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة التنبيهات", e) from e
    return [_row_to_alert(r) for r in rows]


@router.post("/api/v1/alerts", status_code=201, response_model=AlertSummary)
async def create_alert(
    req: AlertCreateRequest,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """ينشئ تنبيهاً زراعيّاً للمستأجِر — يُخزَّن فعليّاً ضمن سياق المستأجِر (RLS).

    يتحقّق من النوع والخطورة (422)، ويؤكّد أنّ الحقل (إن مُرِّر) يخصّ المستأجِر
    (404) قبل الإدراج، ثمّ يردّ التنبيه المُنشأ. idempotent: Idempotency-Key
    (UUID) يمنع تكرار الإنشاء عند إعادة الموبايل (offline).
    """
    import uuid as _uuid

    if req.alert_type not in _ALERT_TYPES:
        raise HTTPException(status_code=422, detail="نوع تنبيه غير معروف")
    if req.severity not in _ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail="درجة خطورة غير معروفة")
    alert_id = "alr_" + _uuid.uuid4().hex[:12]
    try:
        async with tenant_connection(user) as conn:

            async def _work():
                if req.field_id is not None:
                    await _assert_field_in_tenant(conn, req.field_id)
                await conn.execute(
                    """INSERT INTO alerts
                        (alert_id, tenant_id, field_id, alert_type, severity,
                         title_ar, message_ar, status)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'active')""",
                    alert_id,
                    str(user.tenant_id),
                    req.field_id,
                    req.alert_type,
                    req.severity,
                    req.title_ar,
                    req.message_ar,
                )
                created = AlertSummary(
                    alert_id=alert_id,
                    field_id=req.field_id,
                    alert_type=req.alert_type,
                    severity=req.severity,
                    title_ar=req.title_ar,
                    message_ar=req.message_ar,
                    status="active",
                )
                # تسجيل قنوات التسليم المقصودة (بلا إرسال فعليّ) — غير كاسر.
                await _log_alert_deliveries(conn, user, created)
                # حدث إنشاء التنبيه (تفاعليّ): يستهلكه وكيل الإشعارات للبثّ الفوريّ بدل
                # المسح الدوريّ. نفس معاملة الكتابة (outbox) — فشل الإصدار لا يكسر الحفظ.
                await _emit_domain_event(
                    conn,
                    user,
                    "ALERT_CREATED",
                    "alert",
                    alert_id,
                    {
                        "severity": req.severity,
                        "alert_type": req.alert_type,
                        "field_id": req.field_id,
                    },
                )
                # Canonical Field State: تنبيه على حقل قد يعكس تبدّل قراره ⇒ أعِد حساب
                # الإسقاط وأصدِر field.state_changed إن تبدّلت الصلاحيّة (نفس نمط الموسم،
                # نفس معاملة الكتابة). التنبيهات تمرّ عبر مصدر الحقيقة الواحد.
                if req.field_id is not None:
                    from api.field_state_projection import recompute_field_state

                    _fs = await recompute_field_state(conn, req.field_id)
                    if _fs["changed"]:
                        await _emit_domain_event(
                            conn,
                            user,
                            "FIELD_STATE_CHANGED",
                            "field",
                            req.field_id,
                            {
                                "validity": _fs["state"]["validity"],
                                "execution_mode": _fs["state"]["execution_mode"],
                                "trigger": "alert.created",
                            },
                        )
                # نُعيد JSON (model_dump) ليُخزَّن كنتيجة أمر idempotent ويُعاد حرفيّاً
                # عند الإعادة (مع حفظ alert_id الأصليّ) — response_model يتحقّق منه.
                return created.model_dump()

            # idempotent عند توفّر مفتاح (إعادة الموبايل لا تُكرّر)؛ وإلّا تنفيذ عاديّ.
            if idem:
                result = await _idempotent(
                    CommandStore(get_pool(), conn=conn),
                    idem,
                    _work,
                    command_type="alert.create",
                    actor_id=str(user.user_id),
                    tenant_id=str(user.tenant_id),
                    payload={"field_id": req.field_id, "alert_id": alert_id},
                )
            else:
                result = await _work()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("حفظ التنبيه", e) from e
    return result


@router.patch("/api/v1/alerts/{alert_id}/acknowledge", response_model=AlertSummary)
async def acknowledge_alert(
    alert_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُقِرّ تنبيهاً (status='acknowledged') للمستأجِر — مُرشَّح بالمستأجِر (RLS).

    404 لو التنبيه ليس ضمن المستأجِر؛ 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "UPDATE alerts SET status = 'acknowledged' WHERE alert_id = $1 "
                "RETURNING alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at",
                alert_id,
            )
            # حدث الإقرار (تفاعليّ): يُمكّن المستهلكين من تتبّع دورة حياة التنبيه.
            # داخل المعاملة وفقط عند وجود الصفّ (مرشَّح بالمستأجِر عبر RLS).
            if row is not None:
                await _emit_domain_event(
                    conn,
                    user,
                    "ALERT_ACKNOWLEDGED",
                    "alert",
                    alert_id,
                    {"field_id": row["field_id"], "severity": row["severity"]},
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("إقرار التنبيه", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="التنبيه غير موجود ضمن هذا المستأجِر")
    return _row_to_alert(row)
