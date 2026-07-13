"""Publish approved laboratory evidence to soil-service's canonical evidence boundary."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

_ANALYTE_MAP = {
    "ph": ("ph", "1"),
    "ec_dsm": ("electrical_conductivity", "dS/m"),
    "organic_matter_pct": ("organic_matter", "%"),
    "nitrogen_mg_kg": ("nitrogen", "mg/kg"),
    "phosphorus_mg_kg": ("phosphorus", "mg/kg"),
    "potassium_mg_kg": ("potassium", "mg/kg"),
    "cec_cmol_kg": ("cec", "cmol(+)/kg"),
    "calcium_carbonate_pct": ("calcium_carbonate", "%"),
    "texture": ("texture_class", None),
}


async def publish_soil_lab_evidence(
    *,
    tenant_id: str,
    field_id: str,
    sample: dict[str, Any],
    results: dict[str, Any],
    result_rows: list[dict[str, Any]] | None = None,
    correction_reason: str | None = None,
) -> dict[str, Any]:
    # Canonical default must match compose/service_proxy/field_intelligence_adapters
    # (sahool-soil-service:8000). The old "soil-service:8134" default was only masked
    # because SOIL_SERVICE_URL is always set in compose; unset, it dialed a dead host.
    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000").rstrip("/")
    token = (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("SOIL_SERVICE_TOKEN")
        or os.getenv("SAHOOL_AGENT_TOKEN")
    )
    if not token:
        raise RuntimeError(
            "INTERNAL_SERVICE_TOKEN/SOIL_SERVICE_TOKEN/SAHOOL_AGENT_TOKEN is required"
        )
    properties: dict[str, Any] = {}
    units: dict[str, str] = {}
    for source_name, (canonical, unit) in _ANALYTE_MAP.items():
        value = results.get(source_name)
        if value is not None:
            properties[canonical] = value
            if unit:
                units[canonical] = unit
    if not properties:
        raise RuntimeError("no publishable soil analytes")
    supersedes_observation_ids: dict[str, str] = {}
    result_by_canonical: dict[str, str] = {}
    for row in result_rows or []:
        mapped = _ANALYTE_MAP.get(row.get("analyte"))
        if not mapped:
            continue
        canonical = mapped[0]
        result_by_canonical[canonical] = str(row.get("result_id"))
        prior = row.get("supersedes_result_id")
        if prior:
            prior_observation = row.get("superseded_published_observation_id")
            if prior_observation:
                supersedes_observation_ids[canonical] = prior_observation
    payload = {
        "source_type": "laboratory",
        "source_id": sample["sample_id"],
        "properties": properties,
        "observed_at": datetime.now(UTC).isoformat(),
        "depth_from_cm": float(sample.get("depth_cm_from") or 0),
        "depth_to_cm": float(sample.get("depth_cm_to") or 30),
        "approved": True,
        "procedure_id": "platform-lab-workflow.v1",
        "supersedes_observation_ids": supersedes_observation_ids,
        "supersession_reason": correction_reason,
        "provenance": {
            "sample_id": sample["sample_id"],
            "units": units,
            "workflow_status": "published",
        },
    }
    headers = {"X-Agent-Token": token, "X-Tenant-Id": tenant_id}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base}/v1/fields/{field_id}/soil/evidence", json=payload, headers=headers
        )
    response.raise_for_status()
    receipt = response.json()
    receipt["result_by_canonical"] = result_by_canonical
    return receipt
