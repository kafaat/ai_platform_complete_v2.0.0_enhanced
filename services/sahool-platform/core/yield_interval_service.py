"""core/yield_interval_service.py — مُغلِّف نزيه لنطاق الإنتاج (Honest Yield Interval).

غلاف صِرف (لا قاعدة بيانات، لا حالة) يُكيّف مُدخلات العميل/الحقل لِـ
``core.engines.yield_interval.conformal_interval`` ويُشكّل استجابة API نزيهة:
الإنتاج يُبلَّغ كـ«نطاق» مثل ``[4.2, 7.1] t/ha بتغطية 90%``، أو «قيد المعايرة»
حين لا تتوفّر بقايا معايرة كافية — لا نقطة وهميّة أبداً.

كلّ الإحصاء (كمّ البقايا المطلق، النطاق conformal) يبقى مُفوَّضاً للمحرّك؛ هذا
الملفّ يُكيّف المُدخلات/المُخرجات ويفرض النزاهة والتشكيل فقط.
"""

from __future__ import annotations

from core.engines.yield_interval import YieldInterval, conformal_interval

# الحدّ الأدنى لعدد البقايا المحجوبة الذي يقبله المحرّك لِبناء نطاق موثوق.
_MIN_CALIBRATION = 10

_UNIT = "t/ha"


def _pending(
    point_estimate: float | None,
    coverage: float,
    n_residuals: int,
    note_ar: str,
) -> dict:
    """تشكيل استجابة «قيد المعايرة» — بلا نطاق وهميّ."""
    return {
        "point_estimate": point_estimate,
        "interval": None,
        "coverage": None,
        "calibrated": False,
        "n_residuals": n_residuals,
        "unit": _UNIT,
        "status_ar": "قيد المعايرة",
        "note_ar": note_ar,
        "coverage_requested": coverage,
    }


def field_yield_interval(
    point_estimate: float | None,
    residuals: list[float],
    coverage: float = 0.90,
) -> dict:
    """تُرجِع نطاق إنتاج conformal نزيهاً لحقلٍ من تقدير نقطيّ + بقايا معايرة.

    المُدخلات يُوفّرها العميل (سِجِلّ معايرته المحجوب)، لأنّ المنصّة تحتفظ بسجلّ
    محدود على الخادم. حين تكون البقايا قليلة جدّاً أو ``point_estimate`` غائباً،
    تُرجَع حالة «قيد المعايرة» بلا نطاق — نزاهة، لا اختلاق نطاق بلا بيانات.

    الإحصاء مُفوَّض بالكامل لِ``conformal_interval``؛ هنا تكييف وتشكيل فقط.
    """
    residuals = list(residuals or [])
    n = len(residuals)

    # نزاهة: بلا تقدير نقطيّ لا يوجد مركز للنطاق ⇒ قيد المعايرة.
    if point_estimate is None:
        return _pending(
            None,
            coverage,
            n,
            "قيد المعايرة — لا تقدير نقطيّ مرجعيّ لِبناء النطاق حوله",
        )

    # بقايا غير كافية ⇒ نُفوّض للمحرّك الذي يرفض الاختلاق (status=pending).
    result: YieldInterval = conformal_interval(
        point_estimate=float(point_estimate),
        calibration_residuals=residuals,
        coverage=coverage,
    )

    if result.status != "calibrated" or result.lower is None or result.upper is None:
        return _pending(
            None,
            coverage,
            result.n_calibration,
            result.note_ar
            or (f"قيد المعايرة — تحتاج ≥{_MIN_CALIBRATION} نقطة بقايا محجوبة لِنطاق موثوق"),
        )

    return {
        "point_estimate": result.point_estimate,
        "interval": [result.lower, result.upper],
        "coverage": result.coverage,
        "calibrated": True,
        "n_residuals": result.n_calibration,
        "unit": _UNIT,
        "status_ar": "معايَر",
        "note_ar": result.note_ar,
        "coverage_requested": coverage,
    }
