"""api/evidence_registry.py — سجلّ دليل المعايرة (Calibration Evidence Registry)

#384: يجمع نتائج القياس الميدانيّ (مخرجات outcome_measurement) لكلّ منطقة في **دليل
تراكميّ**: كم عيّنة؟ ما نسبة نجاح القرار؟ متى آخر تقييم؟ ما مستوى الدليل؟

هذا يحوّل النتائج المتفرّقة إلى **معرفة تراكميّة لكلّ منطقة** — أساس Adaptive
Calibration لاحقاً. **لا تعديل آليّ للمعايرة هنا** (ذلك #387)؛ فقط تجميع الدليل.

نقيّ حتميّ (لا I/O، لا ساعة): الطوابع الزمنيّة تُمرَّر مع كلّ نتيجة. صدق: العتبات
تقديريّة موسومة؛ نتيجة بلا مقياس مُقيَّم لا تُحتسب عيّنة (لا تضخيم دليل).
"""

from __future__ import annotations

# عتبة جمع تقديريّة؛ الاسم التاريخيّ لا يمنح اعتماداً أو معايرة بعدّ الصفوف.
_FIELD_VERIFIED_MIN_SAMPLES = 30


_INDEPENDENCE_KEYS = ("field_id", "season_id", "farm_id", "tenant_id")


def _independence(samples: list[dict]) -> dict:
    """أعداد الوحدات المستقلّة بين العيّنات (حقول/مواسم/مزارع/مستأجِرون) + مَن بلا هويّة.

    صدق (U01): 30 صفّاً من حقلٍ وموسمٍ واحد ليست 30 شاهداً مستقلّاً. العيّنة بلا أيّ
    هويّة وحدة تُعَدّ «مجهولة الوحدة» وتُعلَن لا تُخفى.
    """
    units: dict[str, set] = {k: set() for k in _INDEPENDENCE_KEYS}
    unknown = 0
    for o in samples:
        seen_any = False
        for k in _INDEPENDENCE_KEYS:
            v = o.get(k)
            if v not in (None, ""):
                units[k].add(str(v))
                seen_any = True
        if not seen_any:
            unknown += 1
    return {
        "fields": len(units["field_id"]),
        "seasons": len(units["season_id"]),
        "farms": len(units["farm_id"]),
        "tenants": len(units["tenant_id"]),
        "unknown_unit_samples": unknown,
    }


