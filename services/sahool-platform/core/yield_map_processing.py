"""Derived QC/projection for immutable PA-003 yield-map evidence.

Raw combine/harvest records remain immutable evidence in ``yield_map_records``.
This module never edits or replaces them.  It produces a deterministic processing
projection suitable for zoning/evaluation while preserving every rejection reason
and source digest.

The projection intentionally does *not* polygonize management zones: classified
points are evidence seeds. A polygon management zone still requires a spatial
zoning step and human/agronomic review before it can anchor a prescription.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

SCHEMA_VERSION = "yield_map_processing.v1"
MAD_Z_LIMIT = 4.5


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _robust_bounds(values: list[float]) -> tuple[float, float, str]:
    """Median/MAD bounds; deterministic IQR fallback when MAD collapses to zero."""
    if not values:
        return (0.0, 0.0, "none")
    med = median(values)
    deviations = [abs(v - med) for v in values]
    mad = median(deviations)
    if mad > 1e-12:
        # modified z = 0.6745 * |x-med| / MAD
        span = MAD_Z_LIMIT * mad / 0.6745
        return med - span, med + span, "median_mad_4.5"
    ordered = sorted(values)
    q1 = ordered[round((len(ordered) - 1) * 0.25)]
    q3 = ordered[round((len(ordered) - 1) * 0.75)]
    iqr = q3 - q1
    if iqr > 1e-12:
        return q1 - 3.0 * iqr, q3 + 3.0 * iqr, "iqr_3x"
    return min(values), max(values), "degenerate_no_outlier_rejection"


def _moisture_adjust(
    yield_kg_ha: float, actual_pct: float | None, standard_pct: float | None
) -> float:
    if actual_pct is None or standard_pct is None:
        return yield_kg_ha
    if not (0 <= actual_pct < 100 and 0 <= standard_pct < 100):
        return yield_kg_ha
    # Standard wet-basis correction: preserve dry matter.
    return yield_kg_ha * ((100.0 - actual_pct) / (100.0 - standard_pct))


@dataclass(frozen=True)
class ProcessedYieldSample:
    record_id: str
    source_record_id: str | None
    longitude: float
    latitude: float
    raw_yield_kg_ha: float
    processed_yield_kg_ha: float
    moisture_pct: float | None
    yield_index: float
    productivity_class: str
    record_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["geometry"] = {"type": "Point", "coordinates": [self.longitude, self.latitude]}
        body["yield"] = self.processed_yield_kg_ha
        return body


@dataclass(frozen=True)
class YieldMapProcessingProjection:
    schema_version: str
    source_sha256: str
    raw_record_count: int
    accepted_record_count: int
    duplicate_record_count: int
    outlier_record_count: int
    moisture_adjusted_count: int
    standard_moisture_pct: float | None
    raw_mean_kg_ha: float | None
    processed_mean_kg_ha: float | None
    outlier_method: str
    quality_status: str
    limitations: list[str]
    samples: list[ProcessedYieldSample]
    processing_digest: str

    def to_dict(self, *, include_samples: bool = True) -> dict[str, Any]:
        body = asdict(self)
        body["samples"] = [s.to_dict() for s in self.samples] if include_samples else []
        return body


def process_yield_records(
    *,
    source_sha256: str,
    rows: list[dict[str, Any]],
    standard_moisture_pct: float | None = None,
) -> YieldMapProcessingProjection:
    if not source_sha256:
        raise ValueError("source_sha256 is required")
    if standard_moisture_pct is not None and not 0 <= float(standard_moisture_pct) < 100:
        raise ValueError("standard_moisture_pct must be within 0..99.999")

    candidates: list[tuple[dict[str, Any], float, float | None]] = []
    seen: set[tuple[float, float, str | None]] = set()
    duplicates = 0
    limitations: list[str] = []
    for row in rows:
        y = _finite(row.get("yield_kg_ha"))
        lon = _finite(row.get("longitude"))
        lat = _finite(row.get("latitude"))
        moisture = _finite(row.get("moisture_pct"))
        if y is None or y <= 0 or lon is None or lat is None:
            continue
        identity = (
            round(lon, 8),
            round(lat, 8),
            str(row.get("harvested_at") or "") or None,
        )
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        candidates.append((row, y, moisture))

    adjusted = [
        _moisture_adjust(y, moisture, standard_moisture_pct) for _, y, moisture in candidates
    ]
    low, high, method = _robust_bounds(adjusted)
    kept: list[tuple[dict[str, Any], float, float | None]] = []
    outliers = 0
    for (row, _raw, moisture), value in zip(candidates, adjusted, strict=True):
        if value < low or value > high:
            outliers += 1
            continue
        kept.append((row, value, moisture))

    mean_processed = sum(v for _, v, _ in kept) / len(kept) if kept else None
    raw_values = [y for _, y, _ in candidates]
    raw_mean = sum(raw_values) / len(raw_values) if raw_values else None

    # Tertile-like relative classes around the processed mean.  These are point
    # evidence labels, never polygons and never prescriptions.
    samples: list[ProcessedYieldSample] = []
    for row, value, moisture in kept:
        idx = value / mean_processed if mean_processed and mean_processed > 0 else 1.0
        cls = "low" if idx < 0.85 else "high" if idx > 1.15 else "medium"
        samples.append(
            ProcessedYieldSample(
                record_id=str(row.get("record_id") or ""),
                source_record_id=(
                    str(row.get("source_record_id"))
                    if row.get("source_record_id") is not None
                    else None
                ),
                longitude=float(row["longitude"]),
                latitude=float(row["latitude"]),
                raw_yield_kg_ha=round(float(row["yield_kg_ha"]), 3),
                processed_yield_kg_ha=round(value, 3),
                moisture_pct=moisture,
                yield_index=round(idx, 4),
                productivity_class=cls,
                record_sha256=(str(row.get("record_sha256")) if row.get("record_sha256") else None),
            )
        )

    if standard_moisture_pct is None:
        limitations.append("standard_moisture_not_declared_no_moisture_normalization")
    if duplicates:
        limitations.append(f"duplicate_spatiotemporal_records_removed:{duplicates}")
    if outliers:
        limitations.append(f"robust_outliers_removed:{outliers}")
    if not samples:
        limitations.append("no_cleaned_yield_samples")

    content = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "standard_moisture_pct": standard_moisture_pct,
        "outlier_method": method,
        "samples": [s.to_dict() for s in samples],
        "limitations": limitations,
    }
    return YieldMapProcessingProjection(
        schema_version=SCHEMA_VERSION,
        source_sha256=source_sha256,
        raw_record_count=len(rows),
        accepted_record_count=len(samples),
        duplicate_record_count=duplicates,
        outlier_record_count=outliers,
        moisture_adjusted_count=(
            sum(1 for _, _, m in kept if m is not None) if standard_moisture_pct is not None else 0
        ),
        standard_moisture_pct=standard_moisture_pct,
        raw_mean_kg_ha=round(raw_mean, 3) if raw_mean is not None else None,
        processed_mean_kg_ha=round(mean_processed, 3) if mean_processed is not None else None,
        outlier_method=method,
        quality_status="processed" if samples else "insufficient",
        limitations=limitations,
        samples=samples,
        processing_digest=_digest(content),
    )
