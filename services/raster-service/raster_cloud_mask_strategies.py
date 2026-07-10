"""Cloud/quality mask strategy contracts for raster sources.

Cloud QA is not a single boolean. Sentinel-2, Landsat, drone imagery, and
commercial imagery expose different QA bands.  This module standardizes the
strategy interface while keeping missing masks explicit and honest.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MaskResult:
    """Result of a source-specific cloud/quality masking strategy."""

    strategy: str
    mask: Any | None
    cloud_mask_applied: bool
    cloud_pct: float | None = None
    shadow_mask: Any | None = None
    shadow_pct: float | None = None
    snow_mask: Any | None = None
    snow_pct: float | None = None
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CloudMaskStrategy(ABC):
    """Abstract strategy for source-native cloud/quality masks."""

    name: str

    @abstractmethod
    def apply(self, *, np, band_reader, band_mapping, target_shape) -> MaskResult:
        """Apply a source-specific mask using a band reader callback."""


class Sentinel2SCLStrategy(CloudMaskStrategy):
    """Sentinel-2 QA strategy using SCL plus optional CLM/CLP bands.

    SCL semantics: shadow=3, cloud/cirrus=8/9/10, snow=11.  CLM and CLP
    are treated as source-native cloud supplements when present.  All-NaN CLP
    rasters are handled as unavailable rather than raising via ``nanmax``.
    """

    name = "sentinel2_scl"

    @staticmethod
    def _or_mask(np, left, right):
        if right is None:
            return left
        if left is None:
            return right
        return np.logical_or(left, right)

    def apply(self, *, np, band_reader, band_mapping, target_shape) -> MaskResult:
        warnings: list[str] = []
        sources: list[str] = []
        cloud = None
        shadow = None
        snow = None

        scl_idx = getattr(band_mapping, "scl", None)
        if scl_idx is not None:
            scl = band_reader(scl_idx)
            if scl is not None and getattr(scl, "shape", None) == target_shape:
                scl_cloud = np.isin(scl, [8, 9, 10])
                cloud = self._or_mask(np, cloud, scl_cloud)
                shadow = self._or_mask(np, shadow, np.isin(scl, [3]))
                snow = self._or_mask(np, snow, np.isin(scl, [11]))
                sources.append("SCL")
            else:
                warnings.append("sentinel2_scl_shape_mismatch_or_unreadable")
        else:
            warnings.append("sentinel2_scl_band_unavailable")

        clm_idx = getattr(band_mapping, "clm", None)
        if clm_idx is not None:
            clm = band_reader(clm_idx)
            if clm is not None and getattr(clm, "shape", None) == target_shape:
                cloud = self._or_mask(np, cloud, clm.astype("float32") > 0)
                sources.append("CLM")
            else:
                warnings.append("sentinel2_clm_shape_mismatch_or_unreadable")

        clp_idx = getattr(band_mapping, "clp", None)
        if clp_idx is not None:
            clp = band_reader(clp_idx)
            if clp is not None and getattr(clp, "shape", None) == target_shape:
                clp_f = clp.astype("float32")
                finite = np.isfinite(clp_f)
                if bool(np.any(finite)):
                    clp_max = float(np.nanmax(clp_f))
                    threshold = 0.40 if clp_max <= 1.0 else 40.0
                    cloud = self._or_mask(np, cloud, np.where(finite, clp_f >= threshold, False))
                    sources.append("CLP")
                else:
                    warnings.append("sentinel2_clp_all_nan_unavailable")
            else:
                warnings.append("sentinel2_clp_shape_mismatch_or_unreadable")

        if cloud is None and shadow is None and snow is None:
            return MaskResult(
                strategy=self.name,
                mask=None,
                cloud_mask_applied=False,
                warnings=warnings or ["sentinel2_qa_bands_unavailable"],
            )

        combined = None
        for part in (cloud, shadow, snow):
            combined = self._or_mask(np, combined, part)

        return MaskResult(
            strategy=self.name,
            mask=combined,
            cloud_mask_applied=cloud is not None,
            cloud_pct=float(np.mean(cloud) * 100.0) if cloud is not None else None,
            shadow_mask=shadow,
            shadow_pct=float(np.mean(shadow) * 100.0) if shadow is not None else None,
            snow_mask=snow,
            snow_pct=float(np.mean(snow) * 100.0) if snow is not None else None,
            sources=sources,
            warnings=warnings,
        )


class LandsatQAPixelStrategy(CloudMaskStrategy):
    """Landsat QA_PIXEL strategy using common Collection 2 bit positions."""

    name = "landsat_qa_pixel"

    # Common USGS Collection 2 QA_PIXEL bits: 3 cloud, 4 cloud shadow, 5 snow.
    CLOUD_BIT = 3
    SHADOW_BIT = 4
    SNOW_BIT = 5

    def apply(self, *, np, band_reader, band_mapping, target_shape) -> MaskResult:
        qa_idx = getattr(band_mapping, "qa_pixel", None) or getattr(band_mapping, "scl", None)
        if qa_idx is None:
            return MaskResult(
                strategy=self.name,
                mask=None,
                cloud_mask_applied=False,
                warnings=["landsat_qa_pixel_band_unavailable"],
            )
        qa = band_reader(qa_idx)
        if qa is None or getattr(qa, "shape", None) != target_shape:
            return MaskResult(
                strategy=self.name,
                mask=None,
                cloud_mask_applied=False,
                warnings=["landsat_qa_pixel_shape_mismatch_or_unreadable"],
            )
        qa_i = qa.astype("uint32")
        cloud = (qa_i & (1 << self.CLOUD_BIT)) > 0
        shadow = (qa_i & (1 << self.SHADOW_BIT)) > 0
        snow = (qa_i & (1 << self.SNOW_BIT)) > 0
        combined = np.logical_or(np.logical_or(cloud, shadow), snow)
        return MaskResult(
            strategy=self.name,
            mask=combined,
            cloud_mask_applied=True,
            cloud_pct=float(np.mean(cloud) * 100.0),
            shadow_mask=shadow,
            shadow_pct=float(np.mean(shadow) * 100.0),
            snow_mask=snow,
            snow_pct=float(np.mean(snow) * 100.0),
            sources=["QA_PIXEL"],
        )


class NoOpCloudMaskStrategy(CloudMaskStrategy):
    """Explicit no-op strategy for sources without cloud masks, such as drones."""

    name = "noop_unavailable"

    def apply(self, *, np, band_reader, band_mapping, target_shape) -> MaskResult:  # noqa: ARG002
        return MaskResult(
            strategy=self.name,
            mask=None,
            cloud_mask_applied=False,
            warnings=["source_has_no_native_cloud_mask"],
        )


def strategy_for_source_format(source_format: str | None) -> CloudMaskStrategy:
    """Return the source-native cloud mask strategy for a raster source."""

    value = (source_format or "").lower()
    if "sentinel2" in value or "sentinel-2" in value:
        return Sentinel2SCLStrategy()
    if "landsat" in value:
        return LandsatQAPixelStrategy()
    if "drone" in value:
        return NoOpCloudMaskStrategy()
    return NoOpCloudMaskStrategy()
