from datetime import UTC, datetime, timezone

from p5_certification import (
    build_calibration,
    build_learning_manifest,
    certify,
    evaluate_promotion,
)

from shared.contracts.soil.p5 import (
    FieldValidationRecord,
    ProductionCertificationRecord,
    ValidationMeasurement,
)


def rec(i, pred):
    return FieldValidationRecord(
        tenant_id="t",
        field_id=f"f{i % 5}",
        governorate="Al Jawf",
        crop="wheat",
        campaign_id="c",
        accepted=True,
        measurements=[
            ValidationMeasurement(
                property_name="ec_ds_m",
                measured_value=2.0 + (i % 3) * 0.1,
                predicted_value=pred,
                unit="dS/m",
                method="lab",
                observed_at=datetime.now(UTC),
                evidence_id=f"e{i}",
            )
        ],
    )


def test_calibration_and_promotion():
    rows = [rec(i, 2.05 + (i % 3) * 0.1) for i in range(30)]
    a = build_calibration(
        tenant_id="t",
        governorate="Al Jawf",
        crop="wheat",
        product_type="salinity",
        dataset_version="d1",
        model_version="m1",
        records=rows,
        minimum_samples=25,
    )
    d = evaluate_promotion(a)
    assert a.status == "candidate" and d.promotable


def test_certification_fail_closed_and_dual_approval():
    r = ProductionCertificationRecord(
        tenant_id="t",
        release_ref="r",
        environment="prod",
        migrations_applied_through="v165",
        rls_passed=True,
        concurrency_passed=True,
        e2e_passed=True,
        lineage_passed=True,
        performance_passed=True,
        calibration_passed=True,
        certified_by=["a"],
    )
    assert not certify(r).certified
    r.certified_by = ["a", "b"]
    r.blockers = []
    assert certify(r).certified


def test_learning_manifest_requires_scale_diversity_and_lineage():
    rows = [
        {
            "learning_id": f"l{i}",
            "eligible_for_training": True,
            "field_id": f"f{i % 5}",
            "action_type": "gypsum_rate",
            "source_profile_hash": "h",
            "outcome_id": f"o{i}",
        }
        for i in range(30)
    ]
    m = build_learning_manifest(
        tenant_id="t",
        name="n",
        version="1",
        learning_rows=rows,
        feature_schema_version="f1",
        target_schema_version="t1",
    )
    assert m.eligible_for_training and m.train_count + m.validation_count + m.test_count == 30
