"""
sahool_core.terroir_index
==========================
مؤشّر التيروير — قرينة متعدّدة العوامل على *إمكان* جودة المنطقة، لا حكم.

خلفية (تصحيح قرار سابق): رُفض التيروير سابقاً كـ"عامل لا يُقاس". لكن
المراجعة النقدية محقّة: هذا تناقض مع قبول التحقّق السلبي (ادّعاء بسقف
منخفض). الاتساق يقتضي معاملة التيروير كقرينة بسقف منخفض — تجمع ما
يُقاس، وتعلن صراحةً ما لا يُقاس (لا تخفيه ولا تدّعيه).

ما يُقاس (يدخل المؤشّر، سقف LOW):
  • الارتفاع (elevation) — متاح من السياق
  • فرق الحرارة الليلية/النهارية — من الطقس
  • نمط الهطول — من الطقس
  • خصائص التربة المخبرية (pH, CEC, OM) — إن توفّرت

ما لا يُقاس (يُعلَن كفجوة معروفة، لا يُحسَب):
  • الصنف المحلي المُعتّق (genomics)
  • تقليد المعالجة (مثلاً التجفيف الطبيعي لبنّ المخا)
  • ميكروبيوم التربة الفريد

المبدأ: المؤشّر يقول "هذه المنطقة لها *إمكان* جودة عالٍ بناءً على عوامل
مقيسة" — لا "الجودة عالية" (التي تتطلّب عوامل غير مقيسة). سقف LOW
صريح، والفجوات معلنة. هذا تطبيق متّسق لـ"لا تحسب ما لا تقيس":
ما يُقاس يُحسب بسقف منخفض، وما لا يُقاس يُعلَن لا يُلفَّق.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TerroirResult:
    potential_score: float | None  # 0..1، إمكان لا حكم
    confidence: str  # low دائماً (قرينة)
    measured_factors: dict  # العوامل المقيسة المساهمة
    unmeasured_gaps_ar: list[str]  # ما لا يُقاس (معلن صراحةً)
    note_ar: str = ""
    warnings_ar: list[str] = field(default_factory=list)


# نطاقات مرجعية لإمكان الجودة (استرشادية، ليست أحكاماً)
def _elevation_factor(elevation_m: float | None) -> float | None:
    """الارتفاع العالي يرتبط بفرق حراري أكبر (نكهة أعمق لبعض المحاصيل)."""
    if elevation_m is None:
        return None
    if elevation_m >= 1800:
        return 0.9
    if elevation_m >= 1200:
        return 0.7
    if elevation_m >= 600:
        return 0.5
    return 0.3


def _diurnal_factor(day_night_temp_diff_c: float | None) -> float | None:
    """فرق الحرارة اليومي الكبير يحسّن تراكم السكريات/النكهة."""
    if day_night_temp_diff_c is None:
        return None
    if day_night_temp_diff_c >= 15:
        return 0.9
    if day_night_temp_diff_c >= 10:
        return 0.7
    return 0.4


def terroir_potential(
    *,
    crop_id: str,
    elevation_m: float | None = None,
    day_night_temp_diff_c: float | None = None,
    soil_om_pct: float | None = None,
    known_heritage_variety: bool = False,
    known_traditional_processing: bool = False,
) -> TerroirResult:
    """يقدّر *إمكان* جودة المنطقة من عوامل مقيسة (قرينة سقف LOW).

    لا يُصدر حكم جودة — يقول "إمكان عالٍ/متوسط بناءً على المقيس"،
    ويعلن صراحةً العوامل غير المقيسة التي تمنع اليقين."""
    measured: dict[str, float] = {}
    ev = _elevation_factor(elevation_m)
    if ev is not None:
        measured["elevation"] = ev
    di = _diurnal_factor(day_night_temp_diff_c)
    if di is not None:
        measured["diurnal_range"] = di
    if soil_om_pct is not None:
        measured["soil_om"] = min(1.0, soil_om_pct / 3.0)  # 3% OM ~ مرجع جيد

    # الفجوات غير المقيسة — تُعلَن دائماً (لا تُلفَّق)
    gaps = []
    if not known_heritage_variety:
        gaps.append("الصنف المحلي المُعتّق غير مُوثّق جينياً (عامل جودة كبير غير مقيس)")
    if not known_traditional_processing:
        gaps.append("تقليد المعالجة (مثل التجفيف الطبيعي) غير مُوثّق")
    gaps.append("ميكروبيوم التربة الفريد غير مُقاس (يتطلّب تحليلاً متخصّصاً)")

    if not measured:
        return TerroirResult(
            potential_score=None,
            confidence="none",
            measured_factors={},
            unmeasured_gaps_ar=gaps,
            note_ar="لا عوامل مقيسة متاحة — لا يمكن تقدير إمكان التيروير",
        )

    score = round(sum(measured.values()) / len(measured), 3)
    warnings = [
        "هذا *إمكان* لا حكم جودة — الجودة الفعلية تتطلّب عوامل غير مقيسة (أدناه)",
        "سقف منخفض دائماً: التيروير قرينة لا دليل (مثل أي مدخل غير مخبري حاكم)",
    ]
    return TerroirResult(
        potential_score=score,
        confidence="low",
        measured_factors={k: round(v, 2) for k, v in measured.items()},
        unmeasured_gaps_ar=gaps,
        warnings_ar=warnings,
        note_ar=(
            f"إمكان جودة {crop_id} من العوامل المقيسة: {score} "
            f"(قرينة سقف منخفض؛ {len(gaps)} عوامل جودة غير مقيسة معلنة)"
        ),
    )
