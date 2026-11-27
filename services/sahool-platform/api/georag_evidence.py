"""api/georag_evidence.py — bounded spatial GeoRAG scoping for the unified decision.

Retrieval stays owned by ``core.rag.production_qdrant`` / ``services/rag-retrieval`` (tenant
scoped, provenance-checked, annotation-only). This module adds only what retrieval lacks:
a field/geometry scope check on the annotations it returned, and a fail-closed envelope the
unified decision can carry. It never computes a recommendation, never raises an annotation
to evidence, and grants no execution authority. Missing, unscoped, foreign or unprovenanced
annotations are rejected with a reason, never completed by guessing.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any

import httpx
from fastapi import HTTPException

SCHEMA = "sahool.georag_evidence.v1"
GLOBAL_REFERENCE_TENANT = "__global__"
_PROVENANCE = ("source_uri", "source_revision", "content_digest")
_UNAVAILABLE = "georag_retrieval_unavailable"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _coords_finite(node: Any) -> bool:
    if isinstance(node, (list, tuple)):
        return all(_coords_finite(n) for n in node)
    return isinstance(node, (int, float)) and not isinstance(node, bool) and math.isfinite(node)


def parse_geometry(geom: Any):
    """GeoJSON Polygon/MultiPolygon → valid non-empty shapely geometry, else None."""
    if not isinstance(geom, dict) or geom.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    if not _coords_finite(geom.get("coordinates")):
        return None
    try:
        from shapely.geometry import shape

        g = shape(geom)
    except Exception:  # noqa: BLE001 — any malformed geometry is simply invalid
        return None
    if g.is_empty or not g.is_valid or g.area <= 0:
        return None
    return g


def geometry_digest(geom: Any) -> str | None:
    return _digest(geom) if parse_geometry(geom) is not None else None


def _reject(ann: dict, reason: str) -> dict:
    return {"chunk_id": ann.get("chunk_id") if isinstance(ann, dict) else None, "reason": reason}


def _classify(ann: Any, tenant_id: str, field_id: str, field_geom) -> tuple[str | None, str]:
    """→ (rejection reason | None, spatial_match)."""
    if not isinstance(ann, dict):
        return "annotation_malformed", ""
    if ann.get("decision_authority") != "none" or ann.get("verified") is not False:
        return "annotation_claims_authority", ""
    ann_tenant = ann.get("tenant_id")
    is_global = ann_tenant == GLOBAL_REFERENCE_TENANT
    if not is_global and ann_tenant != tenant_id:
        return "tenant_scope_mismatch", ""
    if any(not str(ann.get(k) or "").strip() for k in _PROVENANCE):
        return "provenance_incomplete", ""
    scope = ann.get("spatial_scope")
    if not isinstance(scope, dict) or not scope:
        if is_global:
            return None, "general_reference"
        return "spatial_scope_missing", ""
    if scope.get("field_id") is not None and scope["field_id"] != field_id:
        return "field_scope_mismatch", ""
    if scope.get("geometry") is not None:
        if field_geom is None:
            return "field_geometry_invalid", ""
        g = parse_geometry(scope["geometry"])
        if g is None:
            return "annotation_geometry_invalid", ""
        if not g.relate_pattern(field_geom, "T********"):
            return "geometry_disjoint", ""
        return None, "geometry_intersects"
    if scope.get("field_id") == field_id:
        return None, "field_id"
    return "spatial_scope_missing", ""


def scope_annotations(
    annotations: list[Any] | None,
    *,
    tenant_id: str,
    field_id: str,
    field_geometry: Any,
    zone_id: str | None = None,
    retrieval_error: str | None = None,
) -> dict[str, Any]:
    field_geom = parse_geometry(field_geometry)
    admitted: list[dict] = []
    rejected: list[dict] = []
    reasons: list[str] = []
    if retrieval_error:
        reasons.append(retrieval_error)
    if field_geom is None:
        reasons.append("field_geometry_invalid")
    for ann in annotations or []:
        why, match = _classify(ann, tenant_id, field_id, field_geom)
        if why:
            rejected.append(_reject(ann, why))
        else:
            admitted.append({**ann, "spatial_match": match})
    if not annotations and not retrieval_error:
        reasons.append("no_annotations")
    if annotations and not admitted:
        reasons.append("no_annotation_in_scope")
    spatial = field_geom is not None and any(
        ann["spatial_match"] != "general_reference" for ann in admitted
    )
    if admitted and not spatial and field_geom is not None:
        reasons.append("no_spatial_annotation")
    body = {
        "schema": SCHEMA,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "zone_id": zone_id,
        "field_geometry_digest": geometry_digest(field_geometry),
        "status": "evidence_available" if spatial and not retrieval_error else "evidence_required",
        "annotations": admitted,
        "rejected": rejected,
        "reason_codes": sorted(set(reasons)),
        "decision_authority": "none",
        "direct_execution_permitted": False,
        "annotation_only": True,
    }
    return {**body, "evidence_digest": _digest(body)}


def envelope_valid(envelope: Any) -> bool:
    """A supplied envelope is trusted only if it is ours and its digest recomputes."""
    if not isinstance(envelope, dict) or envelope.get("schema") != SCHEMA:
        return False
    body = {k: v for k, v in envelope.items() if k != "evidence_digest"}
    return (
        envelope.get("evidence_digest") == _digest(body)
        and envelope.get("decision_authority") == "none"
        and envelope.get("direct_execution_permitted") is False
    )


def not_supplied_envelope(reason: str) -> dict[str, Any]:
    body = {
        "schema": SCHEMA,
        "status": "evidence_required",
        "annotations": [],
        "rejected": [],
        "reason_codes": [reason],
        "decision_authority": "none",
        "direct_execution_permitted": False,
        "annotation_only": True,
    }
    return {**body, "evidence_digest": _digest(body)}


def fetch_annotations(
    base_url: str | None = None,
    *,
    tenant_id: str,
    field_id: str,
    query: str,
    crop: str | None = None,
    region: str | None = None,
    final_k: int = 5,
    headers: dict[str, str] | None = None,
    timeout_s: float = 5.0,
) -> tuple[list[dict], str | None]:
    """POST rag-retrieval ``/v1/search``; any failure → ([], reason) — never raises."""
    if base_url is None:
        base_url = os.getenv("RAG_RETRIEVAL_URL", "http://sahool-rag-retrieval:8000")
    try:
        response = httpx.post(
            base_url.rstrip("/") + "/v1/search",
            json={
                "tenant_id": tenant_id,
                "field_id": field_id,
                "query": query,
                "crop": crop,
                "region": region,
                "final_k": final_k,
            },
            headers={"X-Tenant-Id": tenant_id, **(headers or {})},
            timeout=timeout_s,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return [], _UNAVAILABLE
    rows = payload.get("annotations") if isinstance(payload, dict) else None
    return (rows, None) if isinstance(rows, list) else ([], _UNAVAILABLE)


async def field_at_point(
    conn, tenant_id: str, longitude: float, latitude: float
) -> tuple[str, dict]:
    """Resolve a unique stored field polygon under the authenticated tenant transaction."""
    rows = await conn.fetch(
        """SELECT field_id, ST_AsGeoJSON(geom, 15) AS geometry
             FROM fields
            WHERE tenant_id = $1::uuid
              AND GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')
              AND ST_IsValid(geom)
              AND ST_Covers(geom, ST_SetSRID(ST_MakePoint($2, $3), 4326))
            LIMIT 2""",
        tenant_id,
        longitude,
        latitude,
    )
    if not rows:
        raise HTTPException(404, "georag_point_outside_fields")
    if len(rows) != 1:
        raise HTTPException(409, "georag_point_matches_multiple_fields")
    return rows[0]["field_id"], json.loads(rows[0]["geometry"])
