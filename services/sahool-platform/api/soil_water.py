"""api/soil_water.py — خصائص ماء التربة حسب النسيج (FAO-56 Table 19)

الطبقة الثالثة في خطّ «مركز المحاصيل» (#374 — Soil-Aware Irrigation Need):
`root_zone_balance` و`crop_twin` يتطلّبان `taw_mm` (الماء الكلّيّ المتاح) كمُدخَل —
هذا المصدر الموحّد يشتقّه من **نسيج التربة × عمق الجذور** بدل تمريره أرقاماً سحريّة.

الفصل المفاهيميّ (صدق علميّ):
  • TAW (سعة الاحتفاظ) **خاصّيّة تربة** ⇐ النسيج (FAO-56 Table 19).
  • p (نسبة الاستنفاد المتاح بيُسر، raw_fraction) **خاصّيّة محصول** (FAO-56 Table 22)
    لا نسيج — لذا تُمرَّر من المحصول (افتراض 0.5)، لا نختلقها من النسيج.

نقيّ حتميّ (لا I/O). يدعم مفاتيح النسيج الإنجليزيّة (شرطة سفليّة أو مسافة) والعربيّة.
TAW لكلّ متر يُقرأ من ``core.engines.fao56`` (المصدر الوحيد) — ⚠ قيم FAO-56 Table 19
النوعيّة تحتاج معايرة يمنيّة (تربة كلسيّة، بنية مختلفة). موسومة calibrated=False.
"""

from __future__ import annotations

from core.engines.fao56 import taw_mm_per_m_for_texture

# PARALLEL-TAW-AND-KC-TABLES-DISAGREE-01 — لا جدول TAW هنا. كان ``_TAW_MM_PER_M`` نسخةً
# موازية تخالف المحرّك (loam 175 مقابل 150، silt_loam 200 مقابل 170)، فكان حقلٌ واحد
# يأخذ خزّانين بحسب المستهلك. بقرار المالك (2026-10-15): ``core.engines.fao56`` (θFC/θWP
# حسب القوام، TAW = 1000·(θFC − θWP)) هو المصدر الوحيد، ومرادفات القوام انتقلت إليه.

# عمق جذور افتراضيّ حين يغيب (م) — متوسّط آمن، موسوم. لا اختلاق عمق دقيق.
_DEFAULT_ROOT_DEPTH_M = 0.6
# p (raw_fraction) عامّ من FAO-56 حين لا يمرّره المحصول.
_DEFAULT_RAW_FRACTION = 0.5


def _taw_per_m(texture: str | None) -> tuple[float, bool]:
    """TAW (مم/م) من النسيج ⇒ (القيمة، هل النسيج معروف) — من جدول FAO-56 القانونيّ.

    النسيج المجهول ⇒ قيمة FAO-56 للطميّ (loam) موسومةً ``False``.
    """
    return taw_mm_per_m_for_texture(texture)


def soil_water_params(
    texture: str | None,
    root_depth_m: float | None = None,
    raw_fraction: float = _DEFAULT_RAW_FRACTION,
) -> dict:
    """يشتقّ `taw_mm` و`raw_mm` من النسيج وعمق الجذور — مُدخَل لـ root_zone_balance.

    TAW = TAW(نسيج) × عمق الجذور؛ RAW = p × TAW (p خاصّيّة محصول تُمرَّر، لا نسيج).
    صدق: النسيج المجهول يستعمل قيمة احتياطيّة موسومة (texture_known=False)؛ عمق غائب
    ⇒ افتراض موسوم؛ القيم غير معايَرة يمنيّاً (calibrated=False).
    """
    warnings_ar: list[str] = [
        "TAW من FAO-56 Table 19 (θFC − θWP) غير معايَرة يمنيّاً (تربة كلسيّة) — قدِّر بحذر",
    ]
    taw_per_m, known = _taw_per_m(texture)
    if not known:
        warnings_ar.append("نسيج غير معروف — TAW احتياطيّ (طميّ FAO-56)؛ مرّر نسيجاً للدقّة")

    depth = root_depth_m
    if depth is None or depth <= 0:
        depth = _DEFAULT_ROOT_DEPTH_M
        warnings_ar.append(f"عمق الجذور غائب — افتراض {depth} م (موسوم)")

    p = max(0.0, min(1.0, raw_fraction))
    taw_mm = taw_per_m * depth
    raw_mm = p * taw_mm
    return {
        "texture": (texture or "").strip().lower() or None,
        "texture_known": known,
        "taw_mm_per_m": round(taw_per_m, 1),
        "root_depth_m": round(depth, 2),
        "taw_mm": round(taw_mm, 2),
        "raw_fraction": round(p, 3),
        "raw_mm": round(raw_mm, 2),
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }


def available_water_fraction(depletion_mm: float, taw_mm: float) -> float:
    """جزء الماء المتاح المتبقّي في منطقة الجذور = 1 − Dr/TAW، مقصوص [0,1].

    1.0 = السعة الحقليّة (تربة ممتلئة)، 0.0 = نقطة الذبول (نفد المتاح). هذا هو
    **الأساس الفيزيائيّ للقرار الواعي بالتربة**: نفس ETc (⇒ نفس Dr) يستنزف الرمل
    (TAW منخفض) إلى كسر أدنى أسرع من الطين (TAW مرتفع) — فيُستحقّ الريّ في الرمل أوّلاً.
    """
    if taw_mm <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - depletion_mm / taw_mm))


def irrigation_due_by_soil(depletion_mm: float, taw_mm: float, raw_fraction: float) -> bool:
    """قرار توقيت الريّ الواعي بالتربة — يعتمد كسر الماء المتاح لا ETc وحده.

    مستحقّ حين ينزل الماء المتاح إلى عتبة الاستنفاد: AWF ≤ 1 − p (مكافئ Dr ≥ RAW).
    نفس Dr يستحقّ الريّ في الرمل (AWF أدنى) قبل الطين — فيزياء التربة تحكم التوقيت.
    """
    return available_water_fraction(depletion_mm, taw_mm) <= (1.0 - raw_fraction)
