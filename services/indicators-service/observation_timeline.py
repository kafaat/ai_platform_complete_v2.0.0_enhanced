"""Canonical observation timeline and supersession projection (RS-4).

This module remains a read adapter over raster-service until durable observation
persistence lands. It never computes spectral pixels; it converts real raster
series points into canonical timeline entries and marks older entries as
superseded by the latest valid observation for the same indicator.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
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

RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)
RASTER_SERVICE_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN") or os.getenv("RASTER_SERVICE_TOKEN", "")
TIMELINE_POLICY_ID = os.getenv("RS_TIMELINE_POLICY_ID", "NDVI_TIMELINE_REAL_ONLY_V1")


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


def canonicalize_timeseries(
    *,
    field_id: str,
    tenant_id: UUID,
    season_id: str,
    indicator_code: str,
    points: list[dict[str, Any]],
) -> list[CanonicalObservationV1]:
    ordered = sorted(
        (p for p in points if p.get("datetime") and p.get("mean") is not None),
        key=lambda p: str(p["datetime"]),
    )
    if not ordered:
        return []

    refs: list[str] = []
    for point in ordered:
        acquired = _parse_date(str(point["datetime"]))
        native = _stable_id(
            "obs", tenant_id, field_id, season_id, indicator_code, acquired.isoformat()
        )
        refs.append(f"urn:sahool:observation:{native}")

    now = datetime.now(UTC)
    output: list[CanonicalObservationV1] = []
    latest_ref = refs[-1]
    for idx, point in enumerate(ordered):
        acquired = _parse_date(str(point["datetime"]))
        observation_ref = refs[idx]
        asset_native = _stable_id("ast", tenant_id, field_id, indicator_code, acquired.isoformat())
        run_native = _stable_id("run", asset_native)
        value = Decimal(str(point["mean"]))
        is_latest = observation_ref == latest_ref
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
                summary=ContinuousSummaryV1(mean=value),
                observation_quality=ObservationQualityV1(
                    gate_status=QualityGateStatus.PASSED,
                    policy=QualityPolicyRefV1(
                        policy_id=TIMELINE_POLICY_ID,
                        policy_version="1.0.0",
                        policy_hash=hashlib.sha256(
                            f"{TIMELINE_POLICY_ID}|1.0.0".encode()
                        ).hexdigest(),
                        use_case="timeline_display",
                    ),
                    field_coverage_ratio=Decimal("1"),
                    valid_pixel_ratio=Decimal("1"),
                    field_cloud_ratio=Decimal("0"),
                    field_shadow_ratio=Decimal("0"),
                    indicator_in_range=True,
                    score=Decimal("1"),
                    reason_codes=(),
                ),
                uncertainty=ObservationUncertaintyV1(
                    method="timeline-source-projection-v1", confidence=Decimal("1")
                ),
                lineage=ObservationLineageV1(
                    asset_ref=f"urn:sahool:raster-asset:{asset_native}",
                    processing_run_ref=f"urn:sahool:processing-run:{run_native}",
                    input_hash=hashlib.sha256(
                        f"{tenant_id}|{field_id}|{indicator_code}|{acquired.isoformat()}".encode()
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
    *, field_id: str, tenant_id: UUID, season_id: str, indicators: list[str]
) -> list[CanonicalObservationV1]:
    if not RASTER_SERVICE_TOKEN:
        raise RuntimeError("RASTER_SERVICE_TOKEN/SAHOOL_AGENT_TOKEN is required")
    output: list[CanonicalObservationV1] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for indicator in indicators:
            response = await client.get(
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/timeseries",
                params={"index": indicator},
                headers={"X-Tenant-Id": str(tenant_id), "X-Agent-Token": RASTER_SERVICE_TOKEN},
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("available") or not payload.get("real_data"):
                continue
            output.extend(
                canonicalize_timeseries(
                    field_id=field_id,
                    tenant_id=tenant_id,
                    season_id=season_id,
                    indicator_code=indicator,
                    points=list(payload.get("points") or []),
                )
            )
    return sorted(output, key=lambda item: item.acquired_at, reverse=True)
