"""api/outcome_measurement.py — قياس نتائج القرار (Outcome Measurement)

#383: الطبقة التي تفرّق بين «نظام دعم قرار» و«نظام تشغيل». حتى الآن السلسلة:
رصد → تنبّؤ → قرار. هذه تضيف الخطوة التالية: **قياس النتيجة الفعليّة** للقرار:

  هل اتُّبِع الريّ الموصى به؟ ما فرق الميزانية عن الاستهلاك؟ هل وقع الإجهاد كما تُنبِّئ؟
  هل بلغ الإنتاج الهدف؟

نقيّة حتميّة (لا I/O). تقارن **المُخطَّط** (من القرار/الخطّة) بـ**المرصود** (قياس
ميدانيّ). صدق: تُقيِّم فقط ما توفّر طرفاه (مُخطَّط ومرصود)؛ الناقص يُعلَن «يحتاج بيانات»
لا يُفبرَك. فرق الميزانية أو التنفيذ ليس وفراً سببياً مثبتاً. هذه نصف حلقة التعلّم؛ «التعلّم» (تعديل المعايرة) طبقة لاحقة مستقلّة.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

# هامش تطابق الريّ (±) لاعتبار القرار «مُتَّبَعاً» — نسبة من المُخطَّط. تقديريّ.
_IRRIGATION_TOLERANCE = 0.15
# عتبة بلوغ الإنتاج المستهدف (نسبة من المتوقّع). تقديريّ.
_YIELD_MET_FRACTION = 0.90


def _delta(actual: float | None, planned: float | None) -> float | None:
    if actual is None or planned is None:
        return None
    return round(actual - planned, 2)


def measure_outcome(planned: dict, actual: dict) -> dict:
    """يقارن قرار/خطّة بالنتيجة الفعليّة المرصودة ⇒ تقييم لكلّ مقياس — نقيّ حتميّ.

    planned: {recommended_irrigation_mm, predicted_stress_days, expected_yield_t_ha,
              season_budget_mm}. actual: {actual_irrigation_mm, observed_stress_days,
              actual_yield_t_ha, actual_water_used_mm}. كلّها اختياريّة.
    صدق: مقياس بلا طرفَيه ⇒ status=needs_data (لا حكم مُختلق).
    """
    metrics: list[dict] = []
    success_flags: list[str] = []
    warnings_ar: list[str] = []

    # ١) اتّباع الريّ: المرصود مقابل الموصى به.
    rec = planned.get("recommended_irrigation_mm")
    act_irr = actual.get("actual_irrigation_mm")
    if rec is not None and act_irr is not None:
        d = act_irr - rec
        tol = abs(rec) * _IRRIGATION_TOLERANCE
        if abs(d) <= tol:
            status, label = "followed", "اتُّبِع الريّ الموصى به"
            success_flags.append("irrigation_followed")
        elif d < 0:
            status, label = "under", "ريّ أقلّ من الموصى به (احتمال إجهاد)"
        else:
            status, label = "over", "ريّ أكثر من الموصى به (هدر محتمل)"
        metrics.append(
            {
                "key": "irrigation",
                "planned": rec,
                "actual": act_irr,
                "delta": round(d, 2),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {
                "key": "irrigation",
                "status": "needs_data",
                "label_ar": "يحتاج الريّ الموصى به والمرصود",
            }
        )

    # ٢) الإجهاد: المرصود مقابل المُتنبَّأ (أقلّ = أفضل).
    pred_s = planned.get("predicted_stress_days")
    obs_s = actual.get("observed_stress_days")
    if pred_s is not None and obs_s is not None:
        if obs_s < pred_s:
            status, label = "better", "إجهاد أقلّ من المتوقّع"
            success_flags.append("stress_better")
        elif obs_s == pred_s:
            status, label = "as_predicted", "الإجهاد كما تُنبِّئ"
        else:
            status, label = "worse", "إجهاد أكثر من المتوقّع — راجِع الخطّة"
        if obs_s == 0:
            success_flags.append("stress_avoided")
        metrics.append(
            {
                "key": "stress",
                "predicted": pred_s,
                "observed": obs_s,
                "delta": obs_s - pred_s,
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {"key": "stress", "status": "needs_data", "label_ar": "يحتاج الإجهاد المتنبَّأ والمرصود"}
        )

    # ٣) الإنتاج: الفعليّ مقابل المتوقّع.
    exp_y = planned.get("expected_yield_t_ha")
    act_y = actual.get("actual_yield_t_ha")
    if exp_y is not None and act_y is not None and exp_y > 0:
        ratio = act_y / exp_y
        if ratio >= 1.0:
            status, label = "above", "تجاوز الإنتاج المتوقّع"
            success_flags.append("yield_met")
        elif ratio >= _YIELD_MET_FRACTION:
            status, label = "met", "بلغ الإنتاج المستهدف تقريباً"
            success_flags.append("yield_met")
        else:
            status, label = "below", "إنتاج دون المتوقّع"
        metrics.append(
            {
                "key": "yield",
                "expected": exp_y,
                "actual": act_y,
                "delta": _delta(act_y, exp_y),
                "ratio": round(ratio, 3),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {"key": "yield", "status": "needs_data", "label_ar": "يحتاج الإنتاج المتوقّع والفعليّ"}
        )

    # ٤) الوفر/الميزانيّة المائيّة: الماء الفعليّ مقابل الميزانيّة.
    budget = planned.get("season_budget_mm")
    used = actual.get("actual_water_used_mm")
    if budget is not None and used is not None:
        d = used - budget
        if used <= budget:
            status, label = "within", "ضمن الميزانيّة المائيّة"
            success_flags.append("water_within_budget")
        else:
            status, label = "exceeded", "تجاوز الميزانيّة المائيّة"
        metrics.append(
            {
                "key": "water_budget",
                "planned": budget,
                "actual": used,
                "delta": round(d, 2),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {
                "key": "water_budget",
                "status": "needs_data",
                "label_ar": "يحتاج الميزانيّة والماء المستهلَك",
            }
        )

    evaluated = [m for m in metrics if m["status"] != "needs_data"]
    data_completeness = round(len(evaluated) / len(metrics), 2) if metrics else 0.0
    if not evaluated:
        warnings_ar.append("لا مقياس قابل للتقييم — زوّدنا بقياسات ميدانيّة (ريّ/إجهاد/إنتاج)")

    return {
        "metrics": metrics,
        "success_flags": success_flags,
        "n_evaluated": len(evaluated),
        "n_success": len(success_flags),
        "data_completeness": data_completeness,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }


# Historical measured execution comparison: read-only and no causal savings claim.
_SCENARIO_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _scenario_digest(body: dict) -> str:
    try:
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError, OverflowError):
        return ""
    return hashlib.sha256(raw.encode()).hexdigest()


def _scenario_number(value: Any, *, positive: bool = True) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        value = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        return None
    return value


def _scenario_object(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def _scenario_evidence(row: dict, arm: str) -> tuple[dict, float | None, list[str]]:
    applied = _scenario_object(row.get("as_applied"))
    verification = _scenario_object(row.get("verification"))
    reasons: list[str] = []
    if row.get("state") != "reconciled" or row.get("ledger_eligible") is not True:
        reasons.append(f"{arm}:RECONCILED_LEDGER_EVIDENCE_REQUIRED")
    if (
        row.get("execution_mode") != "manual_measured"
        or applied.get("quality") not in ("measured_meter", "measured_flow")
        or applied.get("ledger_eligible") is not True
        or applied.get("blocking_reasons")
    ):
        reasons.append(f"{arm}:MEASURED_WATER_EVIDENCE_REQUIRED")
    digest = row.get("as_applied_digest")
    body = {key: value for key, value in applied.items() if key != "as_applied_digest"}
    if (
        not isinstance(digest, str)
        or not _SCENARIO_DIGEST.fullmatch(digest)
        or applied.get("as_applied_digest") != digest
        or _scenario_digest(body) != digest
        or str(applied.get("execution_id")) != str(row.get("execution_id"))
    ):
        reasons.append(f"{arm}:AS_APPLIED_DIGEST_MISMATCH")
    verification_body = {
        key: verification.get(key)
        for key in (
            "execution_id",
            "as_applied_digest",
            "reviewer_id",
            "reviewed_at",
            "volume_verified",
            "timing_verified",
            "field_verified",
            "status",
            "blocking_reasons",
        )
    }
    # The verifier hashes datetime.isoformat() (+00:00); Pydantic's JSON mode
    # stores UTC as Z. Restore the original canonical representation.
    try:
        reviewed_at = datetime.fromisoformat(
            str(verification.get("reviewed_at")).replace("Z", "+00:00")
        )
        verified_at = datetime.fromisoformat(
            str(verification.get("verified_at")).replace("Z", "+00:00")
        )
        verification_time_valid = reviewed_at.utcoffset() is not None and reviewed_at == verified_at
        verification_body["reviewed_at"] = reviewed_at.isoformat()
    except ValueError:
        verification_time_valid = False
        verification_body["reviewed_at"] = None
    evidence = verification.get("evidence_digests")
    evidence_valid = (
        isinstance(evidence, list)
        and bool(evidence)
        and all(isinstance(item, str) and _SCENARIO_DIGEST.fullmatch(item) for item in evidence)
    )
    verification_body["evidence_digests"] = sorted(set(evidence)) if evidence_valid else []
    vd = row.get("verification_digest")
    if (
        verification.get("status") != "verified"
        or verification.get("ledger_eligible") is not True
        or verification.get("blocking_reasons") != []
        or str(verification.get("execution_id")) != str(row.get("execution_id"))
        or verification.get("as_applied_digest") != digest
        or not evidence_valid
        or not verification_time_valid
        or not verification.get("reviewer_id")
        or any(
            verification.get(key) is not True
            for key in ("volume_verified", "timing_verified", "field_verified")
        )
        or not isinstance(vd, str)
        or not _SCENARIO_DIGEST.fullmatch(vd)
        or verification.get("verification_digest") != vd
        or _scenario_digest(verification_body) != vd
    ):
        reasons.append(f"{arm}:VERIFICATION_BINDING_REQUIRED")
    depth = _scenario_number(row.get("target_depth_mm"))
    volume = _scenario_number(row.get("target_volume_m3"))
    area = volume / depth / 10 if depth is not None and volume is not None else None
    if area is None or not math.isfinite(area) or area <= 0:
        reasons.append(f"{arm}:POSITIVE_AREA_REQUIRED")
        area = None
    actual_volume = _scenario_number(applied.get("actual_volume_m3"))
    actual_depth = _scenario_number(applied.get("actual_depth_mm"))
    if actual_volume is None or actual_depth is None:
        reasons.append(f"{arm}:FINITE_POSITIVE_WATER_REQUIRED")
    elif area is not None:
        expected_volume = actual_depth * area * 10
        # Half the stored volume quantum (0.001 m³), plus half the depth
        # quantum (0.0001 mm) converted over this area. A fixed absolute
        # tolerance falsely rejects large fields; a relative tolerance grows
        # with the quantity instead of the actual rounding uncertainty.
        tolerance = 0.0005 + 0.0005 * area + math.ulp(actual_volume) + math.ulp(expected_volume)
        if not math.isclose(actual_volume, expected_volume, rel_tol=0.0, abs_tol=tolerance):
            reasons.append(f"{arm}:WATER_AREA_INCONSISTENT")
    return applied, area, reasons


def compare_irrigation_executions(baseline: dict, candidate: dict) -> dict:
    """Return null deltas unless both bound measured records are comparable."""
    left, left_area, reasons = _scenario_evidence(baseline, "baseline")
    right, right_area, right_reasons = _scenario_evidence(candidate, "candidate")
    reasons.extend(right_reasons)
    for key in ("field_id", "season_id", "system_id"):
        if not baseline.get(key) or not candidate.get(key) or baseline[key] != candidate[key]:
            reasons.append(f"SAME_{key.upper()}_REQUIRED")
    if str(baseline.get("execution_id")) == str(candidate.get("execution_id")):
        reasons.append("DISTINCT_EXECUTIONS_REQUIRED")
    if (
        left_area is not None
        and right_area is not None
        and not math.isclose(left_area, right_area, rel_tol=1e-6, abs_tol=1e-9)
    ):
        reasons.append("SAME_AREA_REQUIRED")
    usable = not reasons
    water = dict.fromkeys(
        (
            "baseline_volume_m3",
            "candidate_volume_m3",
            "baseline_minus_candidate_m3",
            "baseline_depth_mm",
            "candidate_depth_mm",
            "baseline_minus_candidate_mm",
        )
    )
    runtime = dict.fromkeys(("baseline_hours", "candidate_hours", "baseline_minus_candidate_hours"))
    if usable:
        for suffix, source in (("volume_m3", "actual_volume_m3"), ("depth_mm", "actual_depth_mm")):
            a, b = float(left[source]), float(right[source])
            water[f"baseline_{suffix}"] = a
            water[f"candidate_{suffix}"] = b
            water[
                f"baseline_minus_candidate_{suffix.removeprefix('volume_').removeprefix('depth_')}"
            ] = round(a - b, 4)
        a = _scenario_number(left.get("actual_runtime_h"))
        b = _scenario_number(right.get("actual_runtime_h"))
        if a is not None and b is not None:
            runtime.update(
                baseline_hours=a, candidate_hours=b, baseline_minus_candidate_hours=round(a - b, 4)
            )
        else:
            reasons.append("RUNTIME_MEASUREMENT_REQUIRED")
    explanations = {
        "RECONCILED_LEDGER_EVIDENCE_REQUIRED": "يلزم تنفيذ مُسوّى ومؤهل لدفتر المياه.",
        "MEASURED_WATER_EVIDENCE_REQUIRED": "يلزم قياس المياه؛ التقدير وحده لا يكفي.",
        "AS_APPLIED_DIGEST_MISMATCH": "بصمة قياس التنفيذ غير متطابقة.",
        "VERIFICATION_BINDING_REQUIRED": "التحقق المستقل غير مكتمل أو غير مربوط بالقياس.",
        "POSITIVE_AREA_REQUIRED": "مساحة التنفيذ الموجبة غير متاحة.",
        "FINITE_POSITIVE_WATER_REQUIRED": "كمية المياه أو عمقها غير صالح للمقارنة.",
        "WATER_AREA_INCONSISTENT": "الكمية والعمق لا يتفقان مع مساحة التنفيذ.",
        "SAME_FIELD_ID_REQUIRED": "يلزم الحقل نفسه للتنفيذين.",
        "SAME_SEASON_ID_REQUIRED": "يلزم الموسم نفسه للتنفيذين.",
        "SAME_SYSTEM_ID_REQUIRED": "يلزم نظام الري نفسه للتنفيذين.",
        "DISTINCT_EXECUTIONS_REQUIRED": "اختر تنفيذين مختلفين.",
        "SAME_AREA_REQUIRED": "مساحتا التنفيذ غير متطابقتين.",
        "RUNTIME_MEASUREMENT_REQUIRED": "زمن التشغيل المقيس غير متاح للتنفيذين.",
    }
    blockers_ar = [
        (
            "خط الأساس: "
            if reason.startswith("baseline:")
            else "التنفيذ المقارن: "
            if reason.startswith("candidate:")
            else ""
        )
        + explanations[reason.split(":")[-1]]
        for reason in reasons
    ]
    return {
        "status": "measured_comparison" if usable else "needs_data",
        "baseline_execution_id": str(baseline["execution_id"]),
        "candidate_execution_id": str(candidate["execution_id"]),
        "water": water,
        "runtime": runtime,
        "evidence": {
            arm: {
                "as_applied_digest": row["as_applied_digest"],
                "verification_digest": row["verification_digest"],
            }
            if usable
            else None
            for arm, row in (("baseline", baseline), ("candidate", candidate))
        },
        "causal_effect": {"status": "not_established"},
        "energy": {"status": "not_measured"},
        "economics": {"status": "not_computed"},
        "reasons": reasons,
        "warnings_ar": blockers_ar
        + [
            "مقارنة تاريخية وصفية بين تنفيذين؛ فرق المياه ليس وفراً سببياً مثبتاً.",
            "احتياج المحصول والطقس والتربة قد يختلف؛ لا توجد مقارنة مضبوطة أو قياسات أثر زراعي.",
            "الطاقة والتعرفة والتكاليف الكاملة غير مقيسة؛ زمن التشغيل لا يثبت توفير المال.",
        ],
    }
