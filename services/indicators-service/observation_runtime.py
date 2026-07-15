"""Canonical observation adapter over the current raster-service truth path.

RS-3 shadow runtime: raster-service remains the pixel/COG owner. This module
converts its validated observation bundle into immutable canonical observations
without recomputing band math. It is deliberately stateless; durable persistence
and NATS consumption can be introduced after parity certification.
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
DEFAULT_POLICY_ID = os.getenv("RS_OBSERVATION_POLICY_ID", "NDVI_CURRENT_REAL_ONLY_V1")


def _stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(p or "") for p in parts).encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None


def _parse_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(UTC)
    if len(raw) == 10:
        raw += "T00:00:00Z"
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _algorithm_version(product: dict[str, Any]) -> str:
    provenance = product.get("provenance") or {}
    raw = str(provenance.get("algorithm_version") or "1.0.0")
    # Existing versions may contain service prefixes; canonical contract wants semver.
    for token in raw.replace("_", "-").split("-"):
        if token and token[0].isdigit() and token.count(".") >= 2:
            return token.lstrip("v")
    return "1.0.0"


def canonicalize_bundle(
    *, bundle: dict[str, Any], tenant_id: UUID, season_id: str
) -> list[CanonicalObservationV1]:
    field_id = str(bundle["field_id"])
    now = datetime.now(UTC)
    output: list[CanonicalObservationV1] = []
    for indicator_code, item in (bundle.get("observations") or {}).items():
        stats = item.get("stats") or {}
        product = item.get("indicator_product") or {}
        provenance = product.get("provenance") or {}
        acquired = _parse_time(
            provenance.get("acquisition_datetime")
            or provenance.get("capture_datetime")
            or item.get("date")
        )
        scene_id = provenance.get("scene_id") or "unknown-scene"
        asset_native = _stable_id(
            "ast", tenant_id, field_id, scene_id, indicator_code, acquired.isoformat()
        )
        observation_native = _stable_id(
            "obs", tenant_id, field_id, season_id, asset_native, indicator_code
        )
        run_native = str(provenance.get("processing_job_id") or _stable_id("run", asset_native))
        input_hash = hashlib.sha256(
            f"{tenant_id}|{field_id}|{scene_id}|{indicator_code}|{acquired.isoformat()}".encode()
        ).hexdigest()
        output_hash = hashlib.sha256(repr(sorted(stats.items())).encode()).hexdigest()
        coverage = _to_decimal(item.get("coverage_ratio")) or Decimal("0")
        valid = _to_decimal(item.get("valid_pixel_ratio")) or Decimal("0")
        cloud = _to_decimal(item.get("cloud_cover"))
        if cloud is None:
            pct = _to_decimal(item.get("cloud_pct"))
            cloud = (pct / Decimal("100")) if pct is not None else Decimal("0")
        score = _to_decimal(item.get("confidence"))
        gate = (
            QualityGateStatus.PASSED if bool(item.get("real_data")) else QualityGateStatus.REJECTED
        )
        output.append(
            CanonicalObservationV1(
                observation_ref=f"urn:sahool:observation:{observation_native}",
                tenant_id=tenant_id,
                field_id=field_id,
                season_id=season_id,
                asset_ref=f"urn:sahool:raster-asset:{asset_native}",
                indicator=IndicatorDefinitionRefV1(
                    code=str(indicator_code),
                    semantic_version=_algorithm_version(product),
                    value_type=ValueType.CONTINUOUS,
                    unit="1",
                    algorithm_ref=provenance.get("algorithm_version"),
                ),
                acquired_at=acquired,
                observed_at=now,
                published_at=now,
                summary=ContinuousSummaryV1(
                    mean=_to_decimal(stats.get("mean")),
                    median=_to_decimal(stats.get("median")),
                    p10=_to_decimal(stats.get("p10")),
                    p90=_to_decimal(stats.get("p90")),
                    stddev=_to_decimal(stats.get("std")) or _to_decimal(stats.get("stddev")),
                    minimum=_to_decimal(stats.get("min")),
                    maximum=_to_decimal(stats.get("max")),
                ),
                observation_quality=ObservationQualityV1(
                    gate_status=gate,
                    policy=QualityPolicyRefV1(
                        policy_id=DEFAULT_POLICY_ID,
                        policy_version="1.0.0",
                        policy_hash=hashlib.sha256(
                            f"{DEFAULT_POLICY_ID}|1.0.0|anomaly_detection".encode()
                        ).hexdigest(),
                        use_case="anomaly_detection",
                    ),
                    field_coverage_ratio=coverage,
                    valid_pixel_ratio=valid,
                    field_cloud_ratio=cloud,
                    field_shadow_ratio=Decimal("0"),
                    indicator_in_range=True,
                    score=score,
                    reason_codes=tuple(item.get("index_quality_flags") or ()),
                ),
                uncertainty=ObservationUncertaintyV1(
                    method="quality-propagation-v1",
                    confidence=score if score is not None else valid,
                ),
                lineage=ObservationLineageV1(
                    asset_ref=f"urn:sahool:raster-asset:{asset_native}",
                    processing_run_ref=f"urn:sahool:processing-run:{run_native}",
                    input_hash=input_hash,
                    output_hash=output_hash,
                    pipeline_version="1.0.0",
                ),
                publication_status=PublicationStatus.PUBLISHED,
            )
        )
    return output


async def fetch_canonical_observations(
    *, field_id: str, tenant_id: UUID, season_id: str, indicators: list[str]
) -> list[CanonicalObservationV1]:
    if not RASTER_SERVICE_TOKEN:
        raise RuntimeError("RASTER_SERVICE_TOKEN/SAHOOL_AGENT_TOKEN is required")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/indicator-observation-bundle",
            params={"indices": ",".join(indicators), "date": "latest", "grid": 16},
            headers={"X-Tenant-Id": str(tenant_id), "X-Agent-Token": RASTER_SERVICE_TOKEN},
        )
    response.raise_for_status()
    bundle = response.json()
    if (
        not bundle.get("real_data")
        or bundle.get("mixed_scene")
        or not bundle.get("bundle_consistency")
    ):
        return []
    return canonicalize_bundle(bundle=bundle, tenant_id=tenant_id, season_id=season_id)
