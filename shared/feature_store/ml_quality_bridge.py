"""Read-only SAHOOL -> Unified Local Lab ML screening candidate adapter.

There is no database access, model invocation, real-sensor attestation, promotion,
water-ledger write, actuator action or authorization in this module. Only a
trusted, separately supplied receipt-verifier callback may elevate the *source
classification* of one row; even then the resulting output is a candidate,
not a proven physical measurement or a passed scientific screen.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

CONTRACT_VERSION = "ml-quality/v1"
ADAPTER_VERSION = "sahool-ml-export/v1"
MAX_RECORDS = 100_000
MAX_DEPTH_MM = 10_000
MAX_TEXT = 200
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_SOURCES = {
    "soil_sensor": "soil_sensor_verified",
    "field_measurement": "field_measurement_verified",
}
RECORD_FIELDS = frozenset(
    {
        "case_id",
        "tenant_id",
        "field_id",
        "season_id",
        "split",
        "prediction_at",
        "feature_event_at",
        "feature_available_at",
        "label_measured_at",
        "label_available_at",
        "measurement_origin",
        "measurement_receipt_sha256",
        "target_mm",
        "prediction_mm",
        "baseline_mm",
    }
)
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "dataset_id",
        "tenant_id",
        "model_id",
        "model_artifact_sha256",
        "source_bundle_sha256",
        "evaluation_policy",
        "dataset_freeze_at",
    }
)
# The callback MUST be supplied by a trusted SAHOOL owner, not from a request payload.
ReceiptVerifier = Callable[[str, str, str, str, str, str, str, float], bool]


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _stamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("TIMESTAMP_INVALID")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("TIMESTAMP_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_TIMEZONE_REQUIRED")
    return dt


def _text(value: Any) -> bool:
    return type(value) is str and 0 < len(value) <= MAX_TEXT and value.strip() == value


def _bounded_depth(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return False
    return math.isfinite(number) and 0 <= number <= MAX_DEPTH_MM


def _bounded_fraction(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return False
    return math.isfinite(number) and 0 <= number < 1


def _is_sha(value: Any) -> bool:
    return type(value) is str and HASH_RE.fullmatch(value) is not None


def export_ml_quality_candidate(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    receipt_verifier: ReceiptVerifier | None = None,
) -> dict[str, Any]:
    """Prepare input of the Lab's `assess_irrigation_regression` without side effects.

    Source strings in the returned rows are **still claims**. All audit/proof of
    real data must be separately established by authoritative writers and a
    verifier that cross-checks receipt bytes, tenant, field, season and origin.
    Missing verifier => BLOCKED, with no usable accepted source declaration.
    """
    if type(manifest) is not dict or set(manifest) != MANIFEST_FIELDS:
        raise ValueError("MANIFEST_INVALID")
    if manifest["schema_version"] != CONTRACT_VERSION:
        raise ValueError("CONTRACT_VERSION_UNSUPPORTED")
    if not all(_text(manifest[k]) for k in ("dataset_id", "tenant_id", "model_id")):
        raise ValueError("MANIFEST_IDENTITY_INVALID")
    if not all(_is_sha(manifest[k]) for k in ("model_artifact_sha256", "source_bundle_sha256")):
        raise ValueError("MANIFEST_DIGEST_INVALID")
    if type(manifest["evaluation_policy"]) is not dict or set(manifest["evaluation_policy"]) != {
        "min_independent_groups_per_split",
        "min_relative_mae_improvement",
        "temporal_embargo_hours",
    }:
        raise ValueError("MANIFEST_POLICY_INVALID")
    policy = manifest["evaluation_policy"]
    if (
        type(policy["min_independent_groups_per_split"]) is not int
        or not 1 <= policy["min_independent_groups_per_split"] <= 1000
        or type(policy["temporal_embargo_hours"]) is not int
        or not 0 <= policy["temporal_embargo_hours"] <= 24 * 365
        or not _bounded_fraction(policy["min_relative_mae_improvement"])
    ):
        raise ValueError("MANIFEST_POLICY_INVALID")
    freeze = _stamp(manifest["dataset_freeze_at"])
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise ValueError("RECORDS_INVALID_OR_TOO_MANY")
    if receipt_verifier is not None and not callable(receipt_verifier):
        raise ValueError("RECEIPT_VERIFIER_INVALID")
    result_rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    receipt_sha256s: set[str] = set()
    seen_receipts: set[str] = set()
    ids: set[str] = set()
    for i, record in enumerate(records):
        prefix = f"row_{i}"
        if type(record) is not dict or set(record) != RECORD_FIELDS:
            reasons.append(prefix + ":RECORD_SCHEMA_INVALID")
            continue
        cid = record["case_id"]
        if not _text(cid) or cid in ids:
            reasons.append(prefix + ":CASE_ID_INVALID_OR_DUPLICATE")
            continue
        ids.add(cid)
        if not all(_text(record[k]) for k in ("tenant_id", "field_id", "season_id")):
            reasons.append(cid + ":FIELD_SCOPE_INVALID")
            continue
        if record["tenant_id"] != manifest["tenant_id"]:
            reasons.append(cid + ":TENANT_SCOPE_MISMATCH")
            continue
        if type(record["split"]) is not str or record["split"] not in {
            "train",
            "validation",
            "test",
        }:
            reasons.append(cid + ":SPLIT_INVALID")
            continue
        try:
            prediction = _stamp(record["prediction_at"])
            event = _stamp(record["feature_event_at"])
            available = _stamp(record["feature_available_at"])
            label_measured = _stamp(record["label_measured_at"])
            label_available = _stamp(record["label_available_at"])
        except ValueError:
            reasons.append(cid + ":TIMESTAMP_INVALID")
            continue
        if event > available or available > prediction or event > prediction:
            reasons.append(cid + ":FUTURE_OR_LATE_FEATURE")
            continue
        if (
            label_measured <= prediction
            or label_available < label_measured
            or label_available > freeze
        ):
            reasons.append(cid + ":LABEL_MATURITY_INVALID")
            continue
        if not all(
            _bounded_depth(record[k]) for k in ("target_mm", "prediction_mm", "baseline_mm")
        ):
            reasons.append(cid + ":DEPTH_INVALID")
            continue
        source = record["measurement_origin"]
        accepted_source = "unverified_claim"
        if type(source) is not str or source not in ALLOWED_SOURCES:
            reasons.append(cid + ":NOT_INDEPENDENT_MEASUREMENT")
        else:
            receipt = record["measurement_receipt_sha256"]
            if not _is_sha(receipt):
                reasons.append(cid + ":MEASUREMENT_RECEIPT_INVALID")
            elif receipt in seen_receipts:
                reasons.append(cid + ":MEASUREMENT_RECEIPT_REUSED")
            else:
                # Exactly one evaluation row per receipt, even when verification fails.
                seen_receipts.add(receipt)
                if receipt_verifier is None:
                    reasons.append(cid + ":MEASUREMENT_VERIFIER_NOT_CONFIGURED")
                else:
                    try:
                        verified = (
                            receipt_verifier(
                                record["tenant_id"],
                                record["field_id"],
                                record["season_id"],
                                source,
                                receipt,
                                cid,
                                label_measured.isoformat(),
                                float(record["target_mm"]),
                            )
                            is True
                        )
                    except Exception:  # noqa: BLE001 - unknown verifier failures never confer trust
                        verified = False
                    if not verified:
                        reasons.append(cid + ":MEASUREMENT_VERIFICATION_FAILED")
                    else:
                        accepted_source = ALLOWED_SOURCES[source]
                        receipt_sha256s.add(receipt)
        result_rows.append(
            {
                key: record[key]
                for key in (
                    "case_id",
                    "tenant_id",
                    "field_id",
                    "season_id",
                    "split",
                    "prediction_at",
                    "feature_event_at",
                    "feature_available_at",
                    "label_measured_at",
                    "label_available_at",
                    "target_mm",
                    "prediction_mm",
                    "baseline_mm",
                )
            }
            | {"label_source": accepted_source}
        )
    if not records:
        reasons.append("EMPTY_DATASET")
    return {
        "schema_version": ADAPTER_VERSION,
        "status": "BLOCKED" if reasons else "CANDIDATE_NOT_EVALUATED",
        "blocking_reasons": sorted(set(reasons)),
        "manifest": json.loads(json.dumps(manifest, allow_nan=False)),
        "rows": result_rows,
        "row_count": len(result_rows),
        "input_count": len(records),
        "candidate_manifest_sha256": _hash(manifest),
        "candidate_rows_sha256": _hash(result_rows),
        "claimed_verified_receipt_sha256s": sorted(receipt_sha256s),
        "claims": {
            "data_source_authenticated_by_adapter": False,
            "verifier_callback_provided": receipt_verifier is not None,
            "scientific_screen_executed": False,
            "production_authorized": False,
            "model_inference_executed": False,
            "water_ledger_modified": False,
            "actuator_authorized": False,
        },
    }
