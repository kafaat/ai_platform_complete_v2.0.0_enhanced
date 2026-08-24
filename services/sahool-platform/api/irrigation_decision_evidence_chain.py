"""Fail-closed verifier for the IRRIGATION EvidenceChain v1.1-errata2.

This is a verification/lineage layer only.  It does not create irrigation,
fertigation, MPC, or actuator decisions.

The normative contract is ``docs/contracts/IRRIGATION-CONTRACTS-v1.1-errata2.md``.
The verifier enforces the two constraints that JSON Schema cannot enforce:
E1 deterministic stage digests and E2 strict linear parent linkage.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = PLATFORM_ROOT / "schemas/irrigation-contracts/v1.1-errata2/evidence-chain.schema.json"
SCHEMA_VERSION = "sahool.evidence-chain-stage/v1.1"
CONTRACT_REVISION = "v1.1-errata2"
CANONICALIZATION_VERSION = "sahool-canonical-json-v1"

_STAGE_ORDER = (
    "CanonicalState",
    "Prediction",
    "DecisionCandidate",
    "HydraulicFeasibility",
    "Execution",
    "AsApplied",
    "ObservedOutcome",
    "PredictionError",
    "ModelCalibrationCandidate",
)


def _reject_nonfinite(value: Any) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number is forbidden by E1")
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite(item)


def canonical_json(value: Any) -> bytes:
    """Return the deterministic UTF-8 JSON representation required by E1."""
    _reject_nonfinite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stage_digest(stage: dict[str, Any]) -> str:
    """Compute E1 stage digest, excluding volatile identity/time and the digest itself."""
    payload = dict(stage)
    payload.pop("stage_id", None)
    payload.pop("timestamp", None)
    payload.pop("stage_digest", None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_stage_schema(stage: dict[str, Any]) -> list[str]:
    """Return schema errors in deterministic path order."""
    errors = sorted(_validator().iter_errors(stage), key=lambda e: list(e.path))
    return [f"schema:{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


def verify_chain(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify one complete, ordered, causally linked EvidenceChain.

    A complete chain contains sequence 0..8.  For live execution a caller may
    intentionally stop at an earlier stage; use ``verify_prefix`` for that case.
    """
    errors = _verify_common(stages)
    if not errors:
        if len(stages) != len(_STAGE_ORDER):
            errors.append(f"chain must contain all {_STAGE_ORDER}; got {len(stages)} stages")
        else:
            expected = list(_STAGE_ORDER)
            actual = [s["stage"] for s in stages]
            if actual != expected:
                errors.append(f"sequence mismatch: expected {expected}, got {actual}")
    return _result(stages, errors, complete=True)


