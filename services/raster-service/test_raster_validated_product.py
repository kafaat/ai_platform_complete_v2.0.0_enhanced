from __future__ import annotations

import pytest
from raster_api_models import BandMapping, IndicatorKind, ProcessRequest, SourceFormat
from raster_cloud_mask_strategies import (
    LandsatQAPixelStrategy,
    NoOpCloudMaskStrategy,
    Sentinel2SCLStrategy,
    strategy_for_source_format,
)
from raster_validated_product import build_validated_raster_product


def _req(source_format=SourceFormat.sentinel2_l2a):
    return ProcessRequest(
        tenant_id="t1",
        field_id="f1",
        raster_url="file:///tmp/example.tif",
        indicator=IndicatorKind.ndvi,
        source_format=source_format,
        bands=BandMapping(red=1, nir=2, scl=3),
    )


def test_validated_product_requires_quality_contracts():
    pixel_qa = {
        "schema": "sahool.raster_pixel_qa/1",
        "quality_score": 0.82,
        "valid_pixel_ratio": 0.9,
        "warnings": [],
    }
    quality_flags = {
        "schema": "sahool.raster_quality_flags/1",
        "cloud_mask_applied": True,
        "cloud_shadow_mask_applied": True,
        "snow_mask_applied": False,
        "saturation_mask_applied": False,
        "aerosol_mask_applied": False,
    }
    product = build_validated_raster_product(
        req=_req(),
        pixel_qa=pixel_qa,
        quality_flags=quality_flags,
        spatial_crs="EPSG:32638",
        bounds_4326=[44.0, 15.0, 44.1, 15.1],
        cloud_mask_strategy="sentinel2_scl",
        reflectance_normalized=True,
    )
    assert product.schema == "sahool.validated_raster_product/1"
    assert product.quality_score == 0.82
    assert product.cloud_mask_applied is True
    assert product.reflectance_normalized is True
    assert product.provenance.processing_version == "sahool.raster_validated_product/1"


def test_validated_product_rejects_implicit_missing_cloud_mask():
    pixel_qa = {
        "schema": "sahool.raster_pixel_qa/1",
        "quality_score": 0.5,
        "valid_pixel_ratio": 0.7,
        "warnings": ["cloud_mask_not_applied_or_unavailable"],
    }
    quality_flags = {
        "schema": "sahool.raster_quality_flags/1",
        "cloud_mask_applied": False,
    }
    with pytest.raises(ValueError):
        build_validated_raster_product(
            req=_req(),
            pixel_qa=pixel_qa,
            quality_flags=quality_flags,
            spatial_crs="EPSG:32638",
            cloud_mask_strategy="sentinel2_scl",
        )


def test_source_strategy_selection_is_explicit():
    assert isinstance(strategy_for_source_format("sentinel2_l2a"), Sentinel2SCLStrategy)
    assert isinstance(strategy_for_source_format("landsat8"), LandsatQAPixelStrategy)
    assert isinstance(strategy_for_source_format("drone_orthomosaic"), NoOpCloudMaskStrategy)


def test_validated_product_accepts_honest_unavailable_cloud_strategies():
    # الإصلاح: المسار الصادق «حاولنا قناعاً لكنّه غير متاح» أو «لم يُطلَب» يجب أن
    # يُقبَل بعلامة صريحة (unknown_unavailable / not_requested) لا أن ينهار 500.
    pixel_qa = {
        "schema": "sahool.raster_pixel_qa/1",
        "quality_score": 0.5,
        "valid_pixel_ratio": 0.7,
        "warnings": ["cloud_mask_not_applied_or_unavailable"],
    }
    quality_flags = {
        "schema": "sahool.raster_quality_flags/1",
        "cloud_mask_applied": False,
    }
    for strat in ("unknown_unavailable", "not_requested"):
        product = build_validated_raster_product(
            req=_req(),
            pixel_qa=pixel_qa,
            quality_flags=quality_flags,
            spatial_crs="EPSG:32638",
            cloud_mask_strategy=strat,
        )
        assert product.cloud_mask_applied is False
        assert product.cloud_mask_strategy == strat
