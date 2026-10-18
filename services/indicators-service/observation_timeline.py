"""Canonical observation timeline and supersession projection (RS-4).

This module remains a read adapter over raster-service until durable observation
persistence lands. It never computes spectral pixels; it converts real raster
series points into canonical timeline entries and marks older entries as
superseded by the latest valid observation for the same indicator.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from shared.contracts.remote_sensing import (
    CanonicalObservationV1,
    ContinuousSummaryV1,
    IndicatorDefinitionRefV1,
    ObservationLineageV1,
    ObservationQualityV1,
    ObservationUncertaintyV1,
    PublicationStatus,
    QualityGateStatus,
    QualityPolicyRefV1,
    ValueType,
)
from shared.contracts.remote_sensing.admission import (
    POLICY_VERSION,
    finite_decimal,
    quality_reasons,
)

RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)
RASTER_SERVICE_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN") or os.getenv("RASTER_SERVICE_TOKEN", "")
TIMELINE_POLICY_ID = os.getenv("RS_TIMELINE_POLICY_ID", "NDVI_TIMELINE_REAL_ONLY_V1")


class TimelineSourceError(RuntimeError):
    """Public status for a known context or service-auth failure."""

    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code


def _stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(p or "") for p in parts).encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _parse_date(value: str) -> datetime:
    raw = value.strip()
    if len(raw) == 10:
        raw += "T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _ratio01(value: Any) -> Decimal | None:
    """Coerce a value to a [0,1] Decimal, or None if absent/invalid."""
    d = finite_decimal(value)
    return d if d is not None and Decimal(0) <= d <= Decimal(1) else None


def canonicalize_timeseries(
    *,
    field_id: str,
    tenant_id: UUID,
    season_id: str,
    indicator_code: str,
    points: list[dict[str, Any]],
) -> list[CanonicalObservationV1]:
    dated = sorted(
        (p for p in points if p.get("datetime")), key=lambda p: _parse_date(str(p["datetime"]))
    )
    # A failed newest measurement is an abstention, not permission to resurrect
    # a material change from an older observation as the current result.
    if not dated or finite_decimal(dated[-1].get("mean")) is None:
        return []
    ordered = [p for p in dated if finite_decimal(p.get("mean")) is not None]

    refs: list[str] = []
    for point in ordered:
        acquired = _parse_date(str(point["datetime"]))
        native = _stable_id(
            "obs",
            tenant_id,
            field_id,
            season_id,
            indicator_code,
            acquired.isoformat(),
        )
        refs.append(f"urn:sahool:observation:{native}")

    now = datetime.now(UTC)
    output: list[CanonicalObservationV1] = []
    latest_ref = refs[-1]
    for idx, point in enumerate(ordered):
        acquired = _parse_date(str(point["datetime"]))
        observation_ref = refs[idx]
        asset_native = _stable_id(
            "ast",
            tenant_id,
            field_id,
            indicator_code,
            acquired.isoformat(),
            point.get("scene_id"),
            point.get("geometry_revision"),
            point.get("algorithm_version"),
        )
        # Aggregate observation identity stays stable across policy upgrades.
        # Computation identity and hashes bind the exact reprocessed input.
        run_native = _stable_id(
            "run",
            asset_native,
            json.dumps(point, sort_keys=True, separators=(",", ":"), default=str),
            POLICY_VERSION,
        )
        value = Decimal(str(point["mean"]))
        is_latest = observation_ref == latest_ref
        # RS-4 honesty: carry the REAL per-observation quality reported by
        # raster-service instead of a fabricated perfect 1.0. Legacy layers that
        # predate quality capture report None → flag it, never invent a score.
        _vpr = _ratio01(point.get("valid_pixel_ratio"))
        _cov = _ratio01(point.get("coverage_ratio"))
        _cloud_pct = point.get("cloud_pct")
        _cloud = (
            _ratio01(finite_decimal(_cloud_pct) / Decimal("100"))
            if finite_decimal(_cloud_pct) is not None
            else None
        )
        _quality_reported = _vpr is not None or _cov is not None or _cloud is not None
        _score = _vpr if _vpr is not None else _cov
        quality = {
            "valid_pixel_ratio": _vpr,
            "field_coverage_ratio": _cov,
            "field_cloud_ratio": _cloud,
        }
        in_range = indicator_code not in {"ndvi", "ndmi", "ndwi", "gndvi"} or Decimal(
            -1
        ) <= value <= Decimal(1)
        reasons = quality_reasons(quality) + (() if in_range else ("indicator_out_of_range",))
        gate = (
            QualityGateStatus.NOT_EVALUATED
            if any(x.endswith("unavailable") for x in reasons)
            else QualityGateStatus.REJECTED
            if reasons
            else QualityGateStatus.PASSED
        )
        output.append(
            CanonicalObservationV1(
                observation_ref=observation_ref,
                tenant_id=tenant_id,
                field_id=field_id,
                season_id=season_id,
                asset_ref=f"urn:sahool:raster-asset:{asset_native}",
                indicator=IndicatorDefinitionRefV1(
                    code=indicator_code,
                    semantic_version="1.0.0",
                    value_type=ValueType.CONTINUOUS,
                    unit="1",
                    algorithm_ref="raster-timeseries-real-only",
                ),
                acquired_at=acquired,
                observed_at=now,
                published_at=now,
                summary=ContinuousSummaryV1(mean=value, stddev=finite_decimal(point.get("stddev"))),
                observation_quality=ObservationQualityV1(
                    gate_status=gate,
                    policy=QualityPolicyRefV1(
                        policy_id=TIMELINE_POLICY_ID,
                        policy_version=POLICY_VERSION,
                        policy_hash=hashlib.sha256(
                            f"{TIMELINE_POLICY_ID}|{POLICY_VERSION}".encode()
                        ).hexdigest(),
                        use_case="anomaly_detection",
                    ),
                    field_coverage_ratio=_cov,
                    valid_pixel_ratio=_vpr,
                    field_cloud_ratio=_cloud,
                    field_shadow_ratio=_ratio01(point.get("shadow_ratio")),
                    indicator_in_range=in_range,
                    score=_score,
                    reason_codes=(
                        ("per_point_quality_from_raster",)
                        if _quality_reported
                        else ("per_point_quality_not_reported",)
                    )
                    + reasons,
                ),
                uncertainty=ObservationUncertaintyV1(
                    method=(
                        "timeline-source-projection-v1"
                        if _quality_reported
                        else "timeline-source-projection-quality-unreported-v1"
                    ),
                    confidence=(_score if _score is not None else Decimal("0")),
                    detail="Measured input quality only; zero when unknown. Not a probability of agronomic correctness.",
                ),
                lineage=ObservationLineageV1(
                    asset_ref=f"urn:sahool:raster-asset:{asset_native}",
                    processing_run_ref=f"urn:sahool:processing-run:{run_native}",
                    input_hash=hashlib.sha256(
                        json.dumps(
                            point, sort_keys=True, separators=(",", ":"), default=str
                        ).encode()
                    ).hexdigest(),
                    output_hash=hashlib.sha256(str(value).encode()).hexdigest(),
                    pipeline_version="1.0.0",
                ),
                publication_status=(
                    PublicationStatus.PUBLISHED if is_latest else PublicationStatus.SUPERSEDED
                ),
                supersedes=(refs[idx - 1] if is_latest and idx > 0 else None),
            )
        )
    return output


async def fetch_canonical_timeline(
    *,
    field_id: str,
    tenant_id: UUID,
    season_id: str,
    indicators: list[str],
    authorization: str | None = None,
) -> list[CanonicalObservationV1]:
    if not RASTER_SERVICE_TOKEN:
        raise RuntimeError("RASTER_SERVICE_TOKEN/SAHOOL_AGENT_TOKEN is required")
    if not authorization:
        raise RuntimeError("season_context_authorization_required")
    output: list[CanonicalObservationV1] = []
    async with httpx.AsyncClient(timeout=20) as client:
        platform = os.getenv("PLATFORM_API_URL", "http://sahool-platform:8000").rstrip("/")
        response = await client.get(
            f"{platform}/api/v1/fields/{quote(field_id, safe='')}/seasons",
            headers={"Authorization": authorization, "X-Tenant-Id": str(tenant_id)},
        )
        response.raise_for_status()
        seasons = response.json()
        matches = [
            s for s in seasons if s.get("season_id") == season_id and s.get("field_id") == field_id
        ]
        if not matches:
            raise TimelineSourceError(404, "canonical_season_not_found")
        if len(matches) != 1 or not matches[0].get("sowing_date"):
            raise TimelineSourceError(409, "canonical_season_window_unavailable")
        season = matches[0]
        try:
            start = _parse_date(str(season["sowing_date"]))
            end = (
                _parse_date(str(season["season_end"]))
                if season.get("season_end")
                else datetime.now(UTC)
            )
        except (ValueError, TypeError) as exc:
            raise TimelineSourceError(409, "canonical_season_window_invalid") from exc
        if end < start:
            raise TimelineSourceError(409, "canonical_season_window_invalid")
        for indicator in indicators:
            response = await client.get(
                f"{RASTER_SERVICE_URL}/v1/fields/{quote(field_id, safe='')}/timeseries",
                params={"index": indicator},
                headers={"X-Tenant-Id": str(tenant_id), "X-Agent-Token": RASTER_SERVICE_TOKEN},
            )
            if response.status_code in {401, 403}:
                raise TimelineSourceError(502, "raster_service_authentication_failed")
            if response.is_error:
                raise TimelineSourceError(424, "raster_timeline_source_unavailable")
            payload = response.json()
            if not payload.get("available") or not payload.get("real_data"):
                continue
            output.extend(
                canonicalize_timeseries(
                    field_id=field_id,
                    tenant_id=tenant_id,
                    season_id=season_id,
                    indicator_code=indicator,
                    points=[
                        p
                        for p in (payload.get("points") or [])
                        if p.get("datetime")
                        and start.date() <= _parse_date(str(p["datetime"])).date() <= end.date()
                    ],
                )
            )
    return sorted(output, key=lambda item: item.acquired_at, reverse=True)
