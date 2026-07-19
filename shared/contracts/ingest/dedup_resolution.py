"""حلّ تعارض dedup للإدخال الخارجيّ (SCOUT-INGEST-01 / B1.2) — منطق صرف.

**درس محفور:** ``ON CONFLICT DO NOTHING`` الصامت أُعدِم في هذه الجلسة مرّتين — ابتلاعه
حدثاً هو أخطر ما يكون عند dedup. «نفس مفتاح، جسم مختلف» (جهاز أعاد الإرسال بعد تعديل
الاستمارة، أو مصدر ملوّث يعيد استخدام مفاتيح) **حدث يجب أن يُرى**، لا يُبتلع:

- لا صفّ موجود        ⇒ ``insert_new`` (يُخزَّن بحالة التحقّق السباعي — B1.1).
- موجود، **جسم مطابق** ⇒ ``idempotent_replay`` (200 صادق، نفس الصفّ — لا تخزين مكرّر).
- موجود، **جسم مختلف** ⇒ ``quarantine_divergent``: يُخزَّن بمفتاح **مشتقّ** (لا يصطدم)
  و``trust_status='quarantined'`` وسبب ``duplicate_key_divergent_payload`` — الحدث مرئيّ.

الوصول ≠ الثقة يمتدّ إلى **سكون الـdedup نفسه**. وحدة صرفة (لا قاعدة) — يُستدعى من مسار
الكتابة (B1.2b) بعد استعلام الصفّ الموجود.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DIVERGENT_PAYLOAD_REASON = "duplicate_key_divergent_payload"


@dataclass(frozen=True)
class DedupDecision:
    action: Literal["insert_new", "idempotent_replay", "quarantine_divergent"]
    storage_key: str  # المفتاح الفعليّ للتخزين (مشتقّ للمتباين كي لا يصطدم)
    quarantined: bool
    quarantine_reasons: tuple[str, ...]


def _divergent_key(base_key: str, incoming_content_hash: str) -> str:
    """مفتاح تخزين مشتقّ للصفّ المتباين — فريد لكلّ جسم مختلف، ثابت لإعادة إرساله.

    نلحق بادئة hash الجسم ⇒ جسمان مختلفان لنفس المفتاح ⇒ مفتاحان مختلفان (لا اصطدام)؛
    وإعادة إرسال نفس الجسم المتباين ⇒ نفس المفتاح المشتقّ ⇒ idempotent لذلك المتباين أيضاً.
    """
    return f"{base_key}#dup-{incoming_content_hash[:12]}"


def resolve_dedup(
    *, base_key: str, incoming_content_hash: str, existing_content_hash: str | None
) -> DedupDecision:
    """يقرّر مصير إدخال بالنظر إلى الصفّ الموجود (إن وُجد) — لا ابتلاع صامت لأيّ تعارض."""
    if existing_content_hash is None:
        return DedupDecision("insert_new", base_key, False, ())
    if existing_content_hash == incoming_content_hash:
        # نفس المفتاح ونفس الجسم ⇒ إعادة إرسال صادقة (idempotent) — لا تخزين مكرّر.
        return DedupDecision("idempotent_replay", base_key, False, ())
    # نفس المفتاح، جسم مختلف ⇒ حدث يُرى: quarantine بمفتاح مشتقّ، لا سقوط صامت.
    return DedupDecision(
        "quarantine_divergent",
        _divergent_key(base_key, incoming_content_hash),
        True,
        (DIVERGENT_PAYLOAD_REASON,),
    )
