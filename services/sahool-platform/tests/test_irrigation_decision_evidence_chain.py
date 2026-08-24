from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timezone

from api.irrigation_decision_evidence_chain import (
    CANONICALIZATION_VERSION,
    canonical_json,
    stage_digest,
    verify_chain,
    verify_prefix,
)


def _ulid(ch: str) -> str:
    return "01ARZ3NDEKTSV4RRFFQ69G5FAV"[:-1] + ch


def _base(seq: int, stage: str, stage_id: str, parent_id=None, parent_digest=None):
    return {
        "schema": "sahool.evidence-chain-stage/v1.1",
        "contract_revision": "v1.1-errata2",
        "chain_id": _ulid("1"),
        "correlation_id": _ulid("2"),
        "stage_id": stage_id,
        "parent_stage_id": parent_id,
        "parent_digest": parent_digest,
        "stage_digest": "0" * 64,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "digest_algorithm": "sha256",
        "sequence": seq,
        "stage": stage,
        "related_stage_ids": [],
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "succeeded",
    }


def _chain():
    ids = [_ulid(str(i)) for i in range(9)]
    stages = []
    state = _base(0, "CanonicalState", ids[0])
    state.update({"state_snapshot_id": _ulid("A"), "state_digest": "1" * 64})
    stages.append(state)

    prediction = _base(1, "Prediction", ids[1], ids[0], None)
    prediction.update(
        {
            "prediction_id": _ulid("B"),
            "model_version": "demand-v1",
            "input_digest": "1" * 64,
            "predicted": {
                "required_volume_l": 18.4,
                "recommended_window_start": "2026-08-24T08:00:00Z",
                "recommended_window_end": "2026-08-24T10:00:00Z",
                "predicted_vwc_delta": 1.8,
                "confidence": 0.87,
                "explanation": "ET0=5.2; Kc=1.1; VWC_30=0.18",
            },
        }
    )
    stages.append(prediction)

    decision = _base(2, "DecisionCandidate", ids[2], ids[1], None)
    decision.update(
        {
            "decision_id": _ulid("C"),
            "prediction_id": prediction["prediction_id"],
            "decision_domains": ["irrigation"],
            "candidate": {
                "irrigation_volume_l": 18.4,
                "recommended_window_start": "2026-08-24T08:00:00Z",
                "recommended_window_end": "2026-08-24T10:00:00Z",
            },
            "policy_review": {
                "requires_human_review": True,
                "execution_allowed": False,
                "salinity_gate": "PASS",
            },
        }
    )
    stages.append(decision)

    hydraulic = _base(3, "HydraulicFeasibility", ids[3], ids[2], None)
    hydraulic.update(
        {
            "decision_id": decision["decision_id"],
            "feasibility": {
                "result": "feasible",
                "constraints": {
                    "available_flow_l_s": 12.0,
                    "required_flow_l_s": 9.5,
                    "pressure_bar": 3.1,
                    "reservations": [],
                },
                "checked_network_model_version": "irr-net-v1",
            },
        }
    )
    stages.append(hydraulic)

    execution = _base(4, "Execution", ids[4], ids[3], None)
    execution.update(
        {
            "decision_id": decision["decision_id"],
            "execution_id": _ulid("D"),
            "requested_volume_l": 18.4,
            "command": {"valve_id": "v1", "duration_s": 720, "flow_l_s": 9.5},
            "policy_approval": {"approved_by": "operator", "approved_at": "2026-08-24T08:01:00Z"},
        }
    )
    stages.append(execution)

    as_applied = _base(5, "AsApplied", ids[5], ids[4], None)
    as_applied.update(
        {
            "decision_id": decision["decision_id"],
            "execution_id": execution["execution_id"],
            "measured_volume_l": 17.9,
            "measured_flow_l_s": 9.3,
            "measured_duration_s": 725,
            "evidence_ref": "exec-evidence-1",
        }
    )
    stages.append(as_applied)

    outcome = _base(6, "ObservedOutcome", ids[6], ids[5], None)
    outcome.update(
        {
            "decision_id": decision["decision_id"],
            "execution_id": execution["execution_id"],
            "observed_vwc_delta": 1.2,
            "observed_drainage_ratio": 0.08,
            "observed_drain_ec_ds_m": 2.6,
            "observed_crop_stress_change": "decreased",
            "measured_at": "2026-08-24T12:00:00Z",
            "evidence_ref": "outcome-1",
        }
    )
    stages.append(outcome)

    error = _base(7, "PredictionError", ids[7], ids[6], None)
    error.update(
        {
            "decision_id": decision["decision_id"],
            "execution_id": execution["execution_id"],
            "errors": {
                "volume_error_l": -0.5,
                "vwc_delta_error_pct": -0.6,
                "et0_error_mm_day": None,
                "demand_error_l": None,
                "mpc_error": None,
                "hydraulic_model_error": None,
            },
            "calculation_note": "predicted-observed",
        }
    )
    stages.append(error)

    candidate = _base(8, "ModelCalibrationCandidate", ids[8], ids[7], None)
    candidate.update(
        {
            "decision_id": decision["decision_id"],
            "execution_id": execution["execution_id"],
            "target": "root_zone_balance",
            "candidate_parameters": {
                "old_value": 0.5,
                "proposed_value": 0.52,
                "reason": "observed error",
            },
            "governance": {
                "auto_adjust": False,
                "review_required": True,
                "review_status": "pending",
                "promotion_candidate_id": _ulid("E"),
            },
        }
    )
    stages.append(candidate)

    # Calculate the chain in causal order; each parent digest is the actual previous digest.
    for i, item in enumerate(stages):
        if i:
            item["parent_digest"] = stages[i - 1]["stage_digest"]
        item["stage_digest"] = stage_digest(item)
    return stages


