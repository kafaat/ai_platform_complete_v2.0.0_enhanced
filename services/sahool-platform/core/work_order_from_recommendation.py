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
    # G3 (F-D06): معرّف القرار حلقةٌ في سلسلة توصية ⇐ قرار ⇐ أمر عمل ⇐ مهمّة. كان يسقط هنا
    # فلا يُعرَف من أمر العمل أيّ قرارٍ أنتجه. يُحمَل نصّاً كما ورد (لا يُخترَع إن غاب).
    if rec.get("decision_id") is not None:
        payload["decision_id"] = str(rec["decision_id"])
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


# ── G3 (F-D06): أمر عمل ⇐ مهمّة حقل ─────────────────────────────────────────────────
# أوامر العمل التي ما زالت قبل التنفيذ هي وحدها ما يُشتقّ منه مهمّة: المنجَز/المُتحقَّق/الملغى
# لا يُعاد فتحه مهمّةً جديدة.
_TASKABLE_WO_STATUSES = frozenset({"planned", "assigned", "in_progress"})


def work_order_to_field_task(work_order: dict) -> dict | None:
    """مسوّدة صفّ ``field_tasks`` من أمر عمل، أو ``None`` إن كان أمر العمل مغلقاً.

    تنقل الحقل والنوع فقط وتُعلن مصدرها (``source_event_type``/``source_agent``)؛ لا تخترع
    أولويّةً ولا موعداً ولا ملاحظةً زراعيّة — الباقي قيم الجدول الافتراضيّة. الرابط بين
    الطرفين يُحفَظ في أمر العمل (``payload.field_task_id``) لا هنا. نقيّة: لا I/O.
    """
    if work_order.get("status") not in _TASKABLE_WO_STATUSES:
        return None
    return {
        "field_id": work_order["field_id"],
        "task_type": work_order["wo_type"],
        "status": "pending",
        "source_event_type": "WORK_ORDER_CREATED",
        "source_agent": "work-order",
    }


# ── G3 (F-D09): إغلاق المهمّة ⇐ نتيجة منسوبة (لا تحقّق) ─────────────────────────────
#: النتائج الصريحة المقبولة عند الإغلاق — تصنيفٌ لِما أبلغ به المنفّذ، لا حكمٌ زراعيّ.
OUTCOME_RESULTS: frozenset[str] = frozenset(
    {"achieved", "partially_achieved", "not_achieved", "inconclusive"}
)


def build_work_order_outcome(
    work_order: dict,
    *,
    task_id: str,
    result: str | None,
    evidence_ref: str | None,
    recorded_by: str,
) -> dict | None:
    """سجلّ نتيجة منسوب إلى التوصية والقرار، أو ``None`` حين لا نتيجة صريحة بدليلها.

    الإغلاق الإداريّ (بلا ``result`` أو بلا ``evidence_ref``) ليس تحقّقاً زراعيّاً فلا يُنتج
    سجلّاً. السجلّ المُنتَج ``verified=False`` دائماً: هو ما أبلغ به المنفّذ مع مرجع دليله،
    والتحقّق خطوةُ إنسانٍ لاحقة لا يدّعيها الإغلاق. نقيّة: لا I/O.
    """
    if result not in OUTCOME_RESULTS:
        return None
    evidence = (evidence_ref or "").strip()
    if not evidence:
        return None
    payload = work_order.get("payload") or {}
    return {
        "result": result,
        "evidence_ref": evidence,
        "task_id": str(task_id),
        "recommendation_id": work_order.get("recommendation_id"),
        "decision_id": payload.get("decision_id"),
        "recorded_by": str(recorded_by),
        "source": "task_close",
        "verified": False,
    }
