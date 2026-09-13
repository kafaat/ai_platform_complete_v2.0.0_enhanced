"""Prepare authorised customer-practice exports for offline analyst review.

Reuses the existing offline feature manifest; creates no store, model or grant.
The caller supplies a current consent-ledger export and chooses the time boundary
and held-out customers before comparing results. This local helper verifies the
export's content, not the identity or authenticity of its producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.feature_store.runtime import write_offline_feature_dataset

REVIEW_VERSION = "customer_practice_review.v1"
COHORT_FIELDS = ("region", "crop", "language", "season_id")


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timezone-aware timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def review_practice_dataset(
    records: list[dict[str, Any]],
    *,
    tenant_id: str,
    consents: dict[str, dict[str, Any]],
    as_of: str,
    split_at: str,
    held_out_customers: list[str],
    feature_names: list[str],
    feature_units: dict[str, str],
    label_name: str,
    label_unit: str,
) -> dict[str, Any]:
    """Return train/evaluation candidates, exclusions and descriptive coverage.

    One operation is one case, regardless of repeated export rows. Labels need a
    recorded observation and elapsed maturity window. Both feature event time and
    availability must precede the decision. Training labels must have been known
    and mature at split_at. No sample count grants local agronomic validity.
    """
    if not _identifier(tenant_id) or not _identifier(label_name):
        raise ValueError("tenant_id and label_name required")
    if not feature_names or not all(_identifier(x) for x in feature_names):
        raise ValueError("explicit feature_names required")
    if len(set(feature_names)) != len(feature_names):
        raise ValueError("duplicate feature name")
    if not _identifier(label_unit) or any(
        not _identifier(feature_units.get(key)) for key in feature_names
    ):
        raise ValueError("explicit feature and label units required")
    now, split = _time(as_of), _time(split_at)
    if split >= now:
        raise ValueError("split_at must precede as_of")
    if not held_out_customers or not all(_identifier(x) for x in held_out_customers):
        raise ValueError("preselected held_out_customers required")
    held_out = set(held_out_customers)
    unique: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for row in records:
        if not isinstance(row, dict) or row.get("tenant_id") != tenant_id:
            raise PermissionError("practice export tenant mismatch")
        operation_id = row.get("operation_id")
        if not _identifier(operation_id):
            raise ValueError("operation_id required for deduplication")
        # Reject non-JSON numeric values even when present in an unused feature.
        fingerprint = _digest(row)
        if operation_id in unique:
            if _digest(unique[operation_id]) != fingerprint:
                raise ValueError("conflicting operation revisions: select the accepted revision")
            duplicates += 1
        else:
            unique[operation_id] = row
    holdout_fields = {
        row.get("field_id") for row in unique.values() if row.get("customer_id") in held_out
    }
    partitions: dict[str, list[dict[str, Any]]] = {"train": [], "evaluation": []}
    excluded: list[dict[str, Any]] = []
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for operation_id, row in sorted(unique.items()):
        reasons: list[str] = []
        for key in ("customer_id", "field_id", "season_id", "source_record_id", *COHORT_FIELDS):
            if not _identifier(row.get(key)):
                reasons.append("missing_" + key)
        features = row.get("features")
        if not isinstance(features, dict) or any(
            features.get(key) is None for key in feature_names
        ):
            reasons.append("missing_selected_feature")
        units = row.get("feature_units")
        if not isinstance(units, dict) or any(
            units.get(key) != feature_units[key] for key in feature_names
        ):
            reasons.append("feature_unit_mismatch")
        if row.get("label_unit") != label_unit:
            reasons.append("label_unit_mismatch")
        labels = row.get("labels")
        value = labels.get(label_name) if isinstance(labels, dict) else None
        if value is None:
            reasons.append("missing_outcome")
        elif (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            reasons.append("invalid_numeric_outcome")
        stamps: dict[str, datetime] = {}
        for key in (
            "event_time",
            "feature_available_at",
            "decision_at",
            "outcome_at",
            "outcome_recorded_at",
            "matures_at",
        ):
            try:
                stamps[key] = _time(row.get(key))
            except (ValueError, OverflowError):
                reasons.append("invalid_" + key)
        if len(stamps) == 6:
            if not stamps["event_time"] <= stamps["feature_available_at"] <= stamps["decision_at"]:
                reasons.append("feature_not_available_at_decision")
            if (
                not stamps["decision_at"]
                <= stamps["outcome_at"]
                <= stamps["outcome_recorded_at"]
                <= now
            ):
                reasons.append("invalid_outcome_timeline")
            if stamps["matures_at"] < stamps["decision_at"] or stamps["matures_at"] > now:
                reasons.append("outcome_not_mature")
            if stamps["outcome_at"] < stamps["matures_at"]:
                reasons.append("outcome_measured_before_maturity")
        customer = row.get("customer_id")
        consent = consents.get(customer, {}) if isinstance(customer, str) else {}
        try:
            consent_valid = (
                consent.get("tenant_id") == tenant_id
                and consent.get("purpose") == "shared_learning"
                and consent.get("status") == "active"
                and _identifier(consent.get("source_record_id"))
                and _time(consent.get("granted_at")) <= now < _time(consent.get("valid_until"))
            )
        except (ValueError, AttributeError, OverflowError):
            consent_valid = False
        if not consent_valid:
            reasons.append("missing_or_inactive_learning_consent")
        partition = "evaluation" if customer in held_out else "train"
        if len(stamps) == 6:
            if partition == "evaluation" and stamps["decision_at"] <= split:
                reasons.append("held_out_case_before_split")
            if partition == "train" and (
                stamps["decision_at"] > split
                or stamps["outcome_recorded_at"] > split
                or stamps["matures_at"] > split
            ):
                reasons.append("training_case_not_known_at_split")
        if partition == "train" and row.get("field_id") in holdout_fields:
            reasons.append("held_out_field")
        if reasons:
            excluded.append({"operation_id": operation_id, "reasons": sorted(set(reasons))})
        else:
            partitions[partition].append(
                {
                    "feature_id": operation_id,
                    "entity_type": "field",
                    "entity_id": row["field_id"],
                    "event_time": row["event_time"],
                    "features": {key: features[key] for key in feature_names},
                    "labels": {label_name: value},
                    "quality": {
                        "tenant_id": tenant_id,
                        "customer_id": customer,
                        "season_id": row["season_id"],
                        "source_record_id": row["source_record_id"],
                        "consent_record_id": consent["source_record_id"],
                        "source_record_sha256": _digest(row),
                        "review_version": REVIEW_VERSION,
                        "feature_units": {key: feature_units[key] for key in feature_names},
                        "label_unit": label_unit,
                    },
                }
            )
        cohort = tuple(
            row.get(key) if _identifier(row.get(key)) else "unknown" for key in COHORT_FIELDS
        )
        group = groups.setdefault(
            cohort,
            {
                "cases": 0,
                "customers": set(),
                "fields": set(),
                "labels": Counter(),
                "excluded_cases": 0,
            },
        )
        group["cases"] += 1
        if _identifier(customer):
            group["customers"].add(customer)
        if _identifier(row.get("field_id")):
            group["fields"].add(row["field_id"])
        # Keep loss/non-response visible. These are source reports, not efficacy.
        reported = row.get("reported_result")
        if reported not in {"improved", "unchanged", "worse", "unresolved", "no_response"}:
            reported = "unknown"
        group["labels"][reported] += 1
        group["excluded_cases"] += bool(reasons)
    cohorts = [
        {
            **dict(zip(COHORT_FIELDS, key, strict=True)),
            "cases": group["cases"],
            "customers": len(group["customers"]),
            "fields": len(group["fields"]),
            "reported_results": dict(sorted(group["labels"].items())),
            "excluded_cases": group["excluded_cases"],
        }
        for key, group in sorted(groups.items())
    ]
    policy = {
        "version": REVIEW_VERSION,
        "tenant_id": tenant_id,
        "as_of": as_of,
        "split_at": split_at,
        "held_out_customers": sorted(held_out),
        "feature_names": feature_names,
        "feature_units": {key: feature_units[key] for key in feature_names},
        "label_name": label_name,
        "label_unit": label_unit,
    }
    feature_set_id = (
        "practice_"
        + _digest([tenant_id, feature_names, feature_units, label_name, label_unit])[:16]
    )
    manifests = {
        name: write_offline_feature_dataset(
            rows, feature_set_id=feature_set_id, dataset_name="customer_practice_" + name
        )
        for name, rows in partitions.items()
    }
    blocked = ["empty_" + name for name, rows in partitions.items() if not rows]
    return {
        "policy": policy,
        "policy_sha256": _digest(policy),
        "source_sha256": _digest(list(unique.values())),
        "consents_sha256": _digest(consents),
        "status": "blocked" if blocked else "prepared_for_review",
        "blocked_reasons": blocked,
        "input_rows": len(records),
        "unique_cases": len(unique),
        "duplicates": duplicates,
        "partitions": partitions,
        "manifests": manifests,
        "excluded": excluded,
        "cohorts": cohorts,
        "training_started": False,
        "model_promotion_allowed": False,
        "agronomic_validation": "not_established",
        "causal_effect": "not_estimated",
        "persisted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="records, consents and policy JSON"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.input.read_text(encoding="utf-8"))
    result = review_practice_dataset(
        request["records"], consents=request["consents"], **request["policy"]
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
