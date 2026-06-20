"""api/evidence_registry.py — سجلّ دليل المعايرة (Calibration Evidence Registry)

#384: يجمع نتائج القياس الميدانيّ (مخرجات outcome_measurement) لكلّ منطقة في **دليل
تراكميّ**: كم عيّنة؟ ما نسبة نجاح القرار؟ متى آخر تقييم؟ ما مستوى الدليل؟

هذا يحوّل النتائج المتفرّقة إلى **معرفة تراكميّة لكلّ منطقة** — أساس Adaptive
Calibration لاحقاً. **لا تعديل آليّ للمعايرة هنا** (ذلك #387)؛ فقط تجميع الدليل.

نقيّ حتميّ (لا I/O، لا ساعة): الطوابع الزمنيّة تُمرَّر مع كلّ نتيجة. صدق: العتبات
تقديريّة موسومة؛ نتيجة بلا مقياس مُقيَّم لا تُحتسب عيّنة (لا تضخيم دليل).
"""

from __future__ import annotations

# أدنى عدد عيّنات ميدانيّة لاعتبار المنطقة «مُتحقَّقة ميدانيّاً». ⚠ تقديريّ غير معايَر.
_FIELD_VERIFIED_MIN_SAMPLES = 30


def aggregate_evidence(
    region: str,
    outcomes: list[dict],
    expert_calibrated: bool = False,
) -> dict:
    """يجمّع نتائج القياس لمنطقة في دليل تراكميّ — نقيّ حتميّ.

    outcomes: قائمة مخرجات measure_outcome (كلّ منها {n_evaluated, n_success,
    success_flags, evaluated_at?}). expert_calibrated: هل للمنطقة قيم خبير مُسبقاً.
    صدق: العيّنة = نتيجة فيها ≥1 مقياس مُقيَّم (الفارغة لا تُحتسب). مستوى الدليل من
    عدد العيّنات (عتبة موسومة): 0⇒none/expert_opinion، <العتبة⇒field_preliminary،
    ≥العتبة⇒field_verified.
    """
    samples = [o for o in outcomes if o.get("n_evaluated", 0) > 0]
    sample_count = len(samples)
    total_eval = sum(o.get("n_evaluated", 0) for o in samples)
    total_success = sum(o.get("n_success", 0) for o in samples)
    success_rate = round(total_success / total_eval, 3) if total_eval else None

    # إحصاء أعلام النجاح عبر العيّنات (أيّ جوانب القرار نجحت أكثر).
    flag_counts: dict[str, int] = {}
    for o in samples:
        for flag in o.get("success_flags", []):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    stamps = [o["evaluated_at"] for o in samples if o.get("evaluated_at")]
    last_evaluated_at = max(stamps) if stamps else None

    if sample_count == 0:
        evidence_level = "expert_opinion" if expert_calibrated else "none"
    elif sample_count >= _FIELD_VERIFIED_MIN_SAMPLES:
        evidence_level = "field_verified"
    else:
        evidence_level = "field_preliminary"

    samples_to_verified = max(0, _FIELD_VERIFIED_MIN_SAMPLES - sample_count)

    warnings_ar = ["عتبة التحقّق الميدانيّ تقديريّة — تحتاج معايرة"]
    if 0 < sample_count < _FIELD_VERIFIED_MIN_SAMPLES:
        warnings_ar.append(
            f"دليل أوّليّ ({sample_count}/{_FIELD_VERIFIED_MIN_SAMPLES}) — يلزم {samples_to_verified} عيّنة للتحقّق"
        )

    return {
        "region": region,
        "sample_count": sample_count,
        "evidence_level": evidence_level,
        "success_rate": success_rate,
        "success_flag_counts": flag_counts,
        "last_evaluated_at": last_evaluated_at,
        "field_verified_min_samples": _FIELD_VERIFIED_MIN_SAMPLES,
        "samples_to_verified": samples_to_verified,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }


def evidence_from_persisted_outcomes(
    region: str,
    rows: list[dict],
    expert_calibrated: bool = False,
) -> dict:
    """يبني الدليل التراكميّ من صفوف outcome_record المُدامة — يُغلق P0-2 (إدامة الدليل).

    rows: صفوف outcome_record المُدامة، كلّ صفّ {metrics, created_at}؛ metrics هي مخرجات
    measure_outcome المخزّنة (فيها n_evaluated/n_success/success_flags). يستخرج منها مدخلات
    aggregate_evidence (evaluated_at=created_at) ثمّ يفوّض إليه — **مصدر واحد** لمنطق العتبة
    والمستوى (لا تكرار). نقيّ حتميّ (لا I/O): الاستعلام يجري في الموجِّه ويُمرَّر ناتجه هنا.

    صدق: الدليل الآن مدعوم بنتائج **مُدامة** (لا حمولة طلب عابرة) — يتراكم نحو عتبة التحقّق
    عبر الزمن. الناقص (metrics فارغة) لا يُحتسب عيّنة (aggregate_evidence يُسقِط n_evaluated=0).
    """
    outcomes: list[dict] = []
    for r in rows:
        m = r.get("metrics") or {}
        outcomes.append(
            {
                "n_evaluated": m.get("n_evaluated", 0),
                "n_success": m.get("n_success", 0),
                "success_flags": m.get("success_flags", []),
                "evaluated_at": r.get("created_at"),
            }
        )
    out = aggregate_evidence(region, outcomes, expert_calibrated=expert_calibrated)
    # صدق: نوضّح مصدر الدليل (نتائج مُدامة) وعدد الصفوف المقروءة (قد يفوق العيّنات المُحتسَبة).
    out["source"] = "persisted_outcomes"
    out["persisted_rows"] = len(rows)
    return out
