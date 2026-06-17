"""core/execution_ledger_entry.py — سجلّ التنفيذ: قيد نتيجة قرار مُسلَّم (نقيّ، تدقيق).

إغلاق الحلقة وقياسها (المرحلة A، الشريحة 4). بعد أن يُستهلَك القرار (dispatched) ويُنفّذه
البشر يدويّاً، **ماذا حدث فعلاً؟** هذه الوحدة تبني قيد سجلّ تنفيذ append-only يربط
القرار بنتيجته (executed/failed) مع بصمة تدقيق (content_hash) تكشف أيّ تلاعب لاحق.
هذا هو «الأثر المُقاس» الذي رصد التدقيق غيابه: توصية ← قرار ← أمر ← **نتيجة**.

نقيّة وحتميّة (لا I/O): تأخذ صفّ قرار + نتيجة، تُرجِع قيداً جاهزاً للإدراج. fail-closed:
نتيجة غير (executed|failed) ⇒ ValueError (لا قيد بحالة مجهولة). البصمة قانونيّة
(sort_keys + فواصل ثابتة) فتُعاد حسابها للتحقّق. تُكمِّل دفتر المزرعة (farm_ledger)
الماليّ: ذاك يسجّل التكلفة، وهذا يسجّل التنفيذ التشغيليّ — مرجع متبادَل بـdecision_id.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# نتائج التنفيذ المسموحة في السجلّ (نهائيّتان — تطابقان دورة حياة exec_status).
OUTCOMES = ("executed", "failed")


def compute_ledger_hash(
    decision_id: str, outcome: str, recorded_at: str, detail: dict[str, Any] | None
) -> str:
    """SHA-256 حتميّ لمحتوى قيد التنفيذ — يكشف أيّ تلاعب لاحق بالسجلّ append-only.

    تمثيل قانونيّ (sort_keys + فواصل ثابتة) ⇒ نفس البصمة لنفس المحتوى بصرف النظر عن
    ترتيب المفاتيح. نقيّ وحتميّ (قابل لإعادة الحساب والتحقّق) — مرآة compute_event_hash.
    """
    canonical = json.dumps(
        {
            "decision": decision_id,
            "outcome": outcome,
            "at": recorded_at,
            "detail": detail or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_outcome(outcome: str) -> str:
    """يتحقّق من نتيجة التنفيذ ويُعيدها مُطبّعة — مجهولة ⇒ ValueError (fail-closed)."""
    o = (outcome or "").strip().lower()
    if o not in OUTCOMES:
        raise ValueError(f"نتيجة تنفيذ مجهولة: {outcome!r} (المسموح: {', '.join(OUTCOMES)})")
    return o


def build_ledger_entry(
    decision_row: Any,
    *,
    outcome: str,
    recorded_at: str,
    channel: str | None = None,
    note_ar: str = "",
    detail: dict[str, Any] | None = None,
) -> dict:
    """يبني قيد سجلّ تنفيذ من صفّ قرار + نتيجة (نقيّ) — جاهز للإدراج append-only.

    `decision_row`: قاموس/سجلّ بمفاتيح dispatch_decisions. `outcome`: executed|failed
    (غيرها ⇒ ValueError). يحسب content_hash من (القرار، النتيجة، الوقت، التفاصيل) للتدقيق.
    الصدق: يبني القيد فقط — الإدراج وانتقال exec_status مسؤوليّة المُنادي (معاملة واحدة).
    """

    def _get(key, default=None):
        try:
            return decision_row[key]
        except (KeyError, TypeError, IndexError):
            return getattr(decision_row, key, default)

    out = normalize_outcome(outcome)
    decision_id = _get("decision_id")
    merged_detail = dict(detail or {})
    content_hash = compute_ledger_hash(decision_id, out, recorded_at, merged_detail)
    return {
        "decision_id": decision_id,
        "action_type": _get("action_type"),
        "field_id": _get("field_id"),
        "channel": (channel or "").strip().lower() or None,
        "outcome": out,
        "note_ar": note_ar or "",
        "detail": merged_detail,
        "content_hash": content_hash,
        "recorded_at": recorded_at,
    }
