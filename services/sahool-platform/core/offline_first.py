"""
sahool_core.offline_first
===========================
البنية الصريحة للعمل بدون اتصال شبكي — تجسيد ما هو ضمني.

الفجوة المُسدّاة من تحليل AI Ag Template:
  "Edge Devices → Gateway → Cloud Streaming" يفترض connectivity مستمرّة.
  السياق اليمني: إنترنت متقطّع، الكهرباء أحياناً، المزارع في
  مناطق نائية. النواة كلها pure-Python (التدقيق الآلي أثبت)،
  لكن لا توثيق صريح ولا آلية sync queue.

النمط الفلسفي المتبنّى:
  • offline as default: النظام يعمل كاملاً بلا شبكة
  • online as enhancement: الشبكة تُغني، لا تُحدّد
  • sync explicit: عند توفّر الاتصال، queue يُفرَّغ صراحةً
  • conflict-aware: ما يحدث لو نفس البيانات أُدخلت في offline ثمّ من مصدر آخر؟

التمييز عن الأنظمة الغربية:
  Cropwise/FieldView يفترضون 24/7 cloud streaming.
  سهول يفترض sync حين الاتصال يأتي.

المبادئ المحفوظة:
  • صفر اختراع: queue ينتظر sync، لا "افتراض" أنّ الشبكة موجودة
  • شفّافية: كل عملية معلّقة لها reason_ar
  • Tenant isolation: كل tenant عنده queue منفصل
  • Pure functions: لا I/O فعلي، tests يكفي in-memory

التكامل:
  ← يستخدمه api_adapter لـsync حين عودة الاتصال
  ← يستخدمه recommendation_bridge لـcaching النتائج
  ← يستخدمه source_of_truth لـconflict resolution
  → يُغذّي farm_memory بأحداث pending sync

ما لم يُبنَ هنا (مُؤجَّل بمبرّر):
  • الاتصال الفعلي بالشبكة (طبقة خارجية)
  • SQLite/IndexedDB embedded storage (في الواجهة)
  • Background sync workers (يحتاج runtime محدّد)
  → هذه wrappers خفيفة فوق ما يُبنى هنا
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class SyncStatus(str, Enum):
    """حالة عملية معلّقة للـsync."""

    QUEUED = "queued"  # تنتظر sync
    SYNCING = "syncing"  # قيد المزامنة
    SYNCED = "synced"  # تمّت بنجاح
    FAILED = "failed"  # فشلت (سبب صريح)
    SUPERSEDED = "superseded"  # حلّت محلّها عملية أحدث
    CONFLICTED = "conflicted"  # تضارب مع server data


class OperationKind(str, Enum):
    """أنواع العمليات القابلة للـqueue.

    القيم القديمة محفوظة بقيمها النصّيّة كما هي (لا كسر للعقد ولا للبيانات
    المُخزّنة سلفاً). الإضافات تُعدِّد العمليّات القابلة للإنشاء offline التي
    تقبلها/تُرسلها مسارات المنصّة فعليّاً (تدقيق ‎api/routers/*‎)، فيتّسع
    التعداد ليطابق ما يُرسله العميل بدل رفضه بـ400.
    """

    # ── قيم أصليّة (محفوظة — لا تُغيَّر قيمها النصّيّة) ──────────────────
    OBSERVATION_CREATE = "observation_create"
    ACTIVITY_COMPLETE = "activity_complete"
    ACTIVITY_SKIP = "activity_skip"
    RECOMMENDATION_REQUEST = "recommendation_request"
    CALIBRATION_RECORD = "calibration_record"

    # ── توسيع: عمليّات mutating أخرى يُنشئها العميل offline ───────────
    TASK_UPDATE = "task_update"  # PATCH /api/v1/tasks/{id} (إكمال/تأجيل مهمّة)
    DECISION_RECORD = "decision_record"  # POST /api/v1/decision/record
    OUTCOME_RECORD = "outcome_record"  # POST /api/v1/outcome/record|measure
    IRRIGATION_PLAN = "irrigation_plan"  # POST /api/v1/irrigation-plan
    HARVEST_LOT_CREATE = "harvest_lot_create"  # POST /api/v1/harvest-lots
    RECOMMENDATION_OUTCOME = "recommendation_outcome"  # POST …/recommendations/outcomes
    SOIL_LAB_TEST = "soil_lab_test"  # نتيجة مختبر تربة تُسجَّل ميدانيّاً
    PHOTO_UPLOAD = "photo_upload"  # رفع صورة حقل ملتقطة offline


@dataclass
class PendingOperation:
    """عملية تنتظر sync. خفيفة، self-contained."""

    op_id: str  # UUID داخلي
    tenant_id: str
    kind: OperationKind
    payload: dict
    created_at: str  # ISO، حين أُنشئت offline
    user_id: str  # من أنشأها
    status: SyncStatus = SyncStatus.QUEUED
    retry_count: int = 0
    last_attempt_at: str | None = None
    last_error: str | None = None
    synced_at: str | None = None
    conflict_with: str | None = None  # op_id آخر إن تضارب


@dataclass
class SyncResult:
    """نتيجة دورة sync كاملة."""

    total_pending: int
    synced_count: int
    failed_count: int
    conflicted_count: int
    superseded_count: int
    duration_ms: float
    reason_ar: str


# ─── Queue Management (per-tenant) ───────────────────────────────


class OfflineQueue:
    """طابور عمليّات معلّقة. multi-tenant by design.

    قواعد ذهبية:
      • كل tenant عنده queue منفصل (isolation تامّ)
      • العمليات تُنفَّذ بترتيب الإنشاء (FIFO)
      • العمليات المتعلّقة (مثل observation ثمّ recommendation عليها)
        تُحفظ في الترتيب الصحيح
      • Superseded: لو عمليّة لاحقة تُغيّر نفس الكيان، الأقدم تُلغى
    """

    def __init__(self, max_per_tenant: int = 1000):
        self.max_per_tenant = max_per_tenant
        # tenant_id → deque[PendingOperation]
        self._queues: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_per_tenant))

    def enqueue(self, op: PendingOperation) -> bool:
        """يضيف عملية للـqueue. يرفض إن تجاوز الحدّ."""
        q = self._queues[op.tenant_id]
        if len(q) >= self.max_per_tenant:
            return False
        q.append(op)
        return True

    def peek_pending(self, tenant_id: str, limit: int = 100) -> list[PendingOperation]:
        """يعرض العمليات المعلّقة دون إخراجها."""
        q = self._queues.get(tenant_id)
        if not q:
            return []
        return [op for op in q if op.status == SyncStatus.QUEUED][:limit]

    def queue_size(self, tenant_id: str) -> int:
        return len(self._queues.get(tenant_id, []))

    def total_pending(self, tenant_id: str) -> int:
        q = self._queues.get(tenant_id, deque())
        return sum(1 for op in q if op.status == SyncStatus.QUEUED)

    def mark_status(
        self, tenant_id: str, op_id: str, status: SyncStatus, error: str | None = None
    ) -> bool:
        """يحدّث حالة عمليّة معيّنة."""
        q = self._queues.get(tenant_id, deque())
        for op in q:
            if op.op_id == op_id:
                op.status = status
                op.last_attempt_at = datetime.utcnow().isoformat()
                if error:
                    op.last_error = error
                    op.retry_count += 1
                if status == SyncStatus.SYNCED:
                    op.synced_at = datetime.utcnow().isoformat()
                return True
        return False

    def clear_synced(self, tenant_id: str, older_than_hours: int = 24) -> int:
        """ينظّف العمليّات المُنجزة. retention للـaudit."""
        cutoff = (datetime.utcnow() - timedelta(hours=older_than_hours)).isoformat()
        q = self._queues.get(tenant_id)
        if not q:
            return 0
        before = len(q)
        # rebuild deque بدون العمليّات المُتقادمة
        kept = deque(
            (
                op
                for op in q
                if not (op.status == SyncStatus.SYNCED and op.synced_at and op.synced_at < cutoff)
            ),
            maxlen=self.max_per_tenant,
        )
        self._queues[tenant_id] = kept
        return before - len(kept)

    def reset(self, tenant_id: str | None = None) -> None:
        """إعادة تعيين (للاختبارات)."""
        if tenant_id:
            self._queues.pop(tenant_id, None)
        else:
            self._queues.clear()


# ─── Supersession Logic ──────────────────────────────────────────


def detect_superseded(
    queue: list[PendingOperation],
) -> list[tuple[str, str]]:
    """يكشف العمليات التي حلّت محلّها أخرى.

    قاعدة: لو عمليّتان من نفس النوع على نفس الكيان (field_id, observable_id)،
    الأقدم تصبح SUPERSEDED.

    يُرجع [(op_id_old, op_id_new), ...]
    """
    superseded_pairs: list[tuple[str, str]] = []

    # نمرّ على activity_complete مثلاً، لنفس activity_id
    # observation_create لنفس (field_id, observable_id, measured_at)
    by_key: dict[tuple, str] = {}
    for op in queue:
        if op.status != SyncStatus.QUEUED:
            continue
        key = (
            op.kind,
            op.payload.get("field_id"),
            op.payload.get("activity_id") or op.payload.get("observable_id"),
        )
        if None in key:
            continue
        prev = by_key.get(key)
        if prev:
            superseded_pairs.append((prev, op.op_id))
        by_key[key] = op.op_id

    return superseded_pairs


def apply_supersession(
    queue: OfflineQueue,
    tenant_id: str,
) -> int:
    """يطبّق supersession آلياً. يُرجع عدد العمليات المُلغاة."""
    pending = queue.peek_pending(tenant_id, limit=10000)
    pairs = detect_superseded(pending)
    count = 0
    for old_id, new_id in pairs:
        if queue.mark_status(tenant_id, old_id, SyncStatus.SUPERSEDED, error=f"حلّت محلّها {new_id}"):
            count += 1
    return count


# ─── Sync Cycle ──────────────────────────────────────────────────


def sync_cycle(
    queue: OfflineQueue,
    tenant_id: str,
    *,
    sync_handler,  # callable(op: PendingOperation) -> bool
    max_batch: int = 50,
) -> SyncResult:
    """ينفّذ دورة sync واحدة.

    sync_handler: دالّة يُمرّرها المستدعي (تتولّى الـHTTP الفعلي).
    Pure function: ECP لا يقرّر شيئاً في الشبكة، فقط يدير الـqueue.

    قاعدة ذهبية: لو الـhandler رفع exception، تُعتبر العمليّة FAILED
    لكنّها تبقى في الـqueue للمحاولة لاحقاً (لا تُحذف).
    """
    start = datetime.utcnow()
    # ١. طبّق supersession أوّلاً (لا نُرسل عمليّات قديمة بلا داعٍ)
    superseded_now = apply_supersession(queue, tenant_id)

    # ٢. خذ الـpending الفعلية
    pending = queue.peek_pending(tenant_id, limit=max_batch)

    synced = 0
    failed = 0
    conflicted = 0

    for op in pending:
        queue.mark_status(tenant_id, op.op_id, SyncStatus.SYNCING)
        try:
            success = sync_handler(op)
            if success:
                queue.mark_status(tenant_id, op.op_id, SyncStatus.SYNCED)
                synced += 1
            else:
                queue.mark_status(
                    tenant_id, op.op_id, SyncStatus.FAILED, error="handler returned False"
                )
                failed += 1
        except Exception as e:
            err_msg = str(e)[:200]
            # تمييز conflict عن failure عادي
            if "conflict" in err_msg.lower() or "duplicate" in err_msg.lower():
                queue.mark_status(tenant_id, op.op_id, SyncStatus.CONFLICTED, error=err_msg)
                conflicted += 1
            else:
                queue.mark_status(tenant_id, op.op_id, SyncStatus.FAILED, error=err_msg)
                failed += 1

    duration = (datetime.utcnow() - start).total_seconds() * 1000

    total = len(pending)
    if total == 0:
        reason = "✅ لا عمليّات معلّقة للـsync"
    elif failed == 0 and conflicted == 0:
        reason = f"✅ {synced} عمليّة sync بنجاح"
    elif conflicted > 0:
        reason = f"⚠️ {synced} sync، {conflicted} تضارب يحتاج مراجعة، {failed} فشل"
    else:
        reason = f"⚠️ {synced} sync، {failed} فشل (سيُعاد لاحقاً)"

    if superseded_now > 0:
        reason += f" (+{superseded_now} عمليّة مُلغاة بـsupersession)"

    return SyncResult(
        total_pending=total,
        synced_count=synced,
        failed_count=failed,
        conflicted_count=conflicted,
        superseded_count=superseded_now,
        duration_ms=round(duration, 2),
        reason_ar=reason,
    )


# ─── Offline-Aware Helpers للـClient ──────────────────────────────


@dataclass
class ConnectivityState:
    """حالة الاتصال الحالية — يضبطها client بناءً على ping أو network event."""

    is_online: bool
    last_check_at: str
    consecutive_failures: int = 0
    reason_ar: str = ""


def record_operation_offline(
    queue: OfflineQueue,
    *,
    tenant_id: str,
    user_id: str,
    kind: OperationKind,
    payload: dict,
) -> PendingOperation:
    """يسجّل عملية أثناء الـoffline. النواة المُوصى بها للـclient.

    التطبيق:
      • client يفحص ConnectivityState
      • لو offline: يستدعي record_operation_offline
      • لو online: يستدعي API مباشرة، fallback لـoffline عند فشل
    """
    import uuid as uuid_mod

    op = PendingOperation(
        op_id=str(uuid_mod.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        kind=kind,
        payload=payload,
        created_at=datetime.utcnow().isoformat(),
    )
    queue.enqueue(op)
    return op


def queue_summary(queue: OfflineQueue, tenant_id: str) -> dict:
    """ملخّص الـqueue لـtenant. للواجهة وللتشخيص."""
    q = queue._queues.get(tenant_id, deque())
    by_status: dict = defaultdict(int)
    by_kind: dict = defaultdict(int)
    for op in q:
        by_status[op.status.value] += 1
        by_kind[op.kind.value] += 1

    return {
        "tenant_id": tenant_id,
        "total_in_queue": len(q),
        "by_status": dict(by_status),
        "by_kind": dict(by_kind),
        "summary_ar": (
            f"queue: {len(q)} عمليّة، "
            f"{by_status.get('queued', 0)} منها معلّقة للـsync، "
            f"{by_status.get('failed', 0)} فشلت، "
            f"{by_status.get('conflicted', 0)} تحتاج مراجعة"
        ),
    }
