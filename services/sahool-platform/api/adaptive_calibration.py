"""api/adaptive_calibration.py — المعايرة التكيّفيّة (Adaptive Calibration) #388

قمّة حلقة التعلّم: حيث — **وفقط حينها** — يصبح تعديل المعايرة مقترَحاً آليّاً **تحت
حُكم الدليل**. لكن بضوابط صدق صارمة:

  • **بوّابة دليل**: لا اقتراح تعديل إلّا حين evidence_level=field_verified وعيّنات ≥ حدّ
    وإشارة اتّجاه واضحة. دون ذلك ⇒ status=gated (لا تغيير).
  • **خطوة محدودة ومقصوصة**: ±0.05 كحدّ أقصى لكلّ دورة، ضمن نطاق فيزيائيّ آمن
    (تدرّج لا قفز) — لا تتجاوز حدود الأدبيّات.
  • **عكوسيّة**: يعيد القيمة السابقة دائماً (previous_value) — قابل للتراجع.
  • **لا يكتب حالة عالميّة**: نقيّ حتميّ — **يقترح** فقط؛ التطبيق/الحفظ خطوة ops
    منفصلة (تبقى مراجعة بشريّة ما لم تُفتَح بوّابة auto_apply_eligible).

صدق: applied=False دائماً هنا (لا تعديل خفيّ)؛ القرار النهائيّ للإنسان/ops.
"""

from __future__ import annotations

# أدنى عيّنات للسماح باقتراح تعديل آليّ. ⚠ تقديريّ.
_ADAPT_MIN_SAMPLES = 30
# أقصى خطوة تعديل لـraw_fraction لكلّ دورة (تدرّج آمن). ⚠ تقديريّ.
_MAX_STEP = 0.05
# النطاق الفيزيائيّ الآمن لـraw_fraction (p) — لا نخرج عنه.
_RAW_BOUNDS = (0.30, 0.70)
# عتبة دلالة فرق الإجهاد (يوم) لاعتباره إشارة اتّجاه.
_STRESS_SIGNAL = 0.5


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def propose_calibration_adjustment(
    region_profile: dict,
    evidence: dict,
    mean_stress_delta: float | None = None,
) -> dict:
    """يقترح تعديل معايرة منطقة تحت بوّابة الدليل — نقيّ حتميّ، لا يطبّق.

    region_profile: get_calibration(region).to_dict(). evidence: aggregate_evidence.
    mean_stress_delta: متوسّط (المرصود − المتنبَّأ) لأيّام الإجهاد (موجب = إجهاد أسوأ).
    صدق: applied=False؛ الخطوة محدودة ومقصوصة؛ previous_value للعكوسيّة.
    """
    region = region_profile.get("region", "_generic")
    level = evidence.get("evidence_level", "none")
    n = evidence.get("sample_count", 0)

    # ── بوّابة الدليل ──
    gate_ok = level == "field_verified" and n >= _ADAPT_MIN_SAMPLES
    if not gate_ok:
        return {
            "region": region,
            "gate": {
                "passed": False,
                "reason_ar": f"الدليل غير كافٍ ({level}, {n} عيّنة) — يلزم field_verified و≥{_ADAPT_MIN_SAMPLES}",
            },
            "proposals": [],
            "status": "gated",
            "applied": False,
            "reversible": True,
            "requires_human_approval": True,
            "calibrated": False,
            "warnings_ar": ["لا تعديل دون دليل ميدانيّ كافٍ — اجمع المزيد من النتائج"],
        }

    # ── إشارة الاتّجاه (تحتاج فرق إجهاد) ──
    if mean_stress_delta is None or abs(mean_stress_delta) < _STRESS_SIGNAL:
        return {
            "region": region,
            "gate": {"passed": True, "reason_ar": "الدليل كافٍ"},
            "proposals": [],
            "status": "no_signal",
            "applied": False,
            "reversible": True,
            "requires_human_approval": True,
            "calibrated": False,
            "warnings_ar": ["الدليل كافٍ لكن لا إشارة اتّجاه واضحة (فرق الإجهاد) — راقِب"],
        }

    # ── الاقتراح: إجهاد أسوأ من المتوقّع ⇒ خفّض p (اسقِ أبكر)؛ والعكس ⇒ ارفع p ──
    current_p = float(region_profile.get("raw_fraction", 0.5))
    # خطوة متناسبة مع الإشارة، مقصوصة عند _MAX_STEP، باتّجاه يقلّل الإجهاد.
    step = _clamp(0.02 * abs(mean_stress_delta), 0.0, _MAX_STEP)
    direction = -1.0 if mean_stress_delta > 0 else 1.0  # إجهاد أعلى ⇒ p أقلّ
    proposed_p = round(_clamp(current_p + direction * step, *_RAW_BOUNDS), 3)

    dir_ar = "خفض p (ريّ أبكر) لتقليل الإجهاد" if direction < 0 else "رفع p (ريّ أقلّ) لتقليل الهدر"
    proposals = [
        {
            "parameter": "raw_fraction",
            "current": current_p,
            "proposed": proposed_p,
            "delta": round(proposed_p - current_p, 3),
            "direction_ar": dir_ar,
            "rationale_ar": (
                f"متوسّط فرق الإجهاد {mean_stress_delta:+.1f} يوم عبر {n} عيّنة مُتحقَّقة — "
                f"تعديل متدرّج محدود (±{_MAX_STEP}) ضمن النطاق الآمن {_RAW_BOUNDS}"
            ),
            "bounds": list(_RAW_BOUNDS),
        }
    ]
    no_change = proposed_p == current_p
    return {
        "region": region,
        "gate": {"passed": True, "reason_ar": "الدليل كافٍ وإشارة اتّجاه واضحة"},
        "proposals": [] if no_change else proposals,
        "status": "no_change_at_bound" if no_change else "auto_apply_eligible",
        "applied": False,  # صدق: لا تطبيق خفيّ — ops/إنسان يطبّق (عكوسيّاً)
        "reversible": True,
        "previous_values": {"raw_fraction": current_p},
        "requires_human_approval": False if not no_change else True,
        "calibrated": False,
        "warnings_ar": [
            "اقتراح مؤهَّل للتطبيق الآليّ تحت حُكم الدليل — لكنّه عكوسيّ ومحدود الخطوة",
        ],
    }
