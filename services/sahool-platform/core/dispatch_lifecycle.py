"""core/dispatch_lifecycle.py — تصليب الموزِّع: دورة حياة التنفيذ + مفتاح اللاتكرار (نقيّ).

تصليب الحلقة المغلقة (المرحلة A، الشريحة 2). الموزِّع (decision_dispatch) يُدرِج قراراً
READY في الطابور (exec_status='queued')، لكن دون حارسين أساسيّين للتشغيل الفعليّ:

  1. **اللاتكرار (idempotency):** نداء execute مكرّر لنفس التوصية كان يُدرِج أمرين ⇒ خطر
     إطلاق مزدوج (ريّ/رشّ مرّتين). مفتاح حتميّ من (التوصية+الإجراء+الحقل) يَسِم القرار،
     وفهرس فريد جزئيّ على الحالات الحيّة (queued/dispatched) يمنع التكرار قاعديّاً.
  2. **دورة حياة صريحة:** exec_status كان ثلاثيّاً ساكناً (not_executed/queued/executed).
     المستهلِك (الشريحة 3) والسجلّ (الشريحة 4) يحتاجان حالتين وسيطتين: dispatched
     (سُلِّم للمستهلِك/أُخطِر البشر) وfailed. هذه الوحدة تحرس الانتقالات المسموحة فقط.

نقيّة وحتميّة (لا I/O): تُستعمَل في نقاط الموزِّع لاشتقاق المفتاح والتحقّق من الانتقال
قبل أيّ كتابة قاعدة. fail-closed: انتقال غير مسموح ⇒ ValueError (لا قفزة حالة صامتة).
"""

from __future__ import annotations

import hashlib

# دورة حياة التنفيذ — الانتقالات المسموحة فقط (البقيّة مرفوضة، fail-closed).
#   not_executed: نهائيّة (قرار BLOCKED/PENDING لم/لن يُنفَّذ).
#   queued      → dispatched (طالَب المستهلِك القرارَ وأخطر البشر) | failed.
#   dispatched  → executed (سُجِّلت نتيجة نجاح في السجلّ) | failed (نتيجة فشل).
#   executed/failed: نهائيّتان (لا انتقال بعدهما — السجلّ append-only).
_TRANSITIONS: dict[str, set[str]] = {
    "not_executed": set(),
    "queued": {"dispatched", "failed"},
    "dispatched": {"executed", "failed"},
    "executed": set(),
    "failed": set(),
}

_TERMINAL = {"not_executed", "executed", "failed"}

# الحالات «الحيّة» التي يحرسها فهرس اللاتكرار الفريد (قرار قيد المعالجة فعليّاً).
LIVE_EXEC_STATES = ("queued", "dispatched")


def is_valid_exec_status(status: str) -> bool:
    """هل القيمة حالة تنفيذ معروفة؟ (تطابق CHECK في migrations/v67)."""
    return (status or "").strip().lower() in _TRANSITIONS


def is_terminal(status: str) -> bool:
    """هل الحالة نهائيّة (لا انتقال بعدها)؟"""
    return (status or "").strip().lower() in _TERMINAL


def can_transition(current: str, target: str) -> bool:
    """هل الانتقال current→target مسموح في دورة الحياة؟ (نقيّ)."""
    cur = (current or "").strip().lower()
    tgt = (target or "").strip().lower()
    return tgt in _TRANSITIONS.get(cur, set())


def assert_transition(current: str, target: str) -> str:
    """يتحقّق من انتقال exec_status ويُعيد الهدف المُطبَّع — وإلّا ValueError (fail-closed).

    يُستعمَل قبل أيّ UPDATE على exec_status: لا قفزة حالة غير موثَّقة (queued→executed
    دون مرور بـdispatched، أو أيّ انتقال من حالة نهائيّة).
    """
    cur = (current or "").strip().lower()
    tgt = (target or "").strip().lower()
    if not is_valid_exec_status(cur):
        raise ValueError(f"حالة تنفيذ مصدر مجهولة: {current!r}")
    if not is_valid_exec_status(tgt):
        raise ValueError(f"حالة تنفيذ هدف مجهولة: {target!r}")
    if tgt not in _TRANSITIONS[cur]:
        raise ValueError(f"انتقال تنفيذ غير مسموح: {cur} ⇏ {tgt}")
    return tgt


def derive_idempotency_key(
    recommendation_id: str, action_type: str, field_id: str | None = None
) -> str:
    """يشتقّ مفتاح لاتكرار حتميّاً من هويّة القرار (نقيّ) — يمنع الإطلاق المزدوج.

    حتميّ: نفس (التوصية، الإجراء، الحقل) ⇒ نفس المفتاح دائماً، فيصطدم بالفهرس الفريد
    الجزئيّ (tenant_id, idempotency_key) للحالات الحيّة، فيُعاد القرار القائم لا يُكرَّر.
    قصير (sha1[:24]) ليناسب عمود VARCHAR(120) مع بادئة قابلة للقراءة.
    """
    rec = (recommendation_id or "").strip()
    act = (action_type or "").strip()
    fld = (field_id or "").strip()
    raw = f"{rec}|{act}|{fld}".encode()
    digest = hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:24]
    return f"disp:{digest}"
