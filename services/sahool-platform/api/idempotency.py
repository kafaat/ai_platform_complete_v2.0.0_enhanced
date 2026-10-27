"""idempotency لنقاط الكتابة: مفتاح `Idempotency-Key` وسجلّ الأوامر.

نُقل من `api/main.py` كما هو، ويُعاد تصديره هناك لأنّ الراوترات تستورده من `api.main`.
وأُضيف هنا شرطُ المستأجر: صفٌّ مخزَّن لمستأجرٍ آخر لا يُعاد ناتجه أبداً.
"""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException

_KEY_REUSED = "Idempotency-Key أُعيد استعماله بحمولةٍ مختلفة — استعمل مفتاحاً جديداً"


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
    النتيجة المخزّنة بلا تنفيذ. الإعادة بينما الأصل قيد المعالجة/فشل: 409 (أعد لاحقاً).

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
        raise HTTPException(status_code=409, detail=_KEY_REUSED)
    # U06: طلبٌ ببصمة يُقارَن ببصمة الصفّ؛ صفٌّ قديم بلا بصمة لا يُعامَل إعادةً صادقة (Copilot #1001).
    wanted = (payload or {}).get("request_digest")
    stored = (existing.payload or {}).get("request_digest")
    if wanted and (stored is None or wanted != stored):
        raise HTTPException(status_code=409, detail=_KEY_REUSED)
    if existing.status == CommandStatus.SUCCEEDED:
        return existing.result  # نتيجة مخزّنة — لا إعادة تنفيذ (idempotent)
    raise HTTPException(status_code=409, detail="الأمر قيد المعالجة — أعد المحاولة لاحقاً")
