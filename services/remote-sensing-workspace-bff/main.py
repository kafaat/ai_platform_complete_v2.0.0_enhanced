"""RS-9 single aggregation point for the remote-sensing field workspace."""

from __future__ import annotations

import asyncio
import os

# Identifiers travel into internal upstream URLs; constrain them so an encoded
# "?"/"#"/"/" can never rewrite the upstream path or query.
import re
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query

from shared.security.decision_service_auth import (
    DecisionServiceAuthUnavailable,
    decision_service_auth_headers,
)

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

app = FastAPI(title="SAHOOL Remote Sensing Workspace BFF", version="1.0.0")

INDICATORS_URL = os.getenv(
    "INDICATORS_SERVICE_URL", "http://sahool-indicators-service:8000"
).rstrip("/")
VEGETATION_URL = os.getenv(
    "VEGETATION_SERVICE_URL", "http://sahool-vegetation-analysis:8000"
).rstrip("/")
DECISION_URL = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
PLATFORM_URL = os.getenv("PLATFORM_API_URL", "http://sahool-platform:8000").rstrip("/")
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
        "platform": PLATFORM_URL,
    }
    missing = sorted(name for name, value in required.items() if not value)
    try:
        decision_service_auth_headers()
    except DecisionServiceAuthUnavailable:
        missing.append("decision_auth")
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


async def _workspace_identity(
    client: httpx.AsyncClient, authorization: str, requested_tenant: str
) -> str:
    """Ask the existing session/RBAC owner before using internal service authority.

    Never mint a trusted tenant header from the caller's X-Tenant-Id. The
    permission list is computed by the platform's canonical has_permission.
    """
    try:
        response = await client.get(
            f"{PLATFORM_URL}/api/v1/auth/me", headers={"Authorization": authorization}
        )
        if response.status_code in {401, 403}:
            raise HTTPException(response.status_code, detail="workspace_access_denied")
        response.raise_for_status()
        user = response.json()["user"]
        tenant = user["tenant_id"]
        permissions = user["permissions"]
        if not isinstance(tenant, str) or not _ID_RE.fullmatch(tenant):
            raise ValueError("invalid trusted tenant")
        if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
            raise ValueError("invalid permission projection")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, detail="workspace_identity_unavailable") from exc
    if tenant != requested_tenant or "recommendation:view" not in permissions:
        raise HTTPException(403, detail="workspace_access_denied")
    return tenant


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
    if not authorization.strip() or len(authorization) > 8192:
        raise HTTPException(400, detail={"code": "invalid_authorization"})
    if not _ID_RE.fullmatch(tenant_id):
        raise HTTPException(400, detail={"code": "invalid_tenant_id"})
    if not _ID_RE.fullmatch(field_id):
        raise HTTPException(400, detail={"code": "invalid_field_id"})
    if not _ID_RE.fullmatch(season_id):
        raise HTTPException(400, detail={"code": "invalid_season_id"})
    result: dict[str, Any] = {
        "field_id": field_id,
        "season_id": season_id,
        "sections": {},
        "partial": False,
    }

    # Internal service DNS must not be redirected through ambient HTTP/SOCKS
    # proxy variables. This also keeps tenant-scoped upstream traffic inside
    # the SAHOOL network boundary.
    async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
        tenant = await _workspace_identity(client, authorization, tenant_id)
        headers = {"Authorization": authorization, "X-Tenant-Id": tenant}
        decision_headers: dict[str, str] = {}
        if sections & {"decisions", "outcomes", "overview"}:
            try:
                decision_headers = {**decision_service_auth_headers(), "X-Tenant-Id": tenant}
            except DecisionServiceAuthUnavailable as exc:
                raise HTTPException(503, detail=str(exc)) from exc
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
                decision_headers,
                {"field_id": field_id, "season_id": season_id, "limit": 100},
            )
        if "outcomes" in sections or "overview" in sections:
            calls["outcomes"] = _get(
                client,
                f"{DECISION_URL}/v1/outcomes/reconciled",
                decision_headers,
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
        result["sections"]["timeline"] = raw.get("timeline", {"entries": []})
    if "anomalies" in sections:
        result["sections"]["anomalies"] = raw.get("anomalies", {"anomalies": []})
    if "decisions" in sections:
        result["sections"]["decisions"] = raw.get("decisions", {"decisions": [], "count": 0})
    if "outcomes" in sections:
        result["sections"]["outcomes"] = raw.get("outcomes", {"outcome_reconciliation": {}})
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
            "items": timeline.get("entries", [])[:2],
        }
    if "overview" in sections:
        timeline = raw.get("timeline", {})
        anomalies = raw.get("anomalies", {}).get("anomalies", [])
        decisions = raw.get("decisions", {}).get("decisions", [])

        result["sections"]["overview"] = {
            "latest_observation_refs": timeline.get("latest_observation_refs", {}),
            "observation_count": len(timeline.get("entries", [])),
            "open_anomaly_count": sum(1 for item in anomalies if item.get("status") != "resolved"),
            # field-wide today: upstream /v1/decisions has no season filter yet;
            # season_id is forwarded for forward-compatibility.
            "decision_count": len(decisions),
            "outcome_reconciliation_available": bool(
                raw.get("outcomes", {}).get("outcome_reconciliation")
            ),
        }
    if errors:
        result["partial"] = True
        result["errors"] = errors
    return result