def test_full_chain_verifies():
    result = verify_chain(_chain())
    assert result["status"] == "VERIFIED", result


def test_parent_tamper_is_rejected():
    stages = _chain()
    stages[3]["parent_digest"] = "f" * 64
    assert verify_chain(stages)["status"] == "REJECTED"


def test_content_tamper_is_rejected_even_when_digest_is_stale():
    stages = _chain()
    stages[1]["predicted"]["confidence"] = 0.1
    assert verify_chain(stages)["status"] == "REJECTED"


def test_prefix_is_valid_for_decision_c6():
    stages = _chain()[:4]
    result = verify_prefix(stages)
    assert result["status"] == "VERIFIED"
    assert result["last_stage"] == "HydraulicFeasibility"


def test_non_finite_json_is_rejected():
    try:
        canonical_json({"x": float("nan")})
    except ValueError:
        pass
    else:
        raise AssertionError("NaN must be rejected")


# ── عزلُ حرّاس E2 عن حارس E1 ───────────────────────────────────────────────
# الاختباراتُ أعلاه تعبث بالمحتوى **ولا تُعيد حساب البصمات**، فيُمسَك العبثُ
# بحارس E1 (`stage_digest`) قبل أن يبلغ حارسَ E2 إطلاقاً. مقيسٌ بالزرع:
# إسقاطُ فحصَي `parent_stage_id` و`parent_digest` كان يُبقي **٥/٥ خضراء** —
# تغطيةٌ بالاسم لا بالأثر، وثغرةٌ يسترها حارسٌ مجاور.
#
# فتُعاد البصماتُ هنا بعد العبث كي **لا** يستره الجارُ، فيبقى الحارسُ
# المقصودُ وحدَه هو ما يُطلِق.


def _relink(stages):
    """أعِد حساب بصمات المراحل بعد العبث — كي يُعزَل حارسُ E2 عن حارس E1."""
    for st in stages:
        st["stage_digest"] = stage_digest(st)
    return stages


def test_parent_stage_id_link_is_checked_on_its_own():
    """`parent_stage_id` المقطوع يُرفَض ولو كانت كلُّ البصمات متّسقة.

    `test_parent_tamper_is_rejected` يعبث بـ`parent_digest` لا بهذا الحقل،
    فكان الحقلُ **بلا اختبارٍ إطلاقاً** رغم أنّ الاسمَ يوحي بتغطيته.
    """
    stages = _relink(_chain())
    stages[3]["parent_stage_id"] = _ulid("Z")
    _relink(stages)
    result = verify_chain(stages)
    assert result["status"] == "REJECTED"
    assert any("parent_stage_id does not point to previous stage" in e for e in result["errors"]), (
        result
    )


