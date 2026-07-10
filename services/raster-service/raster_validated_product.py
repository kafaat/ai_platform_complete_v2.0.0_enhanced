"""Validated raster product contract for indicator preprocessing.

The raster-service must not treat arbitrary raw pixels as an indicator-ready
product.  This module defines the explicit data contract passed from raw/pixel
QA into indicator provenance.  It is intentionally lightweight: it records the
quality/provenance envelope, not the full pixel array payload.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class BoundingBox(BaseModel):
    """Spatial bounds for the validated product."""

    minx: float
    miny: float
    maxx: float
    maxy: float
    crs: str = "EPSG:4326"


class ProvenanceRecord(BaseModel):
    """Minimum provenance needed to trace raw image -> QA -> indicator."""

    schema: str = "sahool.raster_provenance/1"
    source: str | None = None
    source_format: str | None = None
    scene_id: str | None = None
    capture_datetime: str | None = None
    processing_version: str = "sahool.raster_validated_product/1"
    source_uri: str | None = None
    input_checksum: str | None = None
    output_checksum: str | None = None


class ValidatedRasterProduct(BaseModel):
    """Explicit contract accepted by indicator computation/provenance.

    A valid product must carry quality score, valid-pixel ratio, QA flags,
    spatial metadata, and provenance.  Cloud masks may be honestly unavailable
    for sources such as drone orthomosaics, but that unavailability must be
    represented through ``cloud_mask_strategy='noop_unavailable'`` and quality
    warnings rather than silently omitted.
    """

    schema: str = "sahool.validated_raster_product/1"
    source: str | None = None
    source_format: str | None = None
    indicator: str | None = None
    bands: dict[str, Any] = Field(default_factory=dict)
    quality_score: float = Field(ge=0.0, le=1.0)
    valid_pixel_ratio: float = Field(ge=0.0, le=1.0)
    cloud_mask_applied: bool
    shadow_mask_applied: bool = False
    snow_mask_applied: bool = False
    saturation_mask_applied: bool = False
    aerosol_mask_applied: bool = False
    reflectance_normalized: bool = False
    spatial_crs: str
    spatial_bounds: BoundingBox | None = None
    quality_flags: dict[str, Any]
    pixel_qa: dict[str, Any]
    topographic_qa: dict[str, Any] = Field(default_factory=dict)
    cloud_mask_strategy: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    provenance: ProvenanceRecord
    derived_product_computed: bool = False
    fabricated_indicator: bool = False

    @field_validator("quality_flags")
    @classmethod
    def _quality_flags_must_be_contract(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("schema") != "sahool.raster_quality_flags/1":
            raise ValueError("quality_flags must use sahool.raster_quality_flags/1")
        return value

    @field_validator("pixel_qa")
    @classmethod
    def _pixel_qa_must_be_contract(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("schema") != "sahool.raster_pixel_qa/1":
            raise ValueError("pixel_qa must use sahool.raster_pixel_qa/1")
        if value.get("quality_score") is None:
            raise ValueError("pixel_qa.quality_score is required")
        return value

    @model_validator(mode="after")
    def _cloud_mask_status_must_be_explicit(self) -> ValidatedRasterProduct:
        if not self.cloud_mask_applied and self.cloud_mask_strategy not in {
            "noop_unavailable",
            "provider_precomputed_expected",
            "rgba_alpha_mask",
            "unknown_unavailable",
        }:
            raise ValueError(
                "cloud mask must be applied or explicitly represented by a no-op/provider strategy"
            )
        if self.fabricated_indicator:
            raise ValueError("ValidatedRasterProduct cannot represent a fabricated indicator")
        return self


def build_validated_raster_product(
    *,
    req: Any,
    pixel_qa: dict[str, Any],
    quality_flags: dict[str, Any],
    spatial_crs: str,
    bounds_4326: list[float] | None = None,
    topographic_qa: dict[str, Any] | None = None,
    cloud_mask_strategy: str = "unknown_unavailable",
    reflectance_normalized: bool = False,
    source_uri: str | None = None,
) -> ValidatedRasterProduct:
    """Build and validate the indicator-ready raster contract."""

    bounds = None
    if bounds_4326 and len(bounds_4326) == 4:
        bounds = BoundingBox(
            minx=float(bounds_4326[0]),
            miny=float(bounds_4326[1]),
            maxx=float(bounds_4326[2]),
            maxy=float(bounds_4326[3]),
            crs="EPSG:4326",
        )
    return ValidatedRasterProduct(
        source=getattr(req, "raster_url", None),
        source_format=str(getattr(req, "source_format", "")) or None,
        indicator=str(
            getattr(getattr(req, "indicator", None), "value", getattr(req, "indicator", None))
        ),
        bands=(
            getattr(req, "bands", None).model_dump()
            if hasattr(getattr(req, "bands", None), "model_dump")
            else {}
        ),
        quality_score=float(pixel_qa["quality_score"]),
        valid_pixel_ratio=float(pixel_qa.get("valid_pixel_ratio", 0.0)),
        cloud_mask_applied=bool(quality_flags.get("cloud_mask_applied")),
        shadow_mask_applied=bool(quality_flags.get("cloud_shadow_mask_applied")),
        snow_mask_applied=bool(quality_flags.get("snow_mask_applied")),
        saturation_mask_applied=bool(quality_flags.get("saturation_mask_applied")),
        aerosol_mask_applied=bool(quality_flags.get("aerosol_mask_applied")),
        reflectance_normalized=bool(reflectance_normalized),
        spatial_crs=spatial_crs,
        spatial_bounds=bounds,
        quality_flags=quality_flags,
        pixel_qa=pixel_qa,
        topographic_qa=topographic_qa or {},
        cloud_mask_strategy=cloud_mask_strategy,
        warnings=list(pixel_qa.get("warnings", [])),
        provenance=ProvenanceRecord(
            source=getattr(req, "provider", None),
            source_format=str(getattr(req, "source_format", "")) or None,
            scene_id=getattr(req, "scene_id", None),
            capture_datetime=getattr(req, "capture_datetime", None),
            source_uri=source_uri or getattr(req, "raster_url", None),
        ),
        derived_product_computed=False,
        fabricated_indicator=False,
    )


def assert_indicator_accepts_validated_product(product: ValidatedRasterProduct) -> None:
    """Runtime assertion used as a contract boundary before indicator publication."""

    if not isinstance(product, ValidatedRasterProduct):
        raise TypeError("indicator computation requires ValidatedRasterProduct")
    if product.quality_score is None or product.pixel_qa.get("quality_score") is None:
        raise ValueError("ValidatedRasterProduct missing quality score")
