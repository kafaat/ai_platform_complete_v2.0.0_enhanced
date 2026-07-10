from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from raster_api_models import BandMapping  # noqa: E402
from raster_cloud_mask_strategies import (  # noqa: E402
    LandsatQAPixelStrategy,
    NoOpCloudMaskStrategy,
    Sentinel2SCLStrategy,
    strategy_for_source_format,
)

pytestmark = pytest.mark.unit


def _reader(bands: dict[int, np.ndarray]):
    def _read(idx: int):
        return bands.get(idx)

    return _read


def test_strategy_factory_dispatches_by_source_format():
    assert isinstance(strategy_for_source_format("sentinel2_l2a"), Sentinel2SCLStrategy)
    assert isinstance(strategy_for_source_format("landsat8"), LandsatQAPixelStrategy)
    assert isinstance(strategy_for_source_format("drone_orthomosaic"), NoOpCloudMaskStrategy)


def test_sentinel2_strategy_combines_scl_clm_clp_and_handles_shadow_snow():
    scl = np.array([[4, 8], [3, 11]], dtype=np.uint8)
    clm = np.array([[0, 0], [0, 1]], dtype=np.uint8)
    clp = np.array([[0.1, 0.9], [0.2, 0.3]], dtype=np.float32)
    result = Sentinel2SCLStrategy().apply(
        np=np,
        band_reader=_reader({7: scl, 8: clm, 9: clp}),
        band_mapping=BandMapping(scl=7, clm=8, clp=9),
        target_shape=(2, 2),
    )
    assert result.cloud_mask_applied is True
    assert set(result.sources) == {"SCL", "CLM", "CLP"}
    assert result.mask.tolist() == [[False, True], [True, True]]
    assert result.shadow_mask.tolist() == [[False, False], [True, False]]
    assert result.snow_mask.tolist() == [[False, False], [False, True]]


def test_sentinel2_strategy_clp_all_nan_is_warning_not_failure():
    clp = np.array([[np.nan, np.nan]], dtype=np.float32)
    result = Sentinel2SCLStrategy().apply(
        np=np,
        band_reader=_reader({9: clp}),
        band_mapping=BandMapping(clp=9),
        target_shape=(1, 2),
    )
    assert result.cloud_mask_applied is False
    assert result.mask is None
    assert "sentinel2_clp_all_nan_unavailable" in result.warnings


def test_landsat_qa_pixel_strategy_uses_bits():
    # bits: 3 cloud, 4 shadow, 5 snow
    qa = np.array([[0, 1 << 3], [1 << 4, 1 << 5]], dtype=np.uint16)
    result = LandsatQAPixelStrategy().apply(
        np=np,
        band_reader=_reader({10: qa}),
        band_mapping=BandMapping(qa_pixel=10),
        target_shape=(2, 2),
    )
    assert result.cloud_mask_applied is True
    assert result.sources == ["QA_PIXEL"]
    assert result.mask.tolist() == [[False, True], [True, True]]


def test_noop_strategy_is_explicitly_unavailable():
    result = NoOpCloudMaskStrategy().apply(
        np=np,
        band_reader=_reader({}),
        band_mapping=BandMapping(),
        target_shape=(1, 1),
    )
    assert result.strategy == "noop_unavailable"
    assert result.mask is None
    assert result.cloud_mask_applied is False
    assert "source_has_no_native_cloud_mask" in result.warnings


def test_valid_mask_excludes_out_of_field_pixels_from_cloud_pct():
    # مشهد: حقل صغير (بكسل واحد) غائم بالكامل داخل نافذة أكبرها خارج المضلّع (SCL=0
    # مملوء ⇒ يُصنَّف «صافياً»). بلا valid_mask تُخفَّف الغيوم كذباً؛ مع valid_mask
    # يُحسب على البكسل داخل الحقل فقط ⇒ 100%.
    scl = np.array([[0, 0], [0, 8]], dtype=np.uint8)  # فقط البكسل الأخير غيمة (SCL=8)
    valid = np.array([[False, False], [False, True]])  # داخل الحقل = البكسل الغائم
    reader = _reader({1: scl})
    diluted = Sentinel2SCLStrategy().apply(
        np=np, band_reader=reader, band_mapping=BandMapping(scl=1), target_shape=(2, 2)
    )
    in_field = Sentinel2SCLStrategy().apply(
        np=np,
        band_reader=reader,
        band_mapping=BandMapping(scl=1),
        target_shape=(2, 2),
        valid_mask=valid,
    )
    assert diluted.cloud_pct == 25.0  # 1 من 4 (مخفَّف كذباً)
    assert in_field.cloud_pct == 100.0  # 1 من 1 داخل الحقل (صادق)


def test_valid_mask_all_false_yields_none_not_fabricated_zero():
    scl = np.array([[8, 8]], dtype=np.uint8)
    valid = np.array([[False, False]])
    result = Sentinel2SCLStrategy().apply(
        np=np,
        band_reader=_reader({1: scl}),
        band_mapping=BandMapping(scl=1),
        target_shape=(1, 2),
        valid_mask=valid,
    )
    assert result.cloud_pct is None  # لا اختلاق صفر عند غياب بكسل صالح
