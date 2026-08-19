"""Validated stage/DAG receipt contract for raster workflows.

This is not a new scheduler. It is a deterministic execution contract used by
existing raster workers to prove graph validity, dependency completion, input/
output lineage, and tamper-evident receipts before a stage is allowed to run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA = "sahool.raster-stage-receipt.v2"
GRAPH_SCHEMA = "sahool.raster-stage-graph.v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _digest(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, default=str, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    stage_version: str
    dependency_stage_ids: tuple[str, ...] = ()


def build_stage_graph(specs: list[StageSpec | dict[str, Any]]) -> dict[str, Any]:
    """Validate a stage DAG and return deterministic topological order + digest."""
    if not specs:
        raise ValueError("raster stage graph requires at least one stage")
    normalized: dict[str, dict[str, Any]] = {}
    for raw in specs:
        if isinstance(raw, StageSpec):
            stage_id = raw.stage_id
            stage_version = raw.stage_version
            deps = list(raw.dependency_stage_ids)
        elif isinstance(raw, dict):
            stage_id = str(raw.get("stage_id") or "")
            stage_version = str(raw.get("stage_version") or "")
            deps = [str(v) for v in (raw.get("dependency_stage_ids") or []) if str(v)]
        else:
            raise ValueError("invalid raster stage spec")
        if not stage_id or not stage_version:
            raise ValueError("stage_id and stage_version are required")
        if stage_id in normalized:
            raise ValueError(f"duplicate raster stage_id: {stage_id}")
        deps = list(dict.fromkeys(deps))
        if stage_id in deps:
            raise ValueError(f"raster stage cannot depend on itself: {stage_id}")
        normalized[stage_id] = {
            "stage_id": stage_id,
            "stage_version": stage_version,
            "dependency_stage_ids": deps,
        }
    unknown = sorted(
        {
            d
            for row in normalized.values()
            for d in row["dependency_stage_ids"]
            if d not in normalized
        }
    )
    if unknown:
        raise ValueError(f"raster stage graph has unknown dependencies: {unknown}")

    indegree = {sid: 0 for sid in normalized}
    followers: dict[str, list[str]] = {sid: [] for sid in normalized}
    for sid, row in normalized.items():
        for dep in row["dependency_stage_ids"]:
            indegree[sid] += 1
            followers[dep].append(sid)
    ready = sorted(sid for sid, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        sid = ready.pop(0)
        order.append(sid)
        for nxt in sorted(followers[sid]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort()
    if len(order) != len(normalized):
        raise ValueError("raster stage graph contains a cycle")

    stage_rows = [normalized[sid] for sid in sorted(normalized)]
    graph = {
        "schema": GRAPH_SCHEMA,
        "stages": stage_rows,
        "topological_order": order,
    }
    graph["graph_digest"] = _digest(graph)
    return graph


def verify_stage_graph(graph: dict[str, Any]) -> bool:
    if not isinstance(graph, dict) or graph.get("schema") != GRAPH_SCHEMA:
        raise ValueError("invalid raster stage graph schema")
    claimed = str(graph.get("graph_digest") or "")
    raw = {k: v for k, v in graph.items() if k != "graph_digest"}
    if claimed != _digest(raw):
        raise ValueError("raster stage graph digest mismatch")
    rebuilt = build_stage_graph(list(graph.get("stages") or []))
    if rebuilt["graph_digest"] != claimed or rebuilt["topological_order"] != graph.get(
        "topological_order"
    ):
        raise ValueError("raster stage graph canonical form mismatch")
    return True


def verify_receipt(receipt: dict[str, Any]) -> bool:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("invalid raster stage receipt schema")
    if receipt.get("status") not in {"completed", "failed"}:
        raise ValueError("only terminal raster stage receipts are verifiable")
    claimed = str(receipt.get("receipt_digest") or "")
    raw = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    if claimed != _digest(raw):
        raise ValueError("raster stage receipt digest mismatch")
    return True


def _stage_spec(graph: dict[str, Any], stage_id: str) -> dict[str, Any]:
    verify_stage_graph(graph)
    for row in graph["stages"]:
        if row["stage_id"] == stage_id:
            return row
    raise ValueError(f"stage {stage_id!r} is not declared in raster stage graph")


def begin_stage(
    *,
    stage_id: str,
    stage_version: str,
    run_id: str,
    config: dict[str, Any],
    dependency_stage_ids: list[str] | None = None,
    input_refs: list[str] | None = None,
    stage_graph: dict[str, Any] | None = None,
    dependency_receipts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not stage_id or not stage_version or not run_id:
        raise ValueError("stage_id, stage_version and run_id are required")
    deps = list(dict.fromkeys(dependency_stage_ids or []))
    refs = [str(v) for v in (input_refs or []) if str(v)]
    graph = stage_graph or build_stage_graph(
        [
            StageSpec(
                stage_id=stage_id, stage_version=stage_version, dependency_stage_ids=tuple(deps)
            )
        ]
    )
    spec = _stage_spec(graph, stage_id)
    if spec["stage_version"] != stage_version or spec["dependency_stage_ids"] != deps:
        raise ValueError("stage invocation does not match declared raster stage graph")

    dependency_receipts = dependency_receipts or {}
    if set(dependency_receipts) != set(deps):
        missing = sorted(set(deps) - set(dependency_receipts))
        extra = sorted(set(dependency_receipts) - set(deps))
        if missing or extra:
            raise ValueError(
                f"dependency receipt identity mismatch: missing={missing} extra={extra}"
            )
    upstream_refs: list[str] = []
    upstream_digests: list[str] = []
    for dep in deps:
        receipt = dependency_receipts[dep]
        verify_receipt(receipt)
        if receipt.get("stage_id") != dep or receipt.get("run_id") != run_id:
            raise ValueError(f"dependency receipt {dep} belongs to another stage/run")
        if receipt.get("status") != "completed":
            raise ValueError(f"dependency stage {dep} did not complete successfully")
        upstream_refs.extend(str(v) for v in (receipt.get("output_refs") or []) if str(v))
        upstream_digests.append(str(receipt["receipt_digest"]))
    if upstream_refs and not set(upstream_refs).issubset(set(refs)):
        raise ValueError("stage input_refs do not carry all upstream output refs")

    return {
        "schema": SCHEMA,
        "stage_id": stage_id,
        "stage_version": stage_version,
        "run_id": run_id,
        "graph_digest": graph["graph_digest"],
        "config_digest": _digest(config),
        "dependency_stage_ids": deps,
        "dependency_receipt_digests": upstream_digests,
        "input_refs": refs,
        "input_set_digest": _digest(refs),
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "output_refs": [],
        "output_set_digest": None,
        "error_class": None,
    }


def finish_stage(
    receipt: dict[str, Any], *, output_refs: list[str] | None = None
) -> dict[str, Any]:
    if receipt.get("status") != "running":
        raise ValueError("only running stage receipts can finish")
    out = dict(receipt)
    refs = [str(v) for v in (output_refs or []) if str(v)]
    out.update(
        {
            "status": "completed",
            "finished_at": _now(),
            "output_refs": refs,
            "output_set_digest": _digest(refs),
        }
    )
    out["receipt_digest"] = _digest({k: v for k, v in out.items() if k != "receipt_digest"})
    return out


def fail_stage(receipt: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    if receipt.get("status") != "running":
        raise ValueError("only running stage receipts can fail")
    out = dict(receipt)
    out.update(
        {
            "status": "failed",
            "finished_at": _now(),
            "error_class": type(exc).__name__,
            "output_refs": [],
            "output_set_digest": _digest([]),
        }
    )
    out["receipt_digest"] = _digest({k: v for k, v in out.items() if k != "receipt_digest"})
    return out
