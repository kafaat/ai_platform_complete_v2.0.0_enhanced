"""api/canonical_boundary.py — قارئ ثقة الحدود الكنسيّة (Bundle B) — قراءة صرفة، بلا حساب.

الغرض:
   يطبّع صفّ جودة الحدّ المخزَّن (``field_boundaries``: ``confidence_score`` /
   ``source_type`` / ``model_version`` / ``review_status`` — يكتبها مسار التهديف
   ``api/routers/boundaries.py`` عبر ``boundary_confidence.score_boundary``) إلى
   **كتلة كنسيّة واحدة** تقرؤها الحالة القانونيّة والمستهلكون من **مصدر واحد**،
   فلا تُقرأ ثقة الحدّ من أماكن متفرّقة ولا يُعاد تهديفها.

صدق صريح — ما هذا وما ليس هو:
   قارئ **نقيّ لا يحسب ثقة** (التهديف عمل ``score_boundary`` الحتميّ). يقرأ القيمة
   المخزَّنة فقط. غياب ``confidence_score`` (لا تهديف بعد) ⇒ ``None`` — لا كتلة
   مُلفّقة ولا تصعيد على قيمة غائبة. fail-safe: مدخل غير صالح ⇒ ``None`` (لا يَرمي).

علاقته بالتصعيد:
   ``review_recommended`` يُحسَب من نفس عتبة ``score_boundary``
   (``CONFIDENCE_REVIEW_THRESHOLD`` — مصدر واحد للعتبة) كي يُصعّد الإسقاط نمط
   التنفيذ للمراجعة البشريّة عند انخفاض ثقة الحدّ (نظير تصعيد الملوحة الحرجة).
"""

from __future__ import annotations

from api.boundary_confidence import CONFIDENCE_REVIEW_THRESHOLD

_PASSTHROUGH = (
    ("boundary_source", "source_type"),
    ("boundary_version", "model_version"),
    ("review_status", "review_status"),
)


def canonical_boundary(row: dict | None) -> dict | None:
    """يطبّع صفّ جودة حدّ الحقل إلى كتلة كنسيّة، أو ``None`` عند غياب الثقة.

    المُدخل ``row`` — dict (أو None) بمفاتيح ``field_boundaries``:
        ``confidence_score`` (0..1) · ``source_type`` · ``model_version`` ·
        ``review_status``. الناقص يُعامَل بأمان (لا يَرمي).

    المُخرَج — dict أو None:
        - ``boundary_confidence``  (float 0..1, مُقرَّبة)
        - ``boundary_source``      (str|None)  مصدر الحدّ (provenance)
        - ``boundary_version``     (str|None)  إصدار محرّك الاستخلاص
        - ``review_status``        (str|None)  حالة المراجعة البشريّة المخزَّنة
        - ``review_recommended``   (bool)      True إذا < العتبة التقديريّة
        - ``source``               ثابت ``"field_state.canonical"`` (تدقيق)

    صدق: غياب ``confidence_score`` أو مدخل غير صالح ⇒ ``None``.
    """
    if not isinstance(row, dict):
        return None
    raw = row.get("confidence_score")
    if raw is None:
        return None
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        return None

    block = {
        "boundary_confidence": round(conf, 3),
        "review_recommended": conf < CONFIDENCE_REVIEW_THRESHOLD,
        "source": "field_state.canonical",
    }
    for out_key, in_key in _PASSTHROUGH:
        block[out_key] = row.get(in_key)
    return block
