"""api/routers/sync.py — مزامنة العمليّات (Offline Sync)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/الثوابت) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا. رموز ``core.offline_first`` (OperationKind/SyncStatus/
record_operation_offline/apply_supersession) تُستورَد مباشرةً من وحدتها (نفس
الرموز التي كان main يستوردها — نُقل استيرادها هنا لإزالة F401 من main بعد النقل).
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from core.offline_first import (
    OperationKind,
    SyncStatus,
    apply_supersession,
    record_operation_offline,
)
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _DB_POOL,
    _OFFLINE_QUEUE,
    SyncBatchRequest,
    UserSchema,
    get_current_user,
    tenant_connection,
)
from api.offline_sync_contracts import (
    build_sync_manifest,
    normalize_offline_operation,
    summarize_sync_status,
)
from api.offline_sync_db import FIELD_UPDATE_KIND
from api.sync_delta import filter_since, newest_cursor

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _delta_sync_enabled() -> bool:
    """هل المزامنة التفاضليّة مُفعَّلة؟ (مُطفأة افتراضاً — إغلاق مرن).

    عند الإطفاء: يُتجاهَل ``since`` تماماً ويبقى السلوك الحاليّ (full replay)
    بايتاً ببايت — صفر كسر على العقد القائم.
    """
    return os.getenv("FEATURE_DELTA_SYNC", "").strip().lower() in _TRUTHY


@router.get("/api/v1/sync/manifest")
async def sync_manifest(user: UserSchema = Depends(get_current_user)):
    """عقد مزامنة machine-readable للويب والموبايل.

    يثبّت أسماء العمليات، سياسة التعارض، وحقول operation-id المقبولة حتى لا تبقى
    المزامنة منطقاً مخفياً داخل العميل.
    """
    return build_sync_manifest()


@router.get("/api/v1/sync/status")
async def sync_status(user: UserSchema = Depends(get_current_user)):
    """حالة طابور المزامنة للمستأجر الحالي دون كشف بيانات العمليات.

    تستخدم الذاكرة دائماً، وتضيف pending durable من Postgres عند توفره.
    """
    durable_pending = None
    if _DB_POOL is not None:
        try:
            from api.offline_pending_db import fetch_pending

            async with tenant_connection(user) as conn:
                durable_pending = len(await fetch_pending(conn, limit=5000))
        except Exception as exc:  # noqa: BLE001 — حالة status لا تكسر التطبيق
            logging.warning("sync status: durable pending check failed: %s", exc)
    return summarize_sync_status(
        queued=_OFFLINE_QUEUE.total_pending(user.tenant_id),
        queue_size=_OFFLINE_QUEUE.queue_size(user.tenant_id),
        durable_pending=durable_pending,
    )


@router.post("/api/v1/sync")
async def sync(
    req: SyncBatchRequest,
    user: UserSchema = Depends(get_current_user),
    since: str | None = None,
):
    """دفعة عمليات من العميل offline-first.

    العميل أنشأ ops محلّياً، يرسلها هنا حين يعود الاتصال.
    لكلّ عملية: تُكتب للقاعدة فعليّاً (idempotent على op_id)، ثم تُسجَّل النتيجة.

    fail-safe: لو فشلت كتابة عملية، تبقى في الـqueue للمحاولة لاحقاً (لا نُعلن
    نجاحاً زائفاً). إن لم تكن القاعدة مفعّلة (DATABASE_URL غير مضبوط) تبقى الكلّ
    في الـqueue.

    مزامنة تفاضليّة (Delta-Sync) — خلف ``FEATURE_DELTA_SYNC`` (إغلاق مرن):
      • العلم مُطفأ ⇒ ``since`` يُتجاهَل تماماً والسلوك الحاليّ (full replay).
      • العلم مُفعَّل و``since`` مُمرَّر ⇒ تُرشَّح عمليّات هذا الطلب بـ``filter_since``
        فلا تُسجَّل/تُثبَّت إلّا الأحدث من cursor العميل (إقصاء ما استلمه سابقاً)
        ⇒ توفير نطاق. cursor فاسد ⇒ ارتداد آمن لـfull (لا فقدان عمليّات).
      • الاستجابة تُرفِق ``cursor`` (أحدث طابع لِيُرسله العميل تالياً) و
        ``delta_applied`` (هل طُبّق الترشيح فعلاً). stateless: لا جدول/migration.
    """
    # Tenant isolation is authoritative from the authenticated user/JWT.
    # req.tenant_id is retained only as a deprecated legacy compatibility field;
    # if present it must match, but clients no longer need to send it.
    tenant_id = user.tenant_id
    if req.tenant_id is not None and req.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # ٠) مزامنة تفاضليّة اختياريّة: خلف العلم وبتمرير since فقط نرشّح عمليّات الطلب
    #    لِما هو أحدث من cursor العميل (filter_since نقيّ: cursor فاسد ⇒ full).
    #    خارج هذا الشرط: incoming_ops = req.operations حرفيّاً (السلوك الحاليّ).
    delta_applied = False
    incoming_ops = req.operations
    if _delta_sync_enabled() and since is not None:
        incoming_ops = filter_since(req.operations, since)
        delta_applied = True

    # ١) نُسجّل عمليّات هذا الطلب في الـqueue. نوع غير معروف ⇒ 400 صريح (لا 500):
    #    OperationKind(قيمة مجهولة) يرفع ValueError، فنتحقّق قبل الإدخال.
    #    استثناء: شريحة التوزيع field.update (FIELD_UPDATE_KIND) ليست قيمة في
    #    OperationKind (تُطبَّق فعليّاً لا تُدوَّن فقط) — نمرّرها كسلسلة كما هي ليلتقطها
    #    التوزيع (dispatch_decision) في خطوة الإثبات. PendingOperation/persist يقرآن
    #    op.kind نصّاً بأمان (hasattr(.,"value")) فلا كسر بنمرير سلسلة.
    op_ids = []
    for raw_op in incoming_ops:
        try:
            normalized = normalize_offline_operation(raw_op)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

        raw_kind = normalized["kind"]
        if raw_kind == FIELD_UPDATE_KIND:
            kind = FIELD_UPDATE_KIND  # سلسلة منقّطة — تُوزَّع لمسار التطبيق الفعليّ
        else:
            kind = OperationKind(raw_kind)

        op = record_operation_offline(
            _OFFLINE_QUEUE,
            tenant_id=tenant_id,
            user_id=user.user_id,
            kind=kind,
            payload=normalized["payload"],
        )
        # Preserve stable mobile operation ID when supplied. This closes the cross-request
        # idempotency gap for offline retries after weak connectivity; legacy clients that
        # omit it keep the old server-generated behavior.
        if normalized.get("op_id"):
            op.op_id = normalized["op_id"]
        op_ids.append(op.op_id)

    # ٢) supersession أوّلاً (لا نُثبّت عمليّات قديمة حلّت محلّها أحدث منها)
    superseded = apply_supersession(_OFFLINE_QUEUE, tenant_id)

    # ٣) نأخذ الدفعة الفعليّة من رأس الـqueue (FIFO، QUEUED فقط) — نفس ما كان
    #     sync_cycle سيعالجه — لنُثبّت بالضبط ما نعالج (إصلاح: كانت الكتابة تخصّ
    #     عمليّات هذا الطلب فقط بينما الـqueue قد يحوي أقدم، فتُعلَّم FAILED بلا رجعة).
    batch = _OFFLINE_QUEUE.peek_pending(tenant_id, limit=max(len(incoming_ops), 1))

    # ٤) نُثبّت كلّ عمليّة في الدفعة بمتانة ضمن سياق RLS. الناجح ⇒ SYNCED؛ الفاشل
    #    يبقى QUEUED (لا FAILED) ليُعاد في الدورة التالية (peek_pending يُرجع QUEUED
    #    فقط). إن لم تكن القاعدة مفعّلة، تبقى الكلّ QUEUED.
    started = datetime.now(UTC)
    synced = 0
    pending_retry = 0
    applied = 0
    conflicted = 0
    # حالة لكلّ عمليّة (op_id → applied/conflict/synced/queued) لتعرفها الواجهة وتحسم
    # تعارض field.update (409) محلّياً بدل تخمين عامّ من العدّادات الكلّيّة.
    op_status: dict[str, str] = {}
    if _DB_POOL is not None:
        from api.offline_pending_db import (
            claim_pending,
            enqueue_pending,
            mark_failed,
            mark_processed,
        )
        from api.offline_sync_db import (
            apply_field_update,
            dispatch_decision,
            persist_synced_operation,
        )

        async with tenant_connection(user) as conn:
            # إدامة الطابور المعلّق أوّلاً: تنجو العمليّات من إعادة تشغيل العمليّة
            # حتّى لو فشلت مزامنتها الآن (idempotent على op_id ⇒ لا تكرار).
            for op in batch:
                try:
                    async with conn.transaction():  # savepoint
                        await enqueue_pending(conn, op=op, tenant_id=tenant_id)
                except Exception as exc:  # noqa: BLE001 — fail-safe: الذاكريّ يبقى مرجعاً
                    logging.warning("sync: pending enqueue failed for %s: %s", op.op_id, exc)
            for op in batch:
                # مطالبة ذرّيّة pending→processing: عامل واحد فقط يفوز بالصفّ (حارس
                # تنفيذ مزدوج عند تزامن مزامنتَين على العمليّة نفسها). فشل المطالبة
                # (صفّ مُطالَب سلفاً/نهائيّ processed·failed/لم يُدَم بعد) ⇒ نتخطّى الأثر
                # الجانبيّ الدائم ونُبقيها QUEUED لإعادة المحاولة (fail-safe: لا إسقاط
                # ولا تطبيق مزدوج). تعذّر المطالبة نفسه (خطأ قاعدة) ⇒ ارتداد للسلوك
                # السابق (بلا حارس) كي لا نُعطّل المزامنة.
                try:
                    async with conn.transaction():  # savepoint
                        claimed = await claim_pending(conn, op_id=op.op_id)
                except Exception as exc:  # noqa: BLE001 — تعذّر المطالبة ⇒ نُكمل كالسابق
                    logging.warning("sync: claim failed for %s: %s", op.op_id, exc)
                    claimed = True
                if not claimed:
                    _OFFLINE_QUEUE.mark_status(tenant_id, op.op_id, SyncStatus.QUEUED)
                    op_status[op.op_id] = "queued"
                    pending_retry += 1
                    continue
                try:
                    # التوزيع (dispatch): field.update يُطبَّق فعليّاً بسلطة الخادم؛ كلّ
                    # نوع آخر يبقى سجلّ فقط (ledger-only، idempotent ON CONFLICT DO NOTHING).
                    if dispatch_decision(op.kind) == "apply":
                        async with conn.transaction():  # savepoint لكلّ عمليّة
                            outcome = await apply_field_update(conn, op=op, tenant_id=tenant_id)
                        if outcome == "conflict":
                            # سلطة الخادم: الإصدار القديم لا يطابق ⇒ 409. لا كتابة فوقيّة
                            # صامتة. نُعلّمها CONFLICTED (لا تُعاد محاولتها عمياءً — العميل
                            # يحسم ثمّ يُعيد بإصدار أحدث).
                            _OFFLINE_QUEUE.mark_status(tenant_id, op.op_id, SyncStatus.CONFLICTED)
                            op_status[op.op_id] = "conflict"
                            conflicted += 1
                            continue
                        # طُبِّق فعليّاً ⇒ نُدوّنه أيضاً في السجلّ (تتبّع/تدقيق) ثمّ SYNCED.
                        async with conn.transaction():
                            await persist_synced_operation(conn, op=op, tenant_id=tenant_id)
                        op_status[op.op_id] = "applied"
                        applied += 1
                    else:
                        async with conn.transaction():  # savepoint لكلّ عمليّة
                            await persist_synced_operation(conn, op=op, tenant_id=tenant_id)
                        op_status[op.op_id] = "synced"
                    _OFFLINE_QUEUE.mark_status(tenant_id, op.op_id, SyncStatus.SYNCED)
                    # طابور الإدامة: تُعلَّم processed (best-effort ضمن savepoint).
                    try:
                        async with conn.transaction():
                            await mark_processed(conn, op_id=op.op_id)
                    except Exception as exc2:  # noqa: BLE001 — لا يُفشِل المزامنة
                        logging.warning("sync: mark_processed failed for %s: %s", op.op_id, exc2)
                    synced += 1
                except Exception as exc:  # noqa: BLE001 — تبقى QUEUED لإعادة المحاولة
                    _OFFLINE_QUEUE.mark_status(
                        tenant_id, op.op_id, SyncStatus.QUEUED, error=str(exc)[:200]
                    )
                    op_status[op.op_id] = "queued"
                    try:
                        async with conn.transaction():
                            await mark_failed(conn, op_id=op.op_id, error=str(exc))
                    except Exception:  # noqa: BLE001 — تدوين أفضل-جهد فقط
                        pass
                    pending_retry += 1
                    logging.warning("sync: persist failed for op %s: %s", op.op_id, exc)
    else:
        pending_retry = len(batch)
        for op in batch:
            op_status[op.op_id] = "queued"
        logging.warning(
            "sync: DATABASE_URL غير مضبوط — بقيت %d عمليّة QUEUED لإعادة المحاولة", pending_retry
        )

    duration_ms = round((datetime.now(UTC) - started).total_seconds() * 1000, 2)
    if not batch:
        reason = "✅ لا عمليّات معلّقة للـsync"
    elif pending_retry == 0 and conflicted == 0:
        reason = f"✅ {synced} عمليّة sync بنجاح"
    else:
        reason = f"⚠️ {synced} sync، {pending_retry} معلّقة لإعادة المحاولة"
        if conflicted:
            reason += f"، {conflicted} تعارض (409) بانتظار حسم العميل"
    if superseded:
        reason += f" (+{superseded} مُلغاة بـsupersession)"

    result = {
        "status": "completed",
        "synced": synced,
        # العمليّات غير المُثبّتة تبقى QUEUED لإعادة المحاولة (لا FAILED). نفصل
        # العدّين: failed=الفشل النهائي الفعلي (0 هنا)، queued=ما سيُعاد.
        "failed": 0,
        "queued": pending_retry,
        # تعارض field.update (سلطة الخادم، 409): عُلِّم CONFLICTED ولم يُكتَب فوقيّاً.
        "conflicted": conflicted,
        # طُبِّق فعليّاً على fields (شريحة field.update). بقيّة الأنواع سجلّ فقط ضمن synced.
        "applied": applied,
        "superseded": superseded,
        "duration_ms": duration_ms,
        "reason_ar": reason,
        "op_ids": op_ids,
        # حالة لكلّ عمليّة (applied/conflict/synced/queued) — حقل إضافيّ، لا يكسر العقد.
        "op_status": op_status,
    }

    # مزامنة تفاضليّة: نُرفِق الـcursor الجديد (أحدث طابع في الدفعة) ليُرسله العميل
    # تالياً، ونُعلِن delta_applied بوضوح. حقول إضافيّة فقط — العقد القائم محفوظ
    # (لا يُرفَق شيء حين العلم مُطفأ ⇒ استجابة مطابقة للسلوك الحاليّ تماماً).
    if delta_applied:
        next_cursor = newest_cursor(batch)
        # ارتداد آمن: إن لم نحسب طابعاً جديداً (دفعة بلا تأريخ) نُعيد cursor العميل
        # كما هو حتى لا يفقد موضعه (لا يُعاد للصفر).
        result["cursor"] = next_cursor if next_cursor is not None else since
        result["delta_applied"] = True

    return result