def aggregate_evidence(
    region: str,
    outcomes: list[dict],
    expert_calibrated: bool = False,
    *,
    reviewed: bool = False,
) -> dict:
    """يجمّع نتائج القياس لمنطقة في دليل تراكميّ — نقيّ حتميّ.

    outcomes: قائمة مخرجات measure_outcome (كلّ منها {n_evaluated, n_success,
    success_flags, evaluated_at?}). expert_calibrated: هل للمنطقة قيم خبير مُسبقاً.
    صدق: العيّنة = نتيجة فيها ≥1 مقياس مُقيَّم (الفارغة لا تُحتسب). مستوى الدليل من
    عدد العيّنات (عتبة موسومة) **ثمّ** المراجعة: 0⇒none/expert_opinion،
    <العتبة⇒field_preliminary، ≥العتبة⇒field_sample_complete (عيّنة مكتملة بانتظار
    المراجعة)، و≥العتبة مع ``reviewed=True``⇒field_verified — بلوغُ العتبة وحدَه لا يعتمد.
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

    # U01 (التدقيق الموحَّد 2026-09-13): اكتمالُ العيّنة (عدُّ الصفوف) شيء، والاعتمادُ
    # الزراعيّ شيء آخر. كان بلوغُ 30 صفّاً — ولو من حقلٍ وموسمٍ واحد وبنسبة نجاح صفر —
    # يرفع الوصف إلى «مُتحقَّق ميدانيّاً» بلا مراجعة. الآن: العتبة تُنتِج
    # ``field_sample_complete`` (عيّنة مكتملة بانتظار المراجعة)، و``field_verified`` لا
    # يُمنَح إلّا مع ``reviewed=True`` (مراجعة مختصّ مُثبَتة عند المُنادي). أعدادُ الوحدات
    # المستقلّة تُعرَض إلى جانب العدّ الخام.
    if sample_count == 0:
        sample_completeness = "empty"
        evidence_level = "expert_opinion" if expert_calibrated else "none"
    elif sample_count >= _FIELD_VERIFIED_MIN_SAMPLES:
        sample_completeness = "threshold_reached"
        evidence_level = "field_verified" if reviewed else "field_sample_complete"
    else:
        sample_completeness = "below_threshold"
        evidence_level = "field_preliminary"

    samples_to_verified = max(0, _FIELD_VERIFIED_MIN_SAMPLES - sample_count)
    independence = _independence(samples)

    warnings_ar = ["عتبة جمع العيّنات تقديريّة — بلوغها وحده لا يمنح اعتماداً زراعياً أو معايرة"]
    if 0 < sample_count < _FIELD_VERIFIED_MIN_SAMPLES:
        warnings_ar.append(
            f"دليل أوّليّ ({sample_count}/{_FIELD_VERIFIED_MIN_SAMPLES}) — تبقّى {samples_to_verified} عيّنة لبلوغ عتبة الجمع"
        )
    if not reviewed:
        warnings_ar.append(
            "العيّنة بلغت العتبة لكنّ الدليل غير مُعتمَد — يلزم مراجعة مختصّ قبل وصفه «مُتحقَّقاً ميدانيّاً»"
            if evidence_level == "field_sample_complete"
            else "الدليل غير مُراجَع — يلزم تقييم الدليل ومراجعة مختصّ"
        )
    if independence["unknown_unit_samples"] > 0:
        warnings_ar.append(
            f"{independence['unknown_unit_samples']} من {sample_count} عيّنة بلا هوية حقل أو موسم أو مزرعة أو مستأجر"
            " — استقلالُ الشواهد غير قابل للإثبات"
        )
    if sample_count > 1 and (independence["fields"] <= 1 or independence["seasons"] <= 1):
        warnings_ar.append(
            f"معرّفات الحقول المتاحة: {independence['fields']}، والمواسم: {independence['seasons']}"
            " — الهوية محدودة أو ناقصة؛ العدّ لا يعني شواهد مستقلّة"
        )

    return {
        "region": region,
        "sample_count": sample_count,
        "sample_completeness": sample_completeness,
        "independence": independence,
        "review_status": "reviewed" if reviewed else "unreviewed",
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
    *,
    reviewed: bool = False,
) -> dict:
    """يبني الدليل التراكميّ من صفوف outcome_record المُدامة — يُغلق P0-2 (إدامة الدليل).

    rows: صفوف outcome_record المُدامة، كلّ صفّ {metrics, created_at}؛ metrics هي مخرجات
    measure_outcome المخزّنة (فيها n_evaluated/n_success/success_flags). يستخرج منها مدخلات
    aggregate_evidence (evaluated_at=created_at) ثمّ يفوّض إليه — **مصدر واحد** لمنطق العتبة
    والمستوى (لا تكرار). نقيّ حتميّ (لا I/O): الاستعلام يجري في الموجِّه ويُمرَّر ناتجه هنا.

    صدق: الدليل الآن مدعوم بنتائج **مُدامة** (لا حمولة طلب عابرة) — يتراكم نحو عتبة الجمع
    عبر الزمن. الناقص (metrics فارغة) لا يُحتسب عيّنة (aggregate_evidence يُسقِط n_evaluated=0).
    """
    outcomes: list[dict] = []
    for r in rows:
        m = r.get("metrics") or {}
        sample = {
            "n_evaluated": m.get("n_evaluated", 0),
            "n_success": m.get("n_success", 0),
            "success_flags": m.get("success_flags", []),
            "evaluated_at": r.get("created_at"),
        }
        # هويّةُ الوحدة تُمرَّر إلى أعداد الاستقلال متى حملها الصفّ أو مقاييسُه — وإلّا بقيت
        # العيّنة «مجهولة الوحدة» وتُعلَن كذلك (Copilot على #1001: كان المحوِّل يُسقِطها كلَّها).
        for key in _INDEPENDENCE_KEYS:
            value = r.get(key)
            if value in (None, ""):
                value = m.get(key)
            if value not in (None, ""):
                sample[key] = value
        outcomes.append(sample)
    out = aggregate_evidence(
        region, outcomes, expert_calibrated=expert_calibrated, reviewed=reviewed
    )
    # صدق: نوضّح مصدر الدليل (نتائج مُدامة) وعدد الصفوف المقروءة (قد يفوق العيّنات المُحتسَبة).
    out["source"] = "persisted_outcomes"
    out["persisted_rows"] = len(rows)
    return out
