#!/usr/bin/env python3
"""SIM-GOLDEN-01: leakage-safe WOFOST yield validation and signed evidence."""

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
DEFAULT_THRESHOLDS = {"max_mape_pct": 20.0, "max_nrmse_pct": 25.0,
                      "max_abs_bias_pct": 10.0, "min_r2": 0.50,
                      "min_samples": 30, "min_farms": 3, "min_seasons": 2}
REQUIRED = {"sample_id", "crop", "season_id", "farm_id", "observed_yield_kg_ha",
            "predicted_yield_kg_ha", "observation_source", "harvest_at", "prediction_at",
            "model_version", "input_digest"}


class GoldenError(ValueError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise GoldenError("timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate(rows: list[dict]) -> None:
    if not rows:
        raise GoldenError("golden dataset is empty")
    seen: set[str] = set()
    for row in rows:
        missing = REQUIRED - row.keys()
        if missing:
            raise GoldenError("dataset row missing required fields: " + ", ".join(sorted(missing)))
        sample_id = str(row["sample_id"])
        if sample_id in seen:
            raise GoldenError("duplicate sample_id")
        seen.add(sample_id)
        if row["observation_source"] not in ALLOWED_SOURCES:
            raise GoldenError("unverified harvest observation source")
        observed = float(row["observed_yield_kg_ha"])
        predicted = float(row["predicted_yield_kg_ha"])
        if not math.isfinite(observed) or not math.isfinite(predicted) or observed <= 0 or predicted < 0:
            raise GoldenError("yield values must be finite and observed yield must be positive")
        if _time(str(row["prediction_at"])) > _time(str(row["harvest_at"])):
            raise GoldenError("prediction was created after harvest (target leakage)")
        digest = str(row["input_digest"])
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise GoldenError("input_digest must be sha256 hex")
        if "tenant_id" in row:
            raise GoldenError("raw tenant_id is forbidden in portable golden datasets; use farm_id pseudonyms")


def _metrics(rows: list[dict]) -> dict[str, float]:
    observed = [float(row["observed_yield_kg_ha"]) for row in rows]
    predicted = [float(row["predicted_yield_kg_ha"]) for row in rows]
    residuals = [p - o for p, o in zip(predicted, observed, strict=True)]
    mean_observed = statistics.fmean(observed)
    mae = statistics.fmean(abs(v) for v in residuals)
    rmse = math.sqrt(statistics.fmean(v * v for v in residuals))
    mape = statistics.fmean(abs(v) / o for v, o in zip(residuals, observed, strict=True)) * 100
    bias_pct = statistics.fmean(residuals) / mean_observed * 100
    denominator = sum((o - mean_observed) ** 2 for o in observed)
    r2 = 1 - sum(v * v for v in residuals) / denominator if denominator > 0 else float("-inf")
    return {"mae_kg_ha": round(mae, 6), "rmse_kg_ha": round(rmse, 6),
            "nrmse_pct": round(rmse / mean_observed * 100, 6), "mape_pct": round(mape, 6),
            "bias_pct": round(bias_pct, 6), "r2": round(r2, 6)}


def evaluate(dataset: dict, *, signing_key: str = "") -> dict:
    rows = dataset.get("samples") if isinstance(dataset, dict) else None
    if not isinstance(rows, list):
        raise GoldenError("dataset.samples must be a list")
    _validate(rows)
    thresholds = {**DEFAULT_THRESHOLDS, **(dataset.get("thresholds") or {})}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["crop"]).lower()].append(row)
    crop_results = []
    for crop, crop_rows in sorted(grouped.items()):
        farms = {str(r["farm_id"]) for r in crop_rows}
        seasons = sorted({str(r["season_id"]) for r in crop_rows})
        latest = seasons[-1]
        holdout = [r for r in crop_rows if str(r["season_id"]) == latest]
        metrics = _metrics(holdout)
        checks = {
            "sample_count": len(crop_rows) >= int(thresholds["min_samples"]),
            "farm_diversity": len(farms) >= int(thresholds["min_farms"]),
            "season_diversity": len(seasons) >= int(thresholds["min_seasons"]),
            "temporal_holdout_nonempty": bool(holdout) and len(seasons) >= 2,
            "mape": metrics["mape_pct"] <= float(thresholds["max_mape_pct"]),
            "nrmse": metrics["nrmse_pct"] <= float(thresholds["max_nrmse_pct"]),
            "bias": abs(metrics["bias_pct"]) <= float(thresholds["max_abs_bias_pct"]),
            "r2": metrics["r2"] >= float(thresholds["min_r2"]),
        }
        crop_results.append({"crop": crop, "samples": len(crop_rows), "farms": len(farms),
                             "seasons": len(seasons), "holdout_season": latest,
                             "holdout_samples": len(holdout), "metrics": metrics,
                             "checks": checks, "passed": all(checks.values())})
    dataset_digest = hashlib.sha256(canonical(dataset)).hexdigest()
    model_versions = sorted({str(row["model_version"]) for row in rows})
    passed = bool(crop_results) and all(row["passed"] for row in crop_results)
    evidence = {"schema_version": 1, "evidence_type": "sim_golden_01",
                "generated_at_utc": datetime.now(UTC).isoformat(), "dataset_sha256": dataset_digest,
                "model_versions": model_versions, "thresholds": thresholds,
                "crops": crop_results, "status": "verified" if passed else "rejected",
                "eligible_for_promotion": passed and len(signing_key) >= 32,
                "signature_status": "signed" if len(signing_key) >= 32 else "missing"}
    if len(signing_key) >= 32:
        evidence["signature_hmac_sha256"] = hmac.new(signing_key.encode(), canonical(evidence), hashlib.sha256).hexdigest()
    return evidence


def verify_signed_evidence(evidence: dict, signing_key: str) -> bool:
    if len(signing_key) < 32 or evidence.get("signature_status") != "signed":
        return False
    presented = str(evidence.get("signature_hmac_sha256") or "")
    unsigned = dict(evidence)
    unsigned.pop("signature_hmac_sha256", None)
    expected = hmac.new(signing_key.encode(), canonical(unsigned), hashlib.sha256).hexdigest()
    return bool(evidence.get("eligible_for_promotion")) and hmac.compare_digest(presented, expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path("certification/evidence/sim_golden_summary.json"))
    parser.add_argument("--require-promotion-eligible", action="store_true")
    args = parser.parse_args()
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        evidence = evaluate(dataset, signing_key=os.getenv("SIM_GOLDEN_EVIDENCE_KEY", ""))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1 if args.require_promotion_eligible and not evidence["eligible_for_promotion"] else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"SIM-GOLDEN-01: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
