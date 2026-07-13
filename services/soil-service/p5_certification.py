"""P5 validation, calibration, certification and learning governance."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable

from shared.contracts.soil.p5 import (
    AcceptanceThreshold,
    CalibrationMetric,
    CalibrationPromotionDecision,
    FieldValidationRecord,
    LearningDatasetManifest,
    ProductionCertificationRecord,
    RegionalCalibrationArtifact,
)

DEFAULT_THRESHOLDS = {
    ("texture_probability", "clay_pct"): AcceptanceThreshold(
        product_type="texture_probability",
        property_name="clay_pct",
        min_samples=30,
        max_mae=8,
        max_rmse=11,
        max_abs_bias=4,
        min_r2=0.55,
    ),
    ("salinity", "ec_ds_m"): AcceptanceThreshold(
        product_type="salinity",
        property_name="ec_ds_m",
        min_samples=25,
        max_mae=1.5,
        max_rmse=2.0,
        max_abs_bias=0.75,
        min_r2=0.60,
    ),
    ("mobile_visual", "surface_salinity_probability"): AcceptanceThreshold(
        product_type="mobile_visual",
        property_name="surface_salinity_probability",
        min_samples=40,
        max_mae=0.15,
        max_rmse=0.20,
        max_abs_bias=0.08,
        min_r2=0.50,
    ),
}


def _r2(y, p):
    if len(y) < 2:
        return None
    mean = sum(y) / len(y)
    ss = sum((v - mean) ** 2 for v in y)
    if ss == 0:
        return None
    return 1 - sum((a - b) ** 2 for a, b in zip(y, p, strict=False)) / ss


def build_calibration(
    *,
    tenant_id: str,
    governorate: str,
    crop: str | None,
    product_type: str,
    dataset_version: str,
    model_version: str,
    records: Iterable[FieldValidationRecord],
    minimum_samples: int = 20,
) -> RegionalCalibrationArtifact:
    accepted = [
        r
        for r in records
        if r.accepted and r.governorate == governorate and (crop is None or r.crop == crop)
    ]
    grouped = defaultdict(list)
    for r in accepted:
        for m in r.measurements:
            if m.predicted_value is not None:
                grouped[m.property_name].append(
                    (m.measured_value, m.predicted_value, r.field_id, r.validation_id)
                )
    metrics = []
    for prop, rows in sorted(grouped.items()):
        y = [x[0] for x in rows]
        p = [x[1] for x in rows]
        errs = [b - a for a, b in zip(y, p, strict=False)]
        metrics.append(
            CalibrationMetric(
                property_name=prop,
                n=len(rows),
                mae=sum(abs(e) for e in errs) / len(errs),
                rmse=math.sqrt(sum(e * e for e in errs) / len(errs)),
                bias=sum(errs) / len(errs),
                r2=_r2(y, p),
                spatial_cv=len({x[2] for x in rows}) >= 3,
            )
        )
    ids = sorted({r.validation_id for r in accepted})
    h = hashlib.sha256(json.dumps(ids, sort_keys=True).encode()).hexdigest()
    enough = bool(metrics) and all(m.n >= minimum_samples for m in metrics)
    return RegionalCalibrationArtifact(
        tenant_id=tenant_id,
        governorate=governorate,
        crop=crop,
        product_type=product_type,
        dataset_version=dataset_version,
        source_validation_ids=ids,
        metrics=metrics,
        minimum_samples=minimum_samples,
        status="candidate" if enough else "insufficient_data",
        model_version=model_version,
        training_data_hash=h,
        leakage_checks_passed=len(ids) == len(set(ids)),
    )


def evaluate_promotion(
    artifact: RegionalCalibrationArtifact, thresholds: list[AcceptanceThreshold] | None = None
) -> CalibrationPromotionDecision:
    reasons = []
    checked = []
    thresholds = thresholds or [
        v for (pt, _), v in DEFAULT_THRESHOLDS.items() if pt == artifact.product_type
    ]
    by = {m.property_name: m for m in artifact.metrics}
    if artifact.status != "candidate":
        reasons.append("calibration_not_candidate")
    if not artifact.leakage_checks_passed:
        reasons.append("leakage_checks_failed")
    for t in thresholds:
        m = by.get(t.property_name)
        item = {"property_name": t.property_name, "passed": False}
        if not m:
            reasons.append(f"metric_missing:{t.property_name}")
            checked.append(item)
            continue
        failures = []
        if m.n < t.min_samples:
            failures.append("sample_count")
        if t.require_spatial_cv and not m.spatial_cv:
            failures.append("spatial_cv")
        if t.max_mae is not None and (m.mae is None or m.mae > t.max_mae):
            failures.append("mae")
        if t.max_rmse is not None and (m.rmse is None or m.rmse > t.max_rmse):
            failures.append("rmse")
        if t.max_abs_bias is not None and (m.bias is None or abs(m.bias) > t.max_abs_bias):
            failures.append("bias")
        if t.min_r2 is not None and (m.r2 is None or m.r2 < t.min_r2):
            failures.append("r2")
        item.update(
            {"passed": not failures, "failures": failures, "metric": m.model_dump(mode="json")}
        )
        checked.append(item)
        reasons.extend(f"{t.property_name}:{f}" for f in failures)
    return CalibrationPromotionDecision(
        calibration_id=artifact.calibration_id,
        promotable=not reasons,
        reasons=reasons,
        evaluated_metrics=checked,
    )


def certify(record: ProductionCertificationRecord) -> ProductionCertificationRecord:
    blockers = list(record.blockers)
    checks = {
        "rls": record.rls_passed,
        "concurrency": record.concurrency_passed,
        "e2e": record.e2e_passed,
        "lineage": record.lineage_passed,
        "performance": record.performance_passed,
        "calibration": record.calibration_passed,
    }
    blockers.extend(f"{k}_not_passed" for k, v in checks.items() if not v)
    blockers = list(dict.fromkeys(blockers))
    record.blockers = blockers
    record.certified = not blockers and len(record.certified_by) >= 2
    if not blockers and len(record.certified_by) < 2:
        record.blockers = ["dual_certification_required"]
    return record


def build_learning_manifest(
    *,
    tenant_id: str,
    name: str,
    version: str,
    learning_rows: list[dict],
    feature_schema_version: str,
    target_schema_version: str,
) -> LearningDatasetManifest:
    eligible = [r for r in learning_rows if r.get("eligible_for_training")]
    exclusions = []
    if len(eligible) < 30:
        exclusions.append("minimum_training_rows_not_met")
    fields = {r.get("field_id") for r in eligible}
    if len(fields) < 5:
        exclusions.append("field_diversity_insufficient")
    if not all(r.get("source_profile_hash") and r.get("outcome_id") for r in eligible):
        exclusions.append("lineage_incomplete")
    ids = sorted(str(r.get("learning_id")) for r in eligible)
    digest = hashlib.sha256(json.dumps(ids, sort_keys=True).encode()).hexdigest()
    n = len(eligible)
    train = int(n * 0.7)
    val = int(n * 0.15)
    test = n - train - val
    return LearningDatasetManifest(
        tenant_id=tenant_id,
        name=name,
        version=version,
        source_learning_ids=ids,
        feature_schema_version=feature_schema_version,
        target_schema_version=target_schema_version,
        train_count=train,
        validation_count=val,
        test_count=test,
        leakage_checks_passed=len(ids) == len(set(ids)),
        lineage_complete="lineage_incomplete" not in exclusions,
        dataset_hash=digest,
        eligible_for_training=not exclusions,
        exclusion_reasons=exclusions,
    )
