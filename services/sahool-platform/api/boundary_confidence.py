"""services/sahool-platform/api/boundary_confidence.py — محرّك ثقة الحدود (#15)

الغرض:
   كلّ حدّ حقل (polygon) يجب أن يحمل ``confidence_score`` يَسري إلى كلّ التحاليل
   التابعة (المساحة، الري، NDVI، الإنتاجيّة) حتّى لا تنتقل أخطاء الترسيم بصمت.
   هذا الملفّ يحسب ذلك التهديف من خصائص الـpolygon البنيويّة فقط.

صدق صريح — ما هذا وما ليس هو:
   هذه ثقة *حتميّة* مبنيّة على قابليّة المعقوليّة الهندسيّة (geometric
   plausibility heuristic) — وليست ثقة متعلّمة (NOT an ML/learned confidence).
   لا يوجد نموذج، لا تدريب، لا معايرة ميدانيّة مُثبتة. العتبات والعقوبات أدناه
   *تقديريّة* (heuristic) واختِيرت بالحكم الهندسيّ لا بقياس حقليّ، وتحتاج
   *معايرة ميدانيّة* (field calibration) قبل الاعتماد عليها كميّاً. لم تُختلق أيّ
   أرقام معايرة.

ماذا يفعل عمليّاً:
   يأخذ خصائص قابلة للحساب عن الحدّ (عدد الرؤوس، المساحة، الصلاحيّة، عدد
   الحلقات، التقاطعات الذاتيّة، اتّفاق زمنيّ اختياريّ) ويُطبّق عقوبات موثّقة
   ليُخرج درجة 0..1 مع قائمة العوامل المُطبَّقة (بالعربيّة) وتوصية مراجعة بشريّة
   (HIL) عند انخفاض الثقة. النيّة: ألّا تتسلّل حدود ضعيفة الجودة إلى المخرجات.

نقاء:
   دالّة نقيّة بلا قاعدة بيانات/شبكة/ML، ولا تتطلّب shapely — تعمل على dict
   أرقام/قيم بسيطة. لا ترمي أبداً: المفاتيح الناقصة أو القيم الفاسدة تُعالَج
   بقيم افتراضيّة آمنة مع عامل يُنوّه بنقص البيانات.
"""

from __future__ import annotations

from typing import Any

# ─── العتبات والحدود التقديريّة (heuristic — تحتاج معايرة ميدانيّة) ──────

# تحت هذه الدرجة نوصي بمراجعة بشريّة (Human-In-The-Loop).
CONFIDENCE_REVIEW_THRESHOLD = 0.6

# سقف مساحة معقول لحقل واحد (هكتار). فوقه: غالباً خطأ ترسيم أو وحدات.
MAX_PLAUSIBLE_AREA_HA = 10000.0

# الحدّ الأدنى للرؤوس كي يكون مضلّعاً (مثلّث مغلق على الأقلّ).
MIN_POLYGON_VERTICES = 4

# سقف رؤوس فوقه نشكّ في ضوضاء/over-digitization.
MAX_PLAUSIBLE_VERTICES = 2000


