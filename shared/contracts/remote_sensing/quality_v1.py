from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from .base import ContractModel
from .enums import QualityGateStatus
from .identifiers import SchemaVersion, Sha256Digest


class QualityMeasurementV1(ContractModel):
    metric_name: str = Field(min_length=1, max_length=96)
    metric_value: Decimal
    unit: str | None = None
    threshold_value: Decimal | None = None
    threshold_operator: str | None = Field(default=None, pattern=r"^(gte|lte|gt|lt|eq|ne)$")
    passed: bool
    detail: str | None = Field(default=None, max_length=512)


class QualityPolicyRefV1(ContractModel):
    policy_id: str = Field(min_length=1, max_length=128)
    policy_version: SchemaVersion
    policy_hash: Sha256Digest
    use_case: str = Field(min_length=1, max_length=64)


class RasterAssetQualityV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    coverage_ratio: Decimal = Field(ge=0, le=1)
    valid_pixel_ratio: Decimal = Field(ge=0, le=1)
    cloud_ratio: Decimal = Field(ge=0, le=1)
    shadow_ratio: Decimal = Field(ge=0, le=1)
    checksum_value: Sha256Digest
    native_crs: str = Field(min_length=1, max_length=128)
    footprint_crs: str = "EPSG:4326"
    native_resolution_m: Decimal = Field(gt=0)
    expected_bands: tuple[str, ...] = ()
    present_bands: tuple[str, ...] = ()
    missing_bands: tuple[str, ...] = ()
    unexpected_bands: tuple[str, ...] = ()
    measurements: tuple[QualityMeasurementV1, ...] = ()

    @model_validator(mode="after")
    def validate_bands(self):
        expected = set(self.expected_bands)
        present = set(self.present_bands)
        if set(self.missing_bands) != expected - present:
            raise ValueError("missing_bands_mismatch")
        return self


class ObservationQualityV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    gate_status: QualityGateStatus
    policy: QualityPolicyRefV1
    field_coverage_ratio: Decimal = Field(ge=0, le=1)
    valid_pixel_ratio: Decimal = Field(ge=0, le=1)
    field_cloud_ratio: Decimal = Field(ge=0, le=1)
    field_shadow_ratio: Decimal = Field(ge=0, le=1)
    indicator_in_range: bool
    indicator_range_min: Decimal | None = None
    indicator_range_max: Decimal | None = None
    score: Decimal | None = Field(default=None, ge=0, le=1)
    reason_codes: tuple[str, ...] = ()
    measurements: tuple[QualityMeasurementV1, ...] = ()
