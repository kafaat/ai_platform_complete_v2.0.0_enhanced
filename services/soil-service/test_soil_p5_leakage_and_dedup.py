"""P5 calibration: repeated rows must not inflate n, and leakage must be real."""

from datetime import UTC, datetime

import pytest
from p5_certification import build_calibration, build_learning_manifest, evaluate_promotion

from shared.contracts.soil.p5 import FieldValidationRecord, ValidationMeasurement

pytestmark = pytest.mark.unit


def _rec(i, *, field_id=None, vid=None, pred=None):
    kw = {"validation_id": vid} if vid else {}
    return FieldValidationRecord(
        tenant_id="t",
        field_id=field_id or f"f{i % 5}",
        governorate="Al Jawf",
        crop="wheat",
        campaign_id="c",
        accepted=True,
        measurements=[
            ValidationMeasurement(
                property_name="ec_ds_m",
                measured_value=2.0 + (i % 3) * 0.1,
                predicted_value=pred if pred is not None else 2.05 + (i % 3) * 0.1,
                unit="dS/m",
                method="lab",
                observed_at=datetime.now(UTC),
                evidence_id=f"e{i}",
            )
        ],
        **kw,
    )


def _build(records, **kw):
    return build_calibration(
        tenant_id="t",
        governorate="Al Jawf",
        crop="wheat",
        product_type="salinity",
        dataset_version="d1",
        model_version="m1",
        records=records,
        minimum_samples=kw.pop("minimum_samples", 3),
        **kw,
    )


def test_three_records_repeated_ten_times_count_as_three_and_fail_leakage():
    base = [_rec(i, field_id=f"f{i}") for i in range(3)]
    rows = [r.model_copy() for r in base for _ in range(10)]
    a = _build(rows, minimum_samples=3)
    (metric,) = a.metrics
    assert metric.n == 3  # not 30
    assert a.source_validation_ids == sorted(r.validation_id for r in base)
    assert a.leakage_checks_passed is False
    d = evaluate_promotion(a)
    assert d.promotable is False
    assert "leakage_checks_failed" in d.reasons


def test_duplicate_measurement_rows_do_not_inflate_n_with_25_floor():
    base = [_rec(i, field_id=f"f{i}") for i in range(3)]
    rows = [r.model_copy() for r in base for _ in range(10)]
    a = _build(rows, minimum_samples=25)
    assert a.metrics[0].n == 3
    assert a.status == "insufficient_data"


def test_unique_records_pass_leakage():
    a = _build([_rec(i) for i in range(30)], minimum_samples=25)
    assert a.leakage_checks_passed is True
    assert a.metrics[0].n == 30
    assert a.metrics[0].field_diversity_passed is True
    assert a.metrics[0].spatial_cv is False


def test_training_field_overlap_fails_leakage():
    rows = [_rec(i) for i in range(30)]
    assert _build(rows, training_field_ids=["other"]).leakage_checks_passed is True
    assert _build(rows, training_field_ids=["f2"]).leakage_checks_passed is False


def test_field_diversity_requires_three_fields_and_no_dominant_field():
    two_fields = [_rec(i, field_id=f"f{i % 2}") for i in range(30)]
    assert _build(two_fields).metrics[0].field_diversity_passed is False
    # 3 fields but one holds 28 of 30 observations
    dominated = [_rec(i, field_id="big" if i < 28 else f"s{i}") for i in range(30)]
    assert _build(dominated).metrics[0].field_diversity_passed is False
    balanced = [_rec(i, field_id=f"f{i % 3}") for i in range(30)]
    assert _build(balanced).metrics[0].field_diversity_passed is True


def _learning_rows(ids):
    return [
        {
            "learning_id": lid,
            "eligible_for_training": True,
            "field_id": f"f{i % 5}",
            "source_profile_hash": "h",
            "outcome_id": f"o{i}",
        }
        for i, lid in enumerate(ids)
    ]


def _manifest(rows):
    return build_learning_manifest(
        tenant_id="t",
        name="n",
        version="1",
        learning_rows=rows,
        feature_schema_version="f1",
        target_schema_version="t1",
    )


def test_manifest_with_duplicate_learning_ids_is_not_eligible():
    m = _manifest(_learning_rows([f"l{i % 15}" for i in range(30)]))
    assert m.leakage_checks_passed is False
    assert m.eligible_for_training is False
    assert "leakage_checks_failed" in m.exclusion_reasons


def test_manifest_with_unique_ids_stays_eligible():
    m = _manifest(_learning_rows([f"l{i}" for i in range(30)]))
    assert m.leakage_checks_passed is True
    assert m.eligible_for_training is True