def _coerce_float(value: Any) -> float | None:
    """تحويل آمن إلى float — يُرجع None عند الفشل بدل الرمي."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    """تحويل آمن إلى int — يُرجع None عند الفشل بدل الرمي."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def score_boundary(props: dict) -> dict:
    """يحسب درجة ثقة حتميّة (0..1) لحدّ حقل من خصائصه البنيويّة.

    المُدخل ``props`` — dict يحوي (كلّها اختياريّة، الناقص يُعامَل بأمان):
        - ``vertex_count``        (int)         عدد رؤوس الحلقة الخارجيّة
        - ``area_ha``             (float)       المساحة بالهكتار
        - ``is_valid``            (bool)        هل الهندسة صالحة (OGC valid)
        - ``ring_count``          (int)         عدد الحلقات (1 = بلا ثقوب)
        - ``self_intersections``  (int)         عدد التقاطعات الذاتيّة
        - ``temporal_agreement``  (float|None)  اتّفاق متعدّد التواريخ 0..1

    المُخرَج — dict:
        - ``confidence``          (float 0..1, مُقرَّبة)
        - ``factors``             (list[dict])  العوامل المُطبَّقة، كلّ عامل
                                  ``{"name_ar", "delta"}`` (delta سالبة عقوبة،
                                  موجبة تعزيز)
        - ``review_recommended``  (bool)        True إذا < العتبة التقديريّة

    حتميّة ونقيّة: لا تَرمي أبداً.
    """
    factors: list[dict[str, Any]] = []

    # حماية المُدخل: أيّ شيء ليس dict يُعامَل كبيانات مفقودة.
    if not isinstance(props, dict):
        props = {}
        factors.append(
            {
                "name_ar": "مُدخل غير صالح — عومِل كبيانات مفقودة",
                "delta": -0.30,
            }
        )

    # نبدأ من ثقة كاملة ونخصم عقوبات موثّقة.
    confidence = 1.0

    # ─── ١. صلاحيّة الهندسة (عقوبة قويّة) ──────────────────────────
    is_valid = props.get("is_valid", None)
    if is_valid is None:
        factors.append({"name_ar": "صلاحيّة الهندسة غير معروفة (بيانات مفقودة)", "delta": -0.15})
        confidence -= 0.15
    elif not is_valid:
        factors.append({"name_ar": "هندسة غير صالحة (invalid geometry)", "delta": -0.60})
        confidence -= 0.60

    # ─── ٢. التقاطعات الذاتيّة (عقوبة) ─────────────────────────────
    self_int = _coerce_int(props.get("self_intersections"))
    if self_int is None:
        factors.append(
            {"name_ar": "عدد التقاطعات الذاتيّة غير معروف (بيانات مفقودة)", "delta": -0.05}
        )
        confidence -= 0.05
    elif self_int > 0:
        factors.append({"name_ar": f"تقاطعات ذاتيّة في الحدّ ({self_int})", "delta": -0.40})
        confidence -= 0.40

    # ─── ٣. معقوليّة المساحة (عقوبة) ───────────────────────────────
    area_ha = _coerce_float(props.get("area_ha"))
    if area_ha is None:
        factors.append({"name_ar": "المساحة غير معروفة (بيانات مفقودة)", "delta": -0.15})
        confidence -= 0.15
    elif area_ha <= 0:
        factors.append({"name_ar": "مساحة غير فيزيائيّة (≤ 0 هكتار)", "delta": -0.50})
        confidence -= 0.50
    elif area_ha > MAX_PLAUSIBLE_AREA_HA:
        factors.append(
            {
                "name_ar": f"مساحة غير معقولة (> {MAX_PLAUSIBLE_AREA_HA:.0f} هكتار)",
                "delta": -0.35,
            }
        )
        confidence -= 0.35

    # ─── ٤. أطراف عدد الرؤوس (عقوبة) ───────────────────────────────
    vertex_count = _coerce_int(props.get("vertex_count"))
    if vertex_count is None:
        factors.append({"name_ar": "عدد الرؤوس غير معروف (بيانات مفقودة)", "delta": -0.15})
        confidence -= 0.15
    elif vertex_count < MIN_POLYGON_VERTICES:
        factors.append(
            {
                "name_ar": f"رؤوس قليلة جدّاً (< {MIN_POLYGON_VERTICES}) — ليس مضلّعاً",
                "delta": -0.50,
            }
        )
        confidence -= 0.50
    elif vertex_count > MAX_PLAUSIBLE_VERTICES:
        factors.append(
            {
                "name_ar": f"رؤوس كثيرة مرضيّاً (> {MAX_PLAUSIBLE_VERTICES}) — ضوضاء محتملة",
                "delta": -0.15,
            }
        )
        confidence -= 0.15

    # ─── ٥. عدد الحلقات / الثقوب (عقوبة خفيفة) ─────────────────────
    ring_count = _coerce_int(props.get("ring_count"))
    if ring_count is not None and ring_count > 1:
        factors.append({"name_ar": f"حلقات/ثقوب متعدّدة ({ring_count})", "delta": -0.10})
        confidence -= 0.10

    # ─── ٦. الاتّفاق الزمنيّ متعدّد التواريخ (تعزيز/إنقاص) ──────────
    # موجود اختياريّاً: يُمزَج ليرفع الثقة عند اتّفاق متعدّد التواريخ.
    # غائب (None): يُتجاهَل، لكن نُنوّه أنّ التهديف أحاديّ التاريخ أقلّ موثوقيّة.
    temporal = _coerce_float(props.get("temporal_agreement"))
    if temporal is None:
        factors.append(
            {
                "name_ar": "بلا اتّفاق زمنيّ — تهديف أحاديّ التاريخ أقلّ موثوقيّة",
                "delta": 0.0,
            }
        )
    else:
        temporal = max(0.0, min(1.0, temporal))
        # خلط: ٧٠٪ من التهديف الهندسيّ + ٣٠٪ من الاتّفاق الزمنيّ.
        before = max(0.0, min(1.0, confidence))
        blended = 0.70 * before + 0.30 * temporal
        delta = blended - before
        confidence = blended
        factors.append(
            {
                "name_ar": f"خلط الاتّفاق الزمنيّ (agreement={temporal:.2f})",
                "delta": round(delta, 3),
            }
        )

    # القصّ إلى [0, 1] والتقريب.
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    return {
        "confidence": confidence,
        "factors": factors,
        "review_recommended": confidence < CONFIDENCE_REVIEW_THRESHOLD,
    }
