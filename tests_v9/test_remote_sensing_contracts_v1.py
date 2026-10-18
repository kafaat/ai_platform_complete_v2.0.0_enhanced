from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.contracts.remote_sensing import (
    AnomalyStatus,
    BaselineRefV1,
    CanonicalObservationV1,
    ContinuousSummaryV1,
    DiagnosisAssessmentStatus,
    DiagnosisHypothesisV1,
    EvidenceBundleV1,
    IndicatorDefinitionRefV1,
    ObservationLineageV1,
    ObservationPublishedEventV1,
    ObservationPublishedPayloadV1,
    ObservationQualityV1,
    ObservationUncertaintyV1,
    PublicationStatus,
    QualityGateStatus,
    QualityPolicyRefV1,
    RasterAssetPersistedV1,
    RasterAssetQualityV1,
    Severity,
    SignalAnomalyV1,
    ValueType,
    VerificationRequirement,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 15, 12, tzinfo=UTC)
HASH = "a" * 64
TENANT = uuid4()


def valid_quality() -> ObservationQualityV1:
    return ObservationQualityV1(
        gate_status=QualityGateStatus.PASSED,
        policy=QualityPolicyRefV1(
            policy_id="ndvi_current_real_only",
            policy_version="1.0.0",
            policy_hash=HASH,
            use_case="anomaly_detection",
        ),
        field_coverage_ratio=Decimal("0.95"),
        valid_pixel_ratio=Decimal("0.91"),
        field_cloud_ratio=Decimal("0.02"),
        field_shadow_ratio=Decimal("0.01"),
        indicator_in_range=True,
        score=Decimal("0.90"),
    )


def valid_observation() -> CanonicalObservationV1:
    asset_ref = "urn:sahool:raster-asset:ast_1"
    return CanonicalObservationV1(
        observation_ref="urn:sahool:observation:obs_1",
        tenant_id=TENANT,
        field_id="fld_34c8ee0dae0c",
        season_id="sea_2026_spring",
        asset_ref=asset_ref,
        indicator=IndicatorDefinitionRefV1(
            code="ndvi",
            semantic_version="1.0.0",
            value_type=ValueType.CONTINUOUS,
            unit="1",
        ),
        acquired_at=NOW - timedelta(hours=3),
        observed_at=NOW - timedelta(hours=2),
        published_at=NOW - timedelta(hours=1),
        summary=ContinuousSummaryV1(mean=Decimal("0.61"), stddev=Decimal("0.08")),
        observation_quality=valid_quality(),
        uncertainty=ObservationUncertaintyV1(
            method="quality-propagation-v1", confidence=Decimal("0.88")
        ),
        lineage=ObservationLineageV1(
            asset_ref=asset_ref,
            processing_run_ref="urn:sahool:processing-run:run_1",
            input_hash=HASH,
            output_hash=HASH,
            pipeline_version="31.7.0",
        ),
        publication_status=PublicationStatus.PUBLISHED,
    )


def _actual_legacy_observation_builder(monkeypatch, builder, *, measured=False):
    import importlib.util
    from pathlib import Path
    from uuid import UUID

    path = Path(__file__).resolve().parents[1] / "services/indicators-service"
    name = "observation_timeline" if builder == "timeline" else "observation_runtime"
    spec = importlib.util.spec_from_file_location(f"lineage_compat_{name}", path / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, 12, tzinfo=UTC)

    monkeypatch.setattr(module, "datetime", FixedClock)
    common = {
        "field_id": "fld_34c8ee0dae0c",
        "tenant_id": UUID("00000000-0000-4000-8000-000000000001"),
        "season_id": "sea_2026_spring",
    }
    if builder == "timeline":
        return module.canonicalize_timeseries(
            **common,
            indicator_code="ndvi",
            points=[{"datetime": "2026-10-01T07:30:00Z", "mean": 0.5, "valid_pixel_ratio": 0.9}],
        )[0]
    item = {
        "date": "2026-10-01T07:30:00Z",
        "stats": {"mean": 0.5},
        "real_data": True,
        "coverage_ratio": 0.9,
        "valid_pixel_ratio": 0.9,
    }
    if measured:
        item["indicator_product"] = {
            "source": "raster-service",
            "estimated": False,
            "quality_gate_passed": True,
            "quality_score": 0.9,
            "data_available_at": "2026-10-01T09:00:00Z",
            "provenance": {
                "scene_id": "cdse:sh:123",
                "qa_mask_version": "cdse-native-scl-datamask/2",
                "algorithm_version": "sahool.band_math/1",
                "acquisition_datetime": item["date"],
            },
        }
    return module.canonicalize_bundle(
        bundle={"field_id": common["field_id"], "observations": {"ndvi": item}},
        tenant_id=common["tenant_id"],
        season_id=common["season_id"],
    )[0]


