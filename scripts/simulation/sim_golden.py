#!/usr/bin/env python3
"""SIM-GOLDEN-01: temporal yield diagnostics and policy-bound signed evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ALLOWED_SOURCES = {"combine_weighbridge", "certified_scale", "erp_verified"}
DEFAULT_THRESHOLDS = {
    "max_mape_pct": 20.0,
    "max_nrmse_pct": 25.0,
    "max_abs_bias_pct": 10.0,
    "min_r2": 0.50,
    "min_samples": 30,
    "min_farms": 3,
    "min_seasons": 2,
}
REQUIRED = {
    "sample_id",
    "crop",
    "season_id",
    "farm_id",
    "observed_yield_kg_ha",
    "predicted_yield_kg_ha",
    "observation_source",
    "harvest_at",
    "prediction_at",
    "model_version",
    "input_digest",
}
POLICY_REQUIRED = {
    "schema_version",
    "policy_id",
    "candidate_model_version",
    "registered_at",
    "crops",
}
HOLDOUT_REQUIRED = {"holdout_season_id", "min_holdout_samples", "min_holdout_farms"}


class GoldenError(ValueError):
    pass


def canonical(value: object) -> bytes:
    """Canonical UTF-8 JSON for digests/signatures, excluding NaN and Infinity."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GoldenError(f"{label} must be a nonblank string without surrounding whitespace")
    return value


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(_text(value, "timestamp").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise GoldenError("timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value.lower())
    )


def _fields(value: object, required: set[str], optional: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise GoldenError(f"{label} must be an object")
    unknown = value.keys() - required - optional
    if unknown:
        raise GoldenError(f"unknown {label} fields: " + ", ".join(sorted(map(str, unknown))))
    missing = required - value.keys()
    if missing:
        raise GoldenError(f"{label} missing required fields: " + ", ".join(sorted(missing)))


def _count(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise GoldenError(f"{label} must be a positive integer")
    return value


def _number(value: object, label: str) -> float:
    try:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise GoldenError(f"{label} must be a finite number")
        return float(value)
    except OverflowError as exc:
        raise GoldenError(f"{label} must be a finite number") from exc


def _thresholds(overrides: object) -> dict:
    _fields(overrides, set(), set(DEFAULT_THRESHOLDS), "thresholds")
    values = {**DEFAULT_THRESHOLDS, **overrides}
    for key, value in values.items():
        if key.startswith("min_") and key != "min_r2":
            _count(value, key)
        else:
            numeric = _number(value, key)
            if key == "min_r2":
                if numeric > 1:
                    raise GoldenError("min_r2 must not exceed 1")
            elif numeric < 0:
                raise GoldenError(f"{key} must be nonnegative")
    if values["min_farms"] > values["min_samples"]:
        raise GoldenError("min_farms must not exceed min_samples")
    return values


def _not_future(value: str, label: str, now: datetime) -> datetime:
    """A timestamp later than the evaluation instant is not an observation yet."""
    parsed = _time(value)
    if parsed > now:
        raise GoldenError(f"{label} is later than the evaluation time; future evidence is refused")
    return parsed


def _validate(rows: list[dict], now: datetime) -> str:
    if not rows:
        raise GoldenError("golden dataset is empty")
    seen: set[str] = set()
    models: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise GoldenError("dataset rows must be objects")
        missing = REQUIRED - row.keys()
        if missing:
            raise GoldenError("dataset row missing required fields: " + ", ".join(sorted(missing)))
        for field in (
            "sample_id",
            "crop",
            "season_id",
            "farm_id",
            "model_version",
            "observation_source",
        ):
            _text(row[field], field)
        sample_id = row["sample_id"]
        if sample_id in seen:
            raise GoldenError("duplicate sample_id")
        seen.add(sample_id)
        models.add(row["model_version"])
        if row["observation_source"] not in ALLOWED_SOURCES:
            raise GoldenError("unverified harvest observation source")
        observed = _number(row["observed_yield_kg_ha"], "observed_yield_kg_ha")
        predicted = _number(row["predicted_yield_kg_ha"], "predicted_yield_kg_ha")
        if observed <= 0 or predicted < 0:
            raise GoldenError("observed yield must be positive and predicted yield nonnegative")
        prediction_at = _not_future(row["prediction_at"], "prediction_at", now)
        if prediction_at >= _not_future(row["harvest_at"], "harvest_at", now):
            raise GoldenError("prediction must be created strictly before harvest (target leakage)")
        if not _is_sha256(row["input_digest"]):
            raise GoldenError("input_digest must be sha256 hex")
        if "tenant_id" in row:
            raise GoldenError(
                "raw tenant_id is forbidden in portable golden datasets; use farm_id pseudonyms"
            )
    if len(models) != 1:
        raise GoldenError(
            "a single model_version is required; mixed model versions cannot be pooled"
        )
    return models.pop()


def _validate_policy(
    policy: dict, crops: set[str], candidate: str, now: datetime | None = None
) -> dict:
    _fields(policy, POLICY_REQUIRED, {"thresholds"}, "policy")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise GoldenError("policy.schema_version must be 1")
    _text(policy["policy_id"], "policy_id")
    if _text(policy["candidate_model_version"], "candidate_model_version") != candidate:
        raise GoldenError("policy candidate_model_version does not match the dataset candidate")
    if now is None:
        _time(policy["registered_at"])
    else:
        _not_future(policy["registered_at"], "policy.registered_at", now)
    rules = policy["crops"]
    if not isinstance(rules, dict) or set(rules) != crops:
        raise GoldenError("policy crops must exactly cover the canonical lowercase dataset crops")
    for crop, rule in rules.items():
        _fields(rule, HOLDOUT_REQUIRED, set(), f"holdout policy for {crop}")
        _text(rule["holdout_season_id"], "holdout_season_id")
        samples = _count(rule["min_holdout_samples"], "min_holdout_samples")
        farms = _count(rule["min_holdout_farms"], "min_holdout_farms")
        if farms > samples:
            raise GoldenError("min_holdout_farms must not exceed min_holdout_samples")
    return _thresholds(policy.get("thresholds", {}))


def _season_order(rows: list[dict]) -> list[tuple[str, datetime, datetime]]:
    harvests: dict[str, list[datetime]] = defaultdict(list)
    for row in rows:
        harvests[row["season_id"]].append(_time(row["harvest_at"]))
    intervals = sorted(
        ((season, min(times), max(times)) for season, times in harvests.items()),
        key=lambda item: item[1],
    )
    for earlier, later in zip(intervals, intervals[1:], strict=False):
        if earlier[2] >= later[1]:
            raise GoldenError("ambiguous season chronology: harvest intervals overlap or touch")
    return intervals


def _metrics(rows: list[dict]) -> dict[str, float | None]:
    observed = [float(row["observed_yield_kg_ha"]) for row in rows]
    predicted = [float(row["predicted_yield_kg_ha"]) for row in rows]
    try:
        residuals = [p - o for p, o in zip(predicted, observed, strict=True)]
        mean_observed = statistics.fmean(observed)
        mae = statistics.fmean(abs(v) for v in residuals)
        rmse = math.sqrt(statistics.fmean(v * v for v in residuals))
        mape = statistics.fmean(abs(v) / o for v, o in zip(residuals, observed, strict=True)) * 100
        bias_pct = statistics.fmean(residuals) / mean_observed * 100
        denominator = sum((o - mean_observed) ** 2 for o in observed)
        r2 = 1 - sum(v * v for v in residuals) / denominator if denominator > 0 else None
        values = {
            "mae_kg_ha": mae,
            "rmse_kg_ha": rmse,
            "nrmse_pct": rmse / mean_observed * 100,
            "mape_pct": mape,
            "bias_pct": bias_pct,
            "r2": r2,
        }
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        raise GoldenError("yield magnitudes do not produce finite metrics") from exc
    if any(value is not None and not math.isfinite(value) for value in values.values()):
        raise GoldenError("yield magnitudes do not produce finite metrics")
    return {key: round(value, 6) if value is not None else None for key, value in values.items()}


def _crop_checks(result: dict, thresholds: dict, policy: dict | None) -> dict[str, bool]:
    """Use the same criteria when producing and checking a signed crop report."""
    metrics = result["metrics"]
    checks = {
        "sample_count": result["samples"] >= thresholds["min_samples"],
        "farm_diversity": result["farms"] >= thresholds["min_farms"],
        "season_diversity": result["seasons"] >= thresholds["min_seasons"],
        "temporal_holdout_nonempty": result["holdout_samples"] > 0 and result["seasons"] >= 2,
        "mape": metrics["mape_pct"] <= thresholds["max_mape_pct"],
        "nrmse": metrics["nrmse_pct"] <= thresholds["max_nrmse_pct"],
        "bias": abs(metrics["bias_pct"]) <= thresholds["max_abs_bias_pct"],
        "r2": metrics["r2"] is not None and metrics["r2"] >= thresholds["min_r2"],
    }
    if policy is not None:
        rule = policy["crops"][result["crop"]]
        checks.update(
            {
                "declared_holdout_matches": result["holdout_season"] == rule["holdout_season_id"],
                "holdout_sample_count": result["holdout_samples"] >= rule["min_holdout_samples"],
                "holdout_farm_diversity": result["holdout_farms"] >= rule["min_holdout_farms"],
                "policy_registered_before_prediction": _time(policy["registered_at"])
                < _time(result["holdout_first_prediction_at_utc"]),
            }
        )
    return checks


def _consistent_crop_result(result: dict, thresholds: dict, policy: dict) -> bool:
    """Reject signed reports whose own counts, time ranges or checks contradict their policy."""
    for field in ("samples", "farms", "seasons", "holdout_samples", "holdout_farms"):
        _count(result[field], field)
    if (
        result["farms"] > result["samples"]
        or result["holdout_samples"] > result["samples"] - (result["seasons"] - 1)
        or result["holdout_farms"] > min(result["farms"], result["holdout_samples"])
    ):
        return False
    ranges = result["season_harvest_ranges"]
    if not isinstance(ranges, list) or len(ranges) != result["seasons"]:
        return False
    seen = set()
    previous_end = None
    for interval in ranges:
        _fields(interval, {"season_id", "start_utc", "end_utc"}, set(), "season range")
        season = _text(interval["season_id"], "season_id")
        start, end = _time(interval["start_utc"]), _time(interval["end_utc"])
        if season in seen or start > end or (previous_end is not None and previous_end >= start):
            return False
        seen.add(season)
        previous_end = end
    latest = ranges[-1]
    if (
        result["holdout_season"] != latest["season_id"]
        or _time(result["holdout_harvest_start_utc"]) != _time(latest["start_utc"])
        or _time(result["holdout_harvest_end_utc"]) != _time(latest["end_utc"])
        or _time(result["holdout_first_prediction_at_utc"]) >= _time(latest["start_utc"])
    ):
        return False
    metrics = result["metrics"]
    _fields(
        metrics,
        {"mae_kg_ha", "rmse_kg_ha", "nrmse_pct", "mape_pct", "bias_pct", "r2"},
        set(),
        "metrics",
    )
    for name, value in metrics.items():
        if name == "r2" and value is None:
            continue
        numeric = _number(value, name)
        if (name not in {"bias_pct", "r2"} and numeric < 0) or (name == "r2" and numeric > 1):
            return False
    checks = _crop_checks(result, thresholds, policy)
    reported = result["checks"]
    return (
        isinstance(reported, dict)
        and reported == checks
        and all(type(value) is bool for value in reported.values())
        and all(checks.values())
        and result.get("passed") is True
    )


def evaluate(
    dataset: dict,
    *,
    signing_key: str = "",
    validation_policy: dict | None = None,
    expected_policy_sha256: str = "",
    now: datetime | None = None,
) -> dict:
    """Evaluate one candidate; promotion additionally requires an externally pinned policy."""
    rows = dataset.get("samples") if isinstance(dataset, dict) else None
    if not isinstance(rows, list):
        raise GoldenError("dataset.samples must be a list")
    evaluated_at = (now or datetime.now(UTC)).astimezone(UTC)
    candidate = _validate(rows, evaluated_at)
    if not isinstance(signing_key, str):
        raise GoldenError("signing_key must be a string")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["crop"].lower()].append(row)
    policy_digest = None
    policy_pinned = False
    if validation_policy is None:
        if expected_policy_sha256:
            raise GoldenError("a policy pin requires a separate validation policy")
        thresholds = _thresholds(dataset.get("thresholds", {}))
    else:
        thresholds = _validate_policy(validation_policy, set(grouped), candidate, evaluated_at)
        if "thresholds" in dataset:
            raise GoldenError("dataset thresholds cannot override a separate validation policy")
        # Snapshot the validated policy so later caller mutation cannot alter signed evidence.
        validation_policy = json.loads(canonical(validation_policy))
        policy_digest = hashlib.sha256(canonical(validation_policy)).hexdigest()
        if expected_policy_sha256:
            if not _is_sha256(expected_policy_sha256):
                raise GoldenError("expected policy pin must be sha256 hex")
            if not hmac.compare_digest(policy_digest, expected_policy_sha256.lower()):
                raise GoldenError("policy digest does not match the trusted policy pin")
            policy_pinned = True
    crop_results = []
    for crop, crop_rows in sorted(grouped.items()):
        farms = {r["farm_id"] for r in crop_rows}
        seasons = _season_order(crop_rows)
        latest, harvest_start, harvest_end = seasons[-1]
        holdout = [r for r in crop_rows if r["season_id"] == latest]
        holdout_farms = {r["farm_id"] for r in holdout}
        first_prediction = min(_time(r["prediction_at"]) for r in holdout)
        metrics = _metrics(holdout)
        result = {
            "crop": crop,
            "samples": len(crop_rows),
            "farms": len(farms),
            "seasons": len(seasons),
            "holdout_season": latest,
            "holdout_samples": len(holdout),
            "holdout_farms": len(holdout_farms),
            "holdout_harvest_start_utc": harvest_start.isoformat(),
            "holdout_harvest_end_utc": harvest_end.isoformat(),
            "holdout_first_prediction_at_utc": first_prediction.isoformat(),
            "season_harvest_ranges": [
                {
                    "season_id": season,
                    "start_utc": start.isoformat(),
                    "end_utc": end.isoformat(),
                }
                for season, start, end in seasons
            ],
            "metrics": metrics,
        }
        result["checks"] = _crop_checks(result, thresholds, validation_policy)
        result["passed"] = all(result["checks"].values())
        crop_results.append(result)
    passed = bool(crop_results) and all(row["passed"] for row in crop_results)
    signed = len(signing_key) >= 32
    evidence = {
        "schema_version": 2,
        "evidence_type": "sim_golden_01",
        "generated_at_utc": evaluated_at.isoformat(),
        "dataset_sha256": hashlib.sha256(canonical(dataset)).hexdigest(),
        "candidate_model_version": candidate,
        "model_versions": [candidate],
        "validation_policy": validation_policy,
        "policy_sha256": policy_digest,
        "policy_status": "pinned"
        if policy_pinned
        else "missing"
        if validation_policy is None
        else "unpinned",
        "thresholds": thresholds,
        "crops": crop_results,
        "criteria_passed": passed,
        "status": ("verified" if policy_pinned else "diagnostic") if passed else "rejected",
        "eligible_for_promotion": passed and policy_pinned and signed,
        "signature_status": "signed" if signed else "missing",
    }
    if signed:
        evidence["signature_hmac_sha256"] = hmac.new(
            signing_key.encode(), canonical(evidence), hashlib.sha256
        ).hexdigest()
    return evidence


def verify_signed_evidence(
    evidence: dict,
    signing_key: str,
    *,
    expected_model_version: str | None = None,
    expected_policy_sha256: str | None = None,
    expected_dataset_sha256: str | None = None,
) -> bool:
    """Admit schema-2 evidence only for an externally expected candidate and policy.

    ``dataset_sha256`` is signed, so it cannot be altered after signing; but the signer chooses
    which dataset to evaluate. When the admitting party knows which dataset it expects, pass
    ``expected_dataset_sha256`` and evidence for any other dataset is refused.
    """
    if expected_dataset_sha256 is not None and not _is_sha256(expected_dataset_sha256):
        return False
    if (
        not isinstance(evidence, dict)
        or not isinstance(signing_key, str)
        or len(signing_key) < 32
        or not isinstance(expected_model_version, str)
        or not expected_model_version.strip()
        or not _is_sha256(expected_policy_sha256)
    ):
        return False
    if (
        type(evidence.get("schema_version")) is not int
        or evidence["schema_version"] != 2
        or evidence.get("evidence_type") != "sim_golden_01"
        or evidence.get("signature_status") != "signed"
        or evidence.get("eligible_for_promotion") is not True
        or evidence.get("criteria_passed") is not True
        or evidence.get("status") != "verified"
        or evidence.get("policy_status") != "pinned"
        or evidence.get("candidate_model_version") != expected_model_version
        or evidence.get("model_versions") != [expected_model_version]
        or evidence.get("policy_sha256") != expected_policy_sha256.lower()
        or not _is_sha256(evidence.get("dataset_sha256"))
        or (
            expected_dataset_sha256 is not None
            and evidence.get("dataset_sha256") != expected_dataset_sha256.lower()
        )
    ):
        return False
    presented = evidence.get("signature_hmac_sha256")
    if not _is_sha256(presented):
        return False
    unsigned = dict(evidence)
    unsigned.pop("signature_hmac_sha256")
    try:
        expected = hmac.new(signing_key.encode(), canonical(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(presented, expected):
            return False
        policy = evidence.get("validation_policy")
        if hashlib.sha256(canonical(policy)).hexdigest() != expected_policy_sha256.lower():
            return False
        results = evidence["crops"]
        if not isinstance(results, list) or not results:
            return False
        crop_names = {_text(row["crop"], "crop") for row in results}
        if len(crop_names) != len(results) or any(name != name.lower() for name in crop_names):
            return False
        thresholds = _validate_policy(policy, crop_names, expected_model_version)
        _time(evidence["generated_at_utc"])
        _thresholds(evidence["thresholds"])
        return evidence["thresholds"] == thresholds and all(
            _consistent_crop_result(row, thresholds, policy) for row in results
        )
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--policy", type=Path, help="Separate operator-supplied validation policy")
    parser.add_argument(
        "--policy-sha256",
        default=os.getenv("SIM_GOLDEN_POLICY_SHA256", ""),
        help="Trusted canonical-JSON policy digest (defaults to SIM_GOLDEN_POLICY_SHA256)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("certification/evidence/sim_golden_summary.json")
    )
    parser.add_argument("--require-promotion-eligible", action="store_true")
    args = parser.parse_args()
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else None
        evidence = evaluate(
            dataset,
            signing_key=os.getenv("SIM_GOLDEN_EVIDENCE_KEY", ""),
            validation_policy=policy,
            expected_policy_sha256=args.policy_sha256,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False)
        args.output.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
        return (
            1 if args.require_promotion_eligible and not evidence["eligible_for_promotion"] else 0
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"SIM-GOLDEN-01: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
