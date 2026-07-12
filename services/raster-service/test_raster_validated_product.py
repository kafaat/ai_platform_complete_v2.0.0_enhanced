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


def test_provenance_enrichment_satisfies_vegetation_authority_gate():
    """RASTER-PROVENANCE-ENRICHMENT closure: the enriched provenance carries the exact
    fields the vegetation indicator-registry authority check validates against."""
    import sys
    from pathlib import Path

    from raster_quality import ALGORITHM_VERSION
    from raster_validated_product import ProvenanceRecord

    prov = ProvenanceRecord(
        scene_id="S2_X",
        capture_datetime="2026-07-01T00:00:00Z",
        acquisition_datetime="2026-07-01T00:00:00Z",
        algorithm_version=ALGORITHM_VERSION,
        qa_mask_version="sentinel2_scl/1",
        valid_pixel_pct=85.0,
    )
    veg_dir = Path(__file__).resolve().parents[1] / "vegetation-analysis-service"
    sys.path.insert(0, str(veg_dir))
    from indicator_registry import validate_observation

    errors = validate_observation(
        "ndvi",
        {
            "value": 0.6,
            "source": "raster-service",
            "estimated": False,
            "data_available_at": "2026-07-01T01:00:00Z",
            "valid_pixel_pct": prov.valid_pixel_pct,
            "provenance": prov.model_dump(),
        },
    )
    assert errors == []  # real, fully-provenanced NDVI is now authority-eligible


def test_qa_mask_version_absent_when_no_mask_applied():
    """An unmasked scene must stay honestly non-authoritative downstream."""
    from raster_validated_product import ProvenanceRecord

    prov = ProvenanceRecord(scene_id="S2_X", capture_datetime="2026-07-01T00:00:00Z")
    assert prov.qa_mask_version is None and prov.acquisition_datetime is None