@pytest.mark.parametrize("builder", ["timeline", "bundle"])
def test_absent_raster_lineage_preserves_actual_legacy_builder_payload(monkeypatch, builder):
    import json
    from pathlib import Path

    observation = _actual_legacy_observation_builder(monkeypatch, builder)
    # Captured from both real builders at pinned main 6e8cc0f9 with this fixed clock.
    fixture = Path(__file__).parent / "fixtures/observation_lineage_legacy_payloads.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))[builder]
    assert observation.model_dump(mode="json") == expected
    assert json.loads(observation.model_dump_json()) == expected
    assert "raster_provenance" not in observation.lineage.model_dump()
    # The fix must not omit unrelated optional values from the old wire contract.
    assert expected["supersedes"] is None
    assert expected["summary"]["median"] is None


def test_present_raster_lineage_survives_real_builder_and_json_serialization(monkeypatch):
    import json

    observation = _actual_legacy_observation_builder(monkeypatch, "bundle", measured=True)
    expected = {
        "source": "raster-service",
        "scene_id": "cdse:sh:123",
        "qa_mask_version": "cdse-native-scl-datamask/2",
        "algorithm_version": "sahool.band_math/1",
        "acquisition_datetime": "2026-10-01T07:30:00Z",
        "data_available_at": "2026-10-01T09:00:00Z",
    }
    assert observation.model_dump(mode="json")["lineage"]["raster_provenance"] == expected
    assert json.loads(observation.model_dump_json())["lineage"]["raster_provenance"] == expected
    assert observation.lineage.model_dump(mode="json")["raster_provenance"] == expected


def test_raster_lineage_serializer_keeps_extra_fields_forbidden():
    payload = valid_observation().lineage.model_dump()
    payload["unexpected_provenance"] = None
    with pytest.raises(ValidationError) as error:
        ObservationLineageV1.model_validate(payload)
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_contracts_are_immutable_and_forbid_extra_fields():
    obs = valid_observation()
    with pytest.raises(ValidationError):
        obs.observed_at = NOW
    payload = obs.model_dump()
    payload["pixel_array"] = [1, 2]
    with pytest.raises(ValidationError):
        CanonicalObservationV1.model_validate(payload)


def test_internal_storage_path_rejected():
    with pytest.raises(ValidationError):
        RasterAssetPersistedV1(
            asset_ref="urn:sahool:raster-asset:ast_1",
            tenant_id=TENANT,
            field_id="fld_1",
            provider="copernicus",
            platform="sentinel-2",
            sensor="msi",
            scene_id="scene-1",
            product_type="l2a",
            acquired_at=NOW - timedelta(hours=3),
            processed_at=NOW - timedelta(hours=2),
            persisted_at=NOW - timedelta(hours=1),
            cog_artifact_ref="s3://private/bucket.tif",
            asset_quality=RasterAssetQualityV1(
                coverage_ratio=Decimal("1"),
                valid_pixel_ratio=Decimal("1"),
                cloud_ratio=Decimal("0"),
                shadow_ratio=Decimal("0"),
                checksum_value=HASH,
                native_crs="EPSG:32638",
                native_resolution_m=Decimal("10"),
            ),
            processing_run_ref="urn:sahool:processing-run:run_1",
            producer_version="31.7.0",
        )