def verify_prefix(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a valid prefix, suitable for C6 observed/decision evidence."""
    errors = _verify_common(stages)
    if not errors and stages:
        actual = [s["stage"] for s in stages]
        expected = list(_STAGE_ORDER[: len(stages)])
        # حدُّ صدقٍ مقيس: هذا الفرعُ **لا يُبلَغ بأيّ مُدخَل** اليوم، ولا يُسجَّل
        # له تكذيبٌ لذلك. البرهانُ بالجداء الكامل — ٩ مراحل × ٩ مواضع = ٨١
        # مِسباراً، **صفرُ موضعٍ حرّ**: المخطَّطُ يُثبِّت (المرحلة ⇄ التسلسل)،
        # و`_verify_common` يفرض تتابعاً `0..n-1`. فالمرحلةُ في الموضع i هي
        # `_STAGE_ORDER[i]` لزوماً، و`actual != expected` مستحيلة.
        # يبقى دفاعاً في العمق: إن ارتخى المخطَّطُ يوماً عن تثبيت الاقتران عاد
        # هذا السطرُ حيّاً — فحذفُه اليوم يفتح ثغرةً غداً بلا أن يُبلِّغ.
        if actual != expected:  # pragma: no cover — مُبرهَنٌ أنّه غير قابل للبلوغ
            errors.append(f"prefix mismatch: expected {expected}, got {actual}")
    return _result(stages, errors, complete=False)


def _verify_common(stages: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not stages:
        return ["chain is empty"]

    chain_ids = {s.get("chain_id") for s in stages}
    correlation_ids = {s.get("correlation_id") for s in stages}
    if len(chain_ids) != 1:
        errors.append("all stages must share one chain_id")
    if len(correlation_ids) != 1:
        errors.append("all stages must share one correlation_id")

    seen_ids: set[str] = set()
    for idx, stage in enumerate(stages):
        errors.extend(f"stage[{idx}]: {e}" for e in validate_stage_schema(stage))
        if stage.get("stage_id") in seen_ids:
            errors.append(f"duplicate stage_id: {stage.get('stage_id')}")
        seen_ids.add(stage.get("stage_id"))

        if stage.get("canonicalization_version") != CANONICALIZATION_VERSION:
            errors.append(
                f"stage[{idx}]: unsupported canonicalization_version "
                f"{stage.get('canonicalization_version')!r}"
            )
        if stage.get("stage_digest") and stage_digest(stage) != stage.get("stage_digest"):
            errors.append(f"stage[{idx}]: stage_digest mismatch")

        if stage.get("sequence") != idx:
            errors.append(
                f"stage[{idx}]: sequence must be contiguous starting at 0; "
                f"got {stage.get('sequence')}"
            )

        if idx == 0:
            if stage.get("stage") != "CanonicalState":
                errors.append("sequence 0 must be CanonicalState")
            if stage.get("parent_stage_id") is not None or stage.get("parent_digest") is not None:
                errors.append("CanonicalState must have null parent_stage_id and parent_digest")
        else:
            previous = stages[idx - 1]
            if stage.get("parent_stage_id") != previous.get("stage_id"):
                errors.append(f"stage[{idx}]: parent_stage_id does not point to previous stage")
            if stage.get("parent_digest") != previous.get("stage_digest"):
                errors.append(f"stage[{idx}]: parent_digest does not match previous stage_digest")

    # Cross-stage causal identifiers.
    by_stage = {s.get("stage"): s for s in stages}
    prediction = by_stage.get("Prediction")
    decision = by_stage.get("DecisionCandidate")
    execution = by_stage.get("Execution")
    if prediction and decision and decision.get("prediction_id") != prediction.get("prediction_id"):
        errors.append("DecisionCandidate.prediction_id does not match Prediction.prediction_id")
    if prediction and prediction.get("input_digest") != by_stage.get("CanonicalState", {}).get(
        "state_digest"
    ):
        errors.append("Prediction.input_digest must equal CanonicalState.state_digest")
    if decision:
        decision_id = decision.get("decision_id")
        for name in _STAGE_ORDER[3:]:
            item = by_stage.get(name)
            if item and item.get("decision_id") != decision_id:
                errors.append(f"{name}.decision_id does not match DecisionCandidate.decision_id")
    if execution:
        execution_id = execution.get("execution_id")
        for name in _STAGE_ORDER[5:8]:
            item = by_stage.get(name)
            if item and item.get("execution_id") != execution_id:
                errors.append(f"{name}.execution_id does not match Execution.execution_id")

    return errors


def _result(stages: list[dict[str, Any]], errors: list[str], *, complete: bool) -> dict[str, Any]:
    return {
        "status": "VERIFIED" if not errors else "REJECTED",
        "complete": complete,
        "chain_id": stages[0].get("chain_id") if stages else None,
        "correlation_id": stages[0].get("correlation_id") if stages else None,
        "stage_count": len(stages),
        "last_stage": stages[-1].get("stage") if stages else None,
        "errors": errors,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "digest_algorithm": "sha256",
        "contract_revision": CONTRACT_REVISION,
        "schema": SCHEMA_VERSION,
    }