def test_parent_digest_link_is_checked_on_its_own():
    """`parent_digest` المقطوع يُرفَض بحارس E2 نفسِه لا بحارس E1 عرَضاً."""
    stages = _relink(_chain())
    stages[3]["parent_digest"] = "f" * 64
    _relink(stages)
    result = verify_chain(stages)
    assert result["status"] == "REJECTED"
    assert any(
        "parent_digest does not match previous stage_digest" in e for e in result["errors"]
    ), result


def test_an_invalid_prefix_is_rejected_not_only_a_valid_one_accepted():
    """المسارُ السالب لـC6 — `test_prefix_is_valid_for_decision_c6` يختبر السعيدَ وحدَه.

    وقبولُ الصحيح لا يُثبِت رفضَ الخاطئ: بوّابةٌ تقول «نعم» دائماً تمرّ ذاك
    الاختبارَ وتُخفِق في غرضها كلِّه.
    """
    stages = _chain()[:4]
    stages[1], stages[2] = stages[2], stages[1]
    result = verify_prefix(stages)
    assert result["status"] == "REJECTED", result


def test_non_finite_rejection_carries_the_contract_reason_not_a_generic_one():
    """الرفضُ يجب أن يكون **من العقد** لا من `json` عرَضاً.

    `json.dumps(allow_nan=False)` يرفض NaN وحدَه، فكان `_reject_nonfinite`
    **زائداً غيرَ مُثبَت**: إسقاطُه يُبقي ٥/٥ خضراء. مقيسٌ بتعطيله في الذاكرة —
    بقي الرفضُ قائماً برسالة `json` العامّة.

    فالمُثبَّتُ هنا هو الرسالةُ لا الرفض: «‏E1» تقول للقارئ **أيُّ عقدٍ** خُولِف،
    ورسالةٌ عامّة تتركه يخمّن.
    """
    import pytest

    with pytest.raises(ValueError, match="E1"):
        canonical_json({"deeply": {"nested": [1.0, float("inf")]}})


def test_the_schema_pins_stage_to_sequence_which_is_why_prefix_mismatch_is_unreachable():
    """يحرس **البرهانَ** لا الفرع: لماذا لا يُسجَّل تكذيبٌ لـ`prefix mismatch`.

    قِيس بالجداء الكامل — ٩ مراحل × ٩ مواضع = ٨١ مِسباراً — أنّ المخطَّط
    يُثبِّت (المرحلة ⇄ التسلسل) بصفر موضعٍ حرّ. ومع فرض `_verify_common`
    تتابعاً `0..n-1`، تصير المرحلةُ في الموضع i هي `_STAGE_ORDER[i]` لزوماً،
    فيستحيل بلوغُ `actual != expected` في `verify_prefix`.

    فهذا الاختبارُ هو الشرطُ الذي يُبقي ذلك صادقاً: إن ارتخى المخطَّطُ يوماً
    عن تثبيت الاقتران، **يحمرّ هنا** — فيُعلَم أنّ الفرعَ عاد حيّاً وأنّه صار
    يلزمه تكذيبٌ خاصّ به، بدل أن يبقى «مُغطًّى» بادّعاءٍ قديم.
    """
    from api.irrigation_decision_evidence_chain import _STAGE_ORDER, validate_stage_schema

    free = [
        (stage["stage"], seq)
        for index, stage in enumerate(_chain())
        for seq in range(len(_STAGE_ORDER))
        if seq != index and not validate_stage_schema({**stage, "sequence": seq})
    ]
    assert not free, (
        f"المخطَّطُ لم يعد يُثبِّت (المرحلة ⇄ التسلسل) في {free} — "
        "فرعُ `prefix mismatch` صار قابلاً للبلوغ ويلزمه تكذيبٌ خاصّ"
    )
