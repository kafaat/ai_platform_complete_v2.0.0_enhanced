"""idempotency لنقاط الكتابة: مفتاح `Idempotency-Key` وسجلّ الأوامر.

نُقل من `api/main.py` كما هو، ويُعاد تصديره هناك لأنّ الراوترات تستورده من `api.main`.
وأُضيف هنا شرطُ المستأجر: صفٌّ مخزَّن لمستأجرٍ آخر لا يُعاد ناتجه أبداً.

عقد الخادم (D4، 2026-10-27):

* **المفتاح مربوطٌ بالمستأجر ونوع العمليّة.** صفٌّ لمستأجرٍ آخر، أو لنوع عمليّةٍ آخر
  (`command_type`)، لا يُعاد ناتجه ولا يُنفَّذ العمل؛ الردّ 409 ``payload_mismatch``.
  والوصول إلى الناتج المخزَّن يمرّ أوّلاً بترخيص المسار نفسه (``require_permission``).
* **البصمة من تمثيلٍ موحَّد للحمولة المؤثّرة** (`request_digest`): JSON بمفاتيح مرتّبة
  لنموذج الطلب بعد التحقّق (القيم الافتراضيّة مُطبَّقة)، فترتيب مفاتيح JSON لا يصنع تعارضاً.
* **الأمر والتغيير في معاملة PostgreSQL واحدة:** `_idempotent` يُستدعى داخل
  ``tenant_connection`` فيُدرَج صفّ الأمر ويُنفَّذ العمل ويُسجَّل الناتج على الاتّصال
  نفسه؛ فشل العمل يُرجِع الثلاثة معاً. أثرٌ خارج القاعدة (HTTP/طابور) لا تشمله المعاملة
  ويحتاج ضمانه الخاصّ.
* **409 بسببٍ ثابت** في ``detail.reason``: ``payload_mismatch`` (المفتاح نفسه لحمولةٍ أو
  عمليّةٍ أو مستأجرٍ آخر) · ``in_progress`` (الأصل لم يكتمل) · ``retention_expired``
  (انقضت مدّة الاحتفاظ). ونصّ ``message_ar`` لا يدفع أبداً إلى إنشاءٍ بمفتاحٍ جديد.
* **مدّة الاحتفاظ:** يُعاد الناتج المخزَّن ``SAHOOL_IDEMPOTENCY_RETENTION_DAYS`` يوماً
  (الافتراضيّ 30) من إنشاء الأمر. بعدها يُردّ 409 ``retention_expired``: لا يُعاد الناتج
  (قد يكون المورد تغيّر) **ولا يُنفَّذ العمل ثانيةً**، والعميل يُصالِح بقراءة الموارد. صفوف
  ``commands`` لا تُحذف (لا مهمّة تنظيف في المنصّة)، وبقاء الصفّ هو ما يمنع التنفيذ المكرّر
  بعد المدّة؛ حذفُها يدويّاً يُعيد فتح المفتاح للتنفيذ.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException

#: أسباب 409 الثابتة — يقرؤها المستهلك (الموبايل) بدل نصّ الرسالة.
REASON_PAYLOAD_MISMATCH = "payload_mismatch"
REASON_IN_PROGRESS = "in_progress"
REASON_RETENTION_EXPIRED = "retention_expired"

DEFAULT_RETENTION_DAYS = 30

_MSG_PAYLOAD_MISMATCH = (
    "هذه العملية أُرسلت سابقاً بنفس المعرّف. استعِد نتيجة المحاولة السابقة أولاً، ولا تُنشئ سجلاً جديداً."
)
_MSG_IN_PROGRESS = (
    "المحاولة السابقة بنفس المعرّف ما زالت قيد المعالجة — تحقّق منها لاحقاً بالمعرّف نفسه."
)
_MSG_RETENTION_EXPIRED = (
    "انقضت مدّة الاحتفاظ بنتيجة هذه العملية على الخادم. لم تُنفَّذ ثانيةً — راجع السجلّات "
    "القائمة لمطابقة النتيجة، ولا تُنشئ سجلاً جديداً."
)


def retention_days() -> int:
    """مدّة إعادة الناتج المخزَّن بالأيّام (``SAHOOL_IDEMPOTENCY_RETENTION_DAYS``، ≥ 1)."""
    raw = os.getenv("SAHOOL_IDEMPOTENCY_RETENTION_DAYS", "")
    try:
        days = int(raw) if raw.strip() else DEFAULT_RETENTION_DAYS
    except ValueError:
        days = DEFAULT_RETENTION_DAYS
    return max(days, 1)


def _now() -> datetime:
    return datetime.now(UTC)


def request_digest(effective_payload) -> str:
    """بصمة SHA-256 لتمثيلٍ موحَّد (JSON بمفاتيح مرتّبة) للحمولة المؤثّرة.

    التسلسل نفسه الذي خزّنته جداول الريّ منذ UI-M2، فالبصمات المخزَّنة قبله تبقى مطابقة.
    """
    canonical = json.dumps(effective_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _conflict(reason: str, message_ar: str, **extra) -> HTTPException:
    detail = {"code": "idempotency_conflict", "reason": reason, "message_ar": message_ar}
    detail.update(extra)
    return HTTPException(status_code=409, detail=detail)


def _same_tenant(stored, requested) -> bool:
    """مقارنة معرّفَي مستأجر بصيغتهما القانونيّة (UUID)، لا بنصّهما الحرفيّ."""
    try:
        return uuid.UUID(str(stored)) == uuid.UUID(str(requested))
    except ValueError:
        return str(stored) == str(requested)


# ─── idempotency لنقاط الموبايل (إعادات offline لا تُكرّر الكتابة) ──────────────
# الموبايل قد يُعيد POST نفسه (شبكة ضعيفة/مزامنة batch بعد انقطاع). بمفتاح
# Idempotency-Key (UUID) يُسجَّل الأمر مرّة واحدة في جدول commands؛ الإعادة تُعيد
# النتيجة المخزّنة بلا إعادة تنفيذ. كلّ شيء داخل معاملة tenant_connection (RLS +
# ذرّيّة): فشل العمل ⇒ ارتداد كامل (بما فيه أثر الأمر) ⇒ إعادة آمنة. بلا مفتاح ⇒
# تنفيذ عاديّ (توافق خلفيّ كامل — لا يتغيّر سلوك العملاء القائمين).
def _idem_key(idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> str | None:
    """يستخرج مفتاح الإيدمبوتنسي (UUID) ويتحقّق من شكله.

    فارغ/مسافات ⇒ يُعامَل كغياب (None، تنفيذ عاديّ)؛ قيمة غير فارغة غير صالحة ⇒ 400
    (لا تضيع idempotency بصمت لمفتاح مُشوَّه). يُعيد المفتاح بعد strip.
    """
    if idempotency_key is None:
        return None
    key = idempotency_key.strip()
    if not key:
        return None
    try:
        uuid.UUID(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Idempotency-Key يجب أن يكون UUID") from e
    return key


async def _idempotent(store, command_id, do_work, *, command_type, actor_id, tenant_id, payload):
    """منطق idempotency نقيّ (store مُحقَن ⇒ قابل للاختبار). يُرجِع نتيجة العمل (JSON).

    أوّل مرّة: يُدرِج الأمر، ينفّذ do_work، يسجّل النتيجة. الإعادة الناجحة: يُعيد
    النتيجة المخزّنة بلا تنفيذ. الإعادة بينما الأصل قيد المعالجة/فشل: 409 ``in_progress``؛
    مستأجر/نوع/بصمة مختلفة: 409 ``payload_mismatch``؛ بعد مدّة الاحتفاظ: 409
    ``retention_expired`` (انظر عقد الوحدة أعلاه).

    قيد تصميميّ مهمّ: يجب استدعاؤه **داخل معاملة تَرتدّ عند الفشل** (مثل
    tenant_connection). الاعتماد على الارتداد هو ما يجعله سليماً: فشل do_work ⇒
    ارتداد إدراج الأمر أيضاً ⇒ لا أمر «pending» يتيم، والإعادة اللاحقة تُنفَّذ من
    جديد بأمان (لا تعلّق على 409 أبديّ). لذا لا نُعلّم processing/failed صراحةً —
    الارتداد يتكفّل، والتعليم داخل المعاملة سيُرتَدّ بلا فائدة. لا تستخدمه خارج معاملة.
    """
    from api.command_store import Command, CommandSource, CommandStatus

    cmd = Command.new(
        command_type,
        actor_id,
        tenant_id,
        payload,
        source=CommandSource.MOBILE,
        command_id=command_id,
    )
    if await store.insert(cmd):  # أُدرِج الآن ⇒ تنفيذ أوّل
        result = await do_work()
        await store.mark_succeeded(command_id, result)
        return result
    existing = await store.get(command_id)  # موجود مسبقاً
    # المفتاح فريدٌ عبر كلّ المستأجرين (`commands.command_id` مفتاح أساسيّ). تحت دورٍ
    # مقيّد يُخفي RLS صفَّ غيرك فيصل `None` — ولا تفسير آخر له، فالمعاملة المرتدّة كانت
    # ستُبقي الإدراج ناجحاً. وتحت دورٍ يتجاوز RLS يصل الصفّ نفسه. في الحالتين: لا ناتج،
    # ولا «أعد المحاولة» لمفتاحٍ لن يصير لك، والرسالة رسالة تعارض الحمولة
    # (PLATFORM-IDEMPOTENCY-STORE-NOT-TENANT-BOUND-01).
    if existing is None or not _same_tenant(existing.tenant_id, tenant_id):
        raise _conflict(REASON_PAYLOAD_MISMATCH, _MSG_PAYLOAD_MISMATCH)
    # D4: المفتاح مربوطٌ بنوع العمليّة أيضاً — مفتاح «إنشاء حقل» لا يُعيد ناتجه لـ«إنشاء موسم».
    if existing.command_type != command_type:
        raise _conflict(REASON_PAYLOAD_MISMATCH, _MSG_PAYLOAD_MISMATCH)
    # U06: طلبٌ ببصمة يُقارَن ببصمة الصفّ؛ صفٌّ قديم بلا بصمة لا يُعامَل إعادةً صادقة (Copilot #1001).
    wanted = (payload or {}).get("request_digest")
    stored = (existing.payload or {}).get("request_digest")
    if wanted and (stored is None or wanted != stored):
        raise _conflict(REASON_PAYLOAD_MISMATCH, _MSG_PAYLOAD_MISMATCH)
    if existing.status != CommandStatus.SUCCEEDED:
        raise _conflict(REASON_IN_PROGRESS, _MSG_IN_PROGRESS)
    days = retention_days()
    created = existing.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)  # TIMESTAMPTZ يصل واعياً؛ الساذج يُقرأ UTC
    if created is not None and _now() - created > timedelta(days=days):
        # بعد المدّة: لا ناتج قديم ولا تنفيذ ثانٍ — مصالحةٌ لا إنشاء (R13).
        raise _conflict(REASON_RETENTION_EXPIRED, _MSG_RETENTION_EXPIRED, retention_days=days)
    return existing.result  # نتيجة مخزّنة — لا إعادة تنفيذ (idempotent)
