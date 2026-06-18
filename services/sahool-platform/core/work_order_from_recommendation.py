"""core/work_order_from_recommendation.py — رابط نقيّ: توصية ⇐ أمر عمل (FOES slice 2).

نظام تنفيذ عمليّات المزرعة (FOES) يحوّل **التوصيات** (recommendations / AI_SUGGESTION)
إلى **أوامر عمل** قابلة للتنفيذ. هذه الوحدة هي الرابط (mapper) النقيّ: تأخذ توصية
كقاموس (dict) وتُنتج قاموساً جاهزاً للإدراج (INSERT) في جدول `work_orders`.

نقيّ تماماً وحتميّ: لا I/O ولا قاعدة بيانات ولا حالة عالميّة — مجرّد تحويل صرف.
يُعاد استعمال ثوابت `WO_TYPES` من `core.work_order` (لا تُعاد تعريفها هنا).

استدلال النوع (`_infer_wo_type`) يفحص حقل الإجراء/النوع في التوصية عربيّاً وإنجليزيّاً؛
إن تعذّر استنتاج نوع صالح يُعاد `None` (لا نخترع نوعاً).
"""

from __future__ import annotations

from core.work_order import WO_TYPES

# ── رسم الكلمات المفتاحيّة ⇐ نوع أمر العمل (عربيّ + إنجليزيّ) ──
# الترتيب مقصود: يُفحَص كلّ نوع بكلماته المفتاحيّة على نصّ الإجراء المُطبَّع.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "irrigation": ("irrig", "water", "ريّ", "ري", "سقي", "سقا"),
    "fertilization": ("fertil", "تسميد", "سماد", "تغذية"),
    "spraying": ("spray", "رشّ", "رش", "مبيد", "مكافحة"),
    "scouting": ("scout", "inspect", "فحص", "استكشاف", "كشف"),
    "harvest": ("harvest", "حصاد", "قطف", "جني"),
}


def _action_text(rec: dict) -> str:
    """يجمع الحقول الدالّة على الإجراء/النوع في نصّ واحد مُطبَّع (lower) للمطابقة."""
    parts: list[str] = []
    for key in ("action", "kind", "type", "wo_type", "category", "title"):
        value = rec.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _infer_wo_type(rec: dict) -> str | None:
    """يستنتج `wo_type` من نصّ إجراء التوصية، أو `None` إن تعذّر — لا يخترع نوعاً.

    `rec` قاموس التوصية. تُفحَص الكلمات المفتاحيّة العربيّة والإنجليزيّة؛ أوّل نوع
    تُطابَق إحدى كلماته يُعاد (والنوع المُعاد دائماً ضمن `WO_TYPES`).
    """
    text = _action_text(rec)
    if not text:
        return None
    for wo_type, keywords in _KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            # حارس صلابة: لا نُعيد إلّا ما هو معرَّف في WO_TYPES.
            return wo_type if wo_type in WO_TYPES else None
    return None


def _extract_recommendation_id(rec: dict) -> str | None:
    """يستخرج معرّف التوصية من `id` أو `recommendation_id` (نصّاً) أو `None`."""
    raw = rec.get("id")
    if raw is None:
        raw = rec.get("recommendation_id")
    return None if raw is None else str(raw)


def _build_payload(rec: dict) -> dict:
    """يبني حمولة (payload) أمر العمل من حقول التوصية الدالّة المتوفّرة فقط."""
    payload: dict = {}
    for key in ("reason_ar", "reason", "quantity", "unit", "priority", "due_date"):
        if key in rec and rec[key] is not None:
            payload[key] = rec[key]
    return payload


def recommendation_to_work_order(
    recommendation: dict, *, field_id: str, tenant_id: str
) -> dict | None:
    """يحوّل توصية إلى قاموس أمر عمل جاهز للإدراج في `work_orders`، أو `None`.

    يُعيد قاموساً بالأعمدة: `tenant_id`, `field_id`, `wo_type`, `status='planned'`,
    `recommendation_id`, `payload`. إن تعذّر استنتاج `wo_type` من التوصية يُعاد `None`
    (لا نخترع نوعاً). نقيّ تماماً: لا I/O.
    """
    wo_type = _infer_wo_type(recommendation)
    if wo_type is None:
        return None
    return {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "wo_type": wo_type,
        "status": "planned",
        "recommendation_id": _extract_recommendation_id(recommendation),
        "payload": _build_payload(recommendation),
    }


def recommendations_to_work_orders(recs: list, *, field_id: str, tenant_id: str) -> list[dict]:
    """يحوّل قائمة توصيات إلى قائمة أوامر عمل، مُسقِطاً ما تعذّر استنتاج نوعه (`None`)."""
    work_orders: list[dict] = []
    for rec in recs:
        wo = recommendation_to_work_order(rec, field_id=field_id, tenant_id=tenant_id)
        if wo is not None:
            work_orders.append(wo)
    return work_orders
