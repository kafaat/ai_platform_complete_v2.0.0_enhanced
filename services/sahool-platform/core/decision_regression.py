"""core/decision_regression.py — بوّابة تحقّق القرار على حالات مرجعيّة.

الفكرة (مُستلهَمة من مبدأ "validation gate على held-out set" في SkillOpt،
لا من أداته): SkillOpt لا يقبل أيّ تغيير إلّا إذا أثبت تحسّناً (أو عدم تدهور)
على مجموعة محجوزة معروفة النتيجة. نطبّق المبدأ نفسه على **منطق القرار**:

  أيّ تغيير في عتبة/قاعدة (مثلاً EC≥4 → EC≥3.5) يجب أن يُشغَّل أوّلاً على
  حالات مرجعيّة حقيقيّة معروفة التصنيف (الجوف/السنيدار) ويُؤكَّد أنّه **لا
  يُدهور** التصنيف المتوقّع — قبل اعتماده في الإنتاج.

⚠ ليست أداة LLM ولا تدريب. منطق سهول حتمي فيزيائي — فالـ"golden set" هنا
حالات تربة/ملوحة حقيقيّة بنتائج موثّقة، لا prompts. التقييم حتمي (لا نماذج).

المصادر: نطاق ECe الجوف [3.0–7.0] (districts/al_jawf/soil.yaml + دراسة القمح)؛
بيانات السنيدار الأرضيّة (pH~8.2، كلس 31% — دراسة حكوميّة، شرق الحزم).
الحالات **موثّقة لا مخترعة**؛ النتائج المتوقّعة من العتبات العلميّة الحاليّة.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.thresholds import HIGH_PH_THRESHOLD, SALINITY_MODERATE_ECE


# ═══════════════════════════════════════════════════════════════════
# حالات مرجعيّة (golden set) — قيم حقيقيّة/واقعيّة بنتائج تصنيف معروفة.
# كلّ حالة: مدخلات فيزيائيّة + التصنيف المتوقّع (من العلم الموثّق).
# ═══════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    soil_ec_dsm: float | None
    soil_ph: float | None
    expect_salinity_alert: bool  # هل يُتوقّع تنبيه ملوحة؟
    expect_alkalinity_alert: bool  # هل يُتوقّع تنبيه قلويّة؟
    provenance_ar: str  # مصدر الحالة (لا اختراع)


# الحالات المرجعيّة — مرتكزة على نطاق الجوف الموثّق وبيانات السنيدار.
# العتبات الحاليّة: ملوحة EC≥4، قلويّة pH≥7.8.
GOLDEN_CASES: list[DecisionCase] = [
    DecisionCase(
        "jawf_typical_mid",
        5.0,
        8.2,
        True,
        True,
        "وسط نطاق الجوف ECe[3-7] + pH السنيدار ~8.2 — ملوحة وقلويّة متوقّعتان",
    ),
    DecisionCase(
        "jawf_high_salinity", 6.8, 8.0, True, True, "أعلى نطاق الجوف — ملوحة عالية مؤكّدة + قلويّة"
    ),
    DecisionCase(
        "jawf_low_salinity",
        3.2,
        7.5,
        False,
        False,
        "أدنى نطاق الجوف (EC<4، pH<7.8) — لا تنبيه (حدّيّة سفلى)",
    ),
    DecisionCase(
        "sunaydar_ground_truth",
        4.5,
        8.2,
        True,
        True,
        "بيانات السنيدار الأرضيّة (شرق الحزم، pH~8.2، كلس 31%) — النمط المؤكّد",
    ),
    DecisionCase(
        "boundary_ec_exact",
        4.0,
        7.7,
        True,
        False,
        "حدّ الملوحة بالضبط (EC=4 ⇒ تنبيه) + pH تحت عتبة القلويّة (7.7<7.8)",
    ),
    DecisionCase(
        "boundary_ph_exact",
        3.9,
        7.8,
        False,
        True,
        "EC تحت العتبة (3.9<4) + حدّ القلويّة بالضبط (pH=7.8 ⇒ تنبيه)",
    ),
    DecisionCase(
        "clean_soil", 2.0, 7.0, False, False, "تربة نظيفة (EC<4، pH<7.8) — لا تنبيهات (ضبط سلبي)"
    ),
    DecisionCase(
        "missing_inputs",
        None,
        None,
        False,
        False,
        "بلا مدخلات — لا تنبيه (لا اختراع، صدق المدخل المتعذّر)",
    ),
]


def _classify(
    ec: float | None,
    ph: float | None,
    ec_threshold: float = SALINITY_MODERATE_ECE,
    ph_threshold: float = HIGH_PH_THRESHOLD,
) -> dict:
    """يطبّق منطق تصنيف القرار الحالي (نفس عتبات decision_engine).

    معامِلات العتبة قابلة للتمرير لاختبار 'ماذا لو غيّرناها' (held-out eval).
    """
    return {
        "salinity_alert": ec is not None and ec >= ec_threshold,
        "alkalinity_alert": ph is not None and ph >= ph_threshold,
    }


def run_regression(
    ec_threshold: float = SALINITY_MODERATE_ECE, ph_threshold: float = HIGH_PH_THRESHOLD
) -> dict:
    """يشغّل منطق القرار على الحالات المرجعيّة ويتحقّق من عدم التدهور.

    الاستخدام: قبل تغيير عتبة في الإنتاج، شغّل بالعتبة الجديدة وتأكّد أنّ
    كلّ الحالات لا تزال تُصنَّف صحيحاً (أو راجع أيّها تغيّر ولماذا).

    Returns: تقرير بالنجاحات/الإخفاقات + تفصيل كلّ حالة تغيّرت.
    """
    passed = 0
    failures = []
    for c in GOLDEN_CASES:
        got = _classify(c.soil_ec_dsm, c.soil_ph, ec_threshold, ph_threshold)
        sal_ok = got["salinity_alert"] == c.expect_salinity_alert
        alk_ok = got["alkalinity_alert"] == c.expect_alkalinity_alert
        if sal_ok and alk_ok:
            passed += 1
        else:
            failures.append(
                {
                    "case_id": c.case_id,
                    "provenance_ar": c.provenance_ar,
                    "expected": {
                        "salinity": c.expect_salinity_alert,
                        "alkalinity": c.expect_alkalinity_alert,
                    },
                    "got": got,
                }
            )
    return {
        "total": len(GOLDEN_CASES),
        "passed": passed,
        "failed": len(failures),
        "all_pass": len(failures) == 0,
        "thresholds": {"ec": ec_threshold, "ph": ph_threshold},
        "failures": failures,
        "purpose_ar": (
            "بوّابة تحقّق: أيّ تغيير عتبة يجب أن يمرّ على الحالات المرجعيّة "
            "دون تدهور قبل الاعتماد. الحالات موثّقة (الجوف/السنيدار) لا مخترعة."
        ),
    }


def evaluate_threshold_change(
    new_ec_threshold: float | None = None, new_ph_threshold: float | None = None
) -> dict:
    """يقارن العتبة الحاليّة بالمقترحة على الحالات المرجعيّة (بوّابة التغيير).

    يجسّد مبدأ SkillOpt: لا يدخل التغيير إلّا إذا لم يُدهور النتيجة المرجعيّة.
    """
    baseline = run_regression()  # العتبات الحاليّة
    new_ec = new_ec_threshold if new_ec_threshold is not None else 4.0
    new_ph = new_ph_threshold if new_ph_threshold is not None else 7.8
    candidate = run_regression(new_ec, new_ph)

    regressed = candidate["passed"] < baseline["passed"]
    return {
        "baseline_passed": baseline["passed"],
        "candidate_passed": candidate["passed"],
        "candidate_thresholds": {"ec": new_ec, "ph": new_ph},
        "regressed": regressed,
        "verdict_ar": (
            "⛔ مرفوض — التغيير يُدهور التصنيف المرجعي (لا يدخل الإنتاج)"
            if regressed
            else "✓ مقبول — لا تدهور على الحالات المرجعيّة (آمن للاعتماد)"
        ),
        "changed_cases": candidate["failures"],
    }
