"""Authoritative IRR-F01 target→path→resource/capability resolver.

Callers provide only an execution intent. Resource identities, policies, and capacities are
read inside the same transaction from v196/v171/v175; caller-supplied resource lists are not
an authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from api.irrigation_capacity_reservation import ResourcePolicy
from api.irrigation_path_query import PERSISTED_UPSTREAM_PATH_CTE, PathStatus
from api.irrigation_reservation_adapter import ResourceRequest

TARGET_SQL = """
SELECT b.terminal_node_id
FROM irrigation_target_bindings b
WHERE b.tenant_id=$1 AND b.project_id=$2 AND b.target_type=$3 AND b.target_id=$4
  AND b.target_version_id=$5 AND b.valid_from <= $6
  AND (b.valid_to IS NULL OR b.valid_to > $6)
"""
NODE_SQL = """
SELECT id,node_type,asset_ref FROM irrigation_hydraulic_nodes
WHERE tenant_id=$1 AND project_id=$2 AND id=ANY($3::uuid[])
"""
CAPABILITY_SQL = """
SELECT capability_id,status,operational_eligible,maximum_deliverable_flow_lps,
       capability_digest,payload
FROM canonical_hydraulic_capabilities
WHERE tenant_id=$1 AND project_id=$2 AND status IN ('verified','degraded')
  AND operational_eligible=true
ORDER BY created_at DESC LIMIT 1
"""


@dataclass(frozen=True, slots=True)
class ResolvedHydraulicIntent:
    terminal_node_id: UUID
    path_node_ids: tuple[UUID, ...]
    resources: tuple[ResourceRequest, ...]
    capability_id: str
    capability_digest: str


_POLICY_BY_NODE = {
    "valve": ResourcePolicy.EXCLUSIVE,
    "zone": ResourcePolicy.EXCLUSIVE,
    "machine_inlet": ResourcePolicy.EXCLUSIVE,
    "source": ResourcePolicy.SHARED_CAPACITY,
    "reservoir": ResourcePolicy.SHARED_CAPACITY,
    "pump": ResourcePolicy.SHARED_CAPACITY,
    "filter": ResourcePolicy.SHARED_CAPACITY,
    "junction": ResourcePolicy.SHARED_CAPACITY,
}


async def resolve_authoritative_intent(
    conn: Any,
    *,
    tenant_id: UUID,
    project_id: UUID,
    target_type: str,
    target_id: str,
    target_version_id: str,
    at_time: Any,
    requested_flow_m3h: Decimal,
) -> ResolvedHydraulicIntent:
    terminal = await conn.fetchval(
        TARGET_SQL, tenant_id, project_id, target_type, target_id, target_version_id, at_time
    )
    if terminal is None:
        raise ValueError("TARGET_BINDING_NOT_FOUND")
    rows = await conn.fetch(PERSISTED_UPSTREAM_PATH_CTE, tenant_id, project_id, terminal, 32)
    if any(bool(r["cycle"]) for r in rows):
        raise ValueError(PathStatus.INVALID_CYCLE.value)
    source_rows = [r for r in rows if r["node_type"] in ("source", "reservoir")]
    if not source_rows:
        raise ValueError(PathStatus.UNREACHABLE.value)
    paths = {tuple(reversed(tuple(r["path"]))) for r in source_rows}
    if len(paths) != 1:
        raise ValueError(PathStatus.MULTIPLE.value)
    path = next(iter(paths))
    nodes = await conn.fetch(NODE_SQL, tenant_id, project_id, list(path))
    by_id = {UUID(str(r["id"])): r for r in nodes}
    if len(by_id) != len(path):
        raise ValueError("PATH_NODE_MISSING")
    cap = await conn.fetchrow(CAPABILITY_SQL, tenant_id, project_id)
    if cap is None or cap["maximum_deliverable_flow_lps"] is None:
        raise ValueError("VERIFIED_CAPABILITY_NOT_FOUND")
    capacity = Decimal(str(cap["maximum_deliverable_flow_lps"])) * Decimal("3.6")
    resources = tuple(
        ResourceRequest(
            UUID(str(node_id)),
            _POLICY_BY_NODE[by_id[UUID(str(node_id))]["node_type"]],
            requested_flow_m3h,
            capacity,
        )
        for node_id in path
    )
    return ResolvedHydraulicIntent(
        UUID(str(terminal)),
        tuple(UUID(str(x)) for x in path),
        resources,
        str(cap["capability_id"]),
        str(cap["capability_digest"]),
    )
