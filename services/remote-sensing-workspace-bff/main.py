"""RS-9 single aggregation point for the remote-sensing field workspace."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query

app = FastAPI(title="SAHOOL Remote Sensing Workspace BFF", version="1.0.0")

INDICATORS_URL = os.getenv(
    "INDICATORS_SERVICE_URL", "http://sahool-indicators-service:8000"
).rstrip("/")
VEGETATION_URL = os.getenv(
    "VEGETATION_SERVICE_URL", "http://sahool-vegetation-analysis:8000"
).rstrip("/")
DECISION_URL = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
TASK_URL = os.getenv("TASK_SERVICE_URL", "").rstrip("/")
TIMEOUT = float(os.getenv("WORKSPACE_BFF_TIMEOUT_S", "6"))
_ALLOWED = {"overview", "timeline", "anomalies", "ground", "decisions", "compare", "outcomes"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "remote-sensing-workspace-bff"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    required = {
        "indicators": INDICATORS_URL,
        "vegetation": VEGETATION_URL,
        "decision": DECISION_URL,
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise HTTPException(
            503, detail={"code": "workspace_upstream_not_configured", "services": missing}
        )
    return {
        "status": "ready",
        "service": "remote-sensing-workspace-bff",
        "task_service_configured": bool(TASK_URL),
    }


async def _get(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.get(url, headers=headers, params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"upstream_{response.status_code}")
    return response.json()


@app.get("/v1/fields/{field_id}/remote-sensing-workspace")
async def workspace(
    field_id: str,
    season_id: str,
    include: str = Query(default="overview,timeline,anomalies,ground,decisions,compare,outcomes"),
    authorization: str = Header(..., alias="Authorization"),
    tenant_id: str = Header(..., alias="X-Tenant-Id"),
) -> dict[str, Any]:
    sections = {part.strip() for part in include.split(",") if part.strip()}
    unknown = sorted(sections - _ALLOWED)
    if unknown:
        raise HTTPException(422, detail={"code": "unknown_workspace_sections", "sections": unknown})
    if not tenant_id.strip() or len(tenant_id) > 128:
        raise HTTPException(400, detail={"code": "invalid_tenant_id"})
    if not field_id.strip() or len(field_id) > 128:
        raise HTTPException(400, detail={"code": "invalid_field_id"})
    headers = {"Authorization": authorization, "X-Tenant-Id": tenant_id}
    result: dict[str, Any] = {
        "field_id": field_id,
        "season_id": season_id,
        "sections": {},
        "partial": False,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        calls: dict[str, Any] = {}
        if "timeline" in sections or "overview" in sections or "compare" in sections:
            calls["timeline"] = _get(
                client,
                f"{INDICATORS_URL}/v1/fields/{field_id}/observation-timeline",
                headers,
                {"season_id": season_id},
            )
        if "anomalies" in sections or "overview" in sections or "ground" in sections:
            calls["anomalies"] = _get(
                client,
                f"{VEGETATION_URL}/v1/fields/{field_id}/signal-anomalies",
                headers,
                {"season_id": season_id},
            )
        if "decisions" in sections or "overview" in sections:
            calls["decisions"] = _get(
                client,
                f"{DECISION_URL}/v1/decisions",
                headers,
                {"field_id": field_id, "season_id": season_id, "limit": 100},
            )
        if "outcomes" in sections or "overview" in sections:
            calls["outcomes"] = _get(
                client,
                f"{DECISION_URL}/v1/outcomes/reconciled",
                headers,
                {"field_id": field_id, "season_id": season_id},
            )
        if "ground" in sections and TASK_URL:
            calls["ground"] = _get(
                client,
                f"{TASK_URL}/v1/tasks/scouting",
                headers,
                {"field_id": field_id, "season_id": season_id},
            )

        names = list(calls)
        values = await asyncio.gather(*(calls[name] for name in names), return_exceptions=True)
        raw: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, value in zip(names, values, strict=True):
            if isinstance(value, Exception):
                message = str(value)
                errors[name] = (
                    message if message.startswith("upstream_") else "upstream_unavailable"
                )
            else:
                raw[name] = value

    if "timeline" in sections:
        result["sections"]["timeline"] = raw.get("timeline", {"items": []})
    if "anomalies" in sections:
        result["sections"]["anomalies"] = raw.get("anomalies", {"anomalies": []})
    if "decisions" in sections:
        result["sections"]["decisions"] = raw.get("decisions", {"decisions": [], "count": 0})
    if "outcomes" in sections:
        result["sections"]["outcomes"] = raw.get("outcomes", {"outcomes": [], "count": 0})
    if "ground" in sections:
        if TASK_URL:
            result["sections"]["ground"] = raw.get("ground", {"items": []})
        else:
            result["sections"]["ground"] = {
                "configured": False,
                "items": [],
                "reason": "task_service_not_configured",
            }
    if "compare" in sections:
        timeline = raw.get("timeline", {})
        result["sections"]["compare"] = {
            "latest_observation_refs": timeline.get("latest_observation_refs", {}),
            "items": timeline.get("items", [])[:2],
        }
    if "overview" in sections:
        timeline = raw.get("timeline", {})
        anomalies = raw.get("anomalies", {}).get("anomalies", [])
        decisions = raw.get("decisions", {}).get("decisions", [])
        outcomes = raw.get("outcomes", {}).get("outcomes", [])
        result["sections"]["overview"] = {
            "latest_observation_refs": timeline.get("latest_observation_refs", {}),
            "observation_count": len(timeline.get("items", [])),
            "open_anomaly_count": sum(1 for item in anomalies if item.get("status") != "resolved"),
            "decision_count": len(decisions),
            "verified_outcome_count": len(outcomes),
        }
    if errors:
        result["partial"] = True
        result["errors"] = errors
    return result