def test_temporal_order_is_enforced():
    data = valid_observation().model_dump()
    data["acquired_at"] = NOW
    data["observed_at"] = NOW - timedelta(hours=1)
    with pytest.raises(ValidationError, match="acquired_at_after_observed_at"):
        CanonicalObservationV1.model_validate(data)


def test_non_ndvi_summary_is_not_constrained_to_minus_one_plus_one():
    obs = valid_observation().model_copy(
        update={
            "indicator": IndicatorDefinitionRefV1(
                code="surface_temperature",
                semantic_version="1.0.0",
                value_type=ValueType.CONTINUOUS,
                unit="degC",
            ),
            "summary": ContinuousSummaryV1(mean=Decimal("42.5")),
        }
    )
    assert obs.summary.mean == Decimal("42.5")


def test_event_type_is_bound_to_payload():
    event = ObservationPublishedEventV1(
        event_id="evt_1",
        occurred_at=NOW,
        producer="indicators-service",
        producer_version="1.0.0",
        tenant_id=TENANT,
        correlation_id="corr_remote_sensing_1",
        aggregate_id="urn:sahool:observation:obs_1",
        aggregate_version=1,
        idempotency_key="idmp:observation:obs_1",
        payload=ObservationPublishedPayloadV1(observation=valid_observation()),
    )
    assert event.event_type == "sahool.rs.observation.published.v1"
    with pytest.raises(ValidationError):
        ObservationPublishedEventV1.model_validate(
            {**event.model_dump(), "event_type": "sahool.rs.asset.persisted.v1"}
        )


def test_signal_anomaly_cannot_accept_diagnosis_fields():
    anomaly = SignalAnomalyV1(
        anomaly_ref="urn:sahool:anomaly:anm_1",
        tenant_id=TENANT,
        field_id="fld_1",
        season_id="sea_1",
        detection_run_ref="urn:sahool:processing-run:det_1",
        primary_observation_ref="urn:sahool:observation:obs_1",
        signal_type="vegetation_moisture_decline",
        deviation=Decimal("-0.18"),
        baseline_refs=(
            BaselineRefV1(
                baseline_type="same_phenological_stage",
                baseline_run_ref="urn:sahool:processing-run:base_1",
            ),
        ),
        severity=Severity.HIGH,
        confidence=Decimal("0.81"),
        evidence_bundle=EvidenceBundleV1(),
        verification_requirement=VerificationRequirement.REQUIRED,
        status=AnomalyStatus.DETECTED,
        detector_model_ref="urn:sahool:model:veg-analysis-3.2.1",
        detected_at=NOW,
    )
    data = anomaly.model_dump()
    data["suspected_condition"] = "water_stress"
    with pytest.raises(ValidationError):
        SignalAnomalyV1.model_validate(data)


def test_diagnosis_alternative_rule_is_conditional():
    base = dict(
        diagnosis_ref="urn:sahool:diagnosis:dgn_1",
        tenant_id=TENANT,
        field_id="fld_1",
        season_id="sea_1",
        primary_anomaly_ref="urn:sahool:anomaly:anm_1",
        suspected_condition="water_stress",
        evidence_bundle=EvidenceBundleV1(),
        confidence_method="bayesian_fusion_v1",
        ground_verification_requirement=VerificationRequirement.REQUIRED,
        assessment_status=DiagnosisAssessmentStatus.PENDING,
        diagnosis_model_ref="urn:sahool:model:veg-analysis-3.2.1",
        proposed_at=NOW,
    )
    with pytest.raises(ValidationError, match="alternatives_or_assessment_note_required"):
        DiagnosisHypothesisV1(confidence=Decimal("0.80"), **base)
    high = DiagnosisHypothesisV1(confidence=Decimal("0.95"), **base)
    assert high.alternative_conditions == ()


def test_identifier_and_ownership_invariants():
    assert "mean" not in RasterAssetPersistedV1.model_fields
    assert "pixel_array" not in CanonicalObservationV1.model_fields
    assert "suspected_condition" not in SignalAnomalyV1.model_fields
    assert "prescription" not in DiagnosisHypothesisV1.model_fields
    data = valid_observation().model_dump()
    data["field_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        CanonicalObservationV1.model_validate(data)
