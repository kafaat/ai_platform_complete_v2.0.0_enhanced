#!/usr/bin/env python3
"""Guard the direct-Qdrant runtime boundary during RAG authority convergence.

The guard is deliberately narrower than a repository-wide ``qdrant`` grep.  Qdrant
is legitimately used by the canonical retrieval service, the bootstrap seed job,
and operational snapshot tooling.  The authority-sensitive risk is a *runtime
knowledge service* that can answer retrieval requests by talking to Qdrant directly
outside ``rag-retrieval``.

The convergence contract names exactly one temporary exception (``local-ai-rag``)
while the system is in EXPAND/PARITY.  A new direct runtime consumer is a failure;
a cutover/revoked state is also a failure while that exception remains wired.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

_SOURCE_MARKERS = (
    "QdrantVectorStore",
    "QdrantHttpClient(",
    "QdrantClient(",
    "AsyncQdrantClient(",
    "from qdrant_client",
    "import qdrant_client",
    "langchain_qdrant",
)


@dataclass(frozen=True)
class DirectConsumer:
    component_id: str
    component_kind: str
    authority_kind: str
    source_path: str
    deployment_units: tuple[str, ...]
    source_direct: bool
    deployment_direct: bool
    role: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_has_direct_qdrant(root: Path, source_path: str) -> bool:
    base = root / source_path
    if not base.exists():
        return False
    candidates: list[Path] = []
    if base.is_file():
        candidates = [base]
    else:
        for pattern in ("*.py", "requirements*.txt", "pyproject.toml"):
            candidates.extend(base.rglob(pattern))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(marker in text for marker in _SOURCE_MARKERS):
            return True
    return False


def _deployment_has_direct_qdrant(service: dict[str, Any]) -> bool:
    env = service.get("environment") or {}
    if isinstance(env, list):
        keys = {str(v).split("=", 1)[0] for v in env}
    else:
        keys = {str(k) for k in env}
    if any(k.startswith("QDRANT_") for k in keys):
        return True
    depends = service.get("depends_on") or {}
    if isinstance(depends, list):
        return "sahool-qdrant" in depends
    return "sahool-qdrant" in depends


def inventory(root: Path = ROOT, state: dict[str, Any] | None = None) -> list[DirectConsumer]:
    state = state or _load_json(root / "docs/architecture/rag_authority_convergence.json")
    registry = _load_json(root / "docs/architecture/component_registry.json")["components"]
    compose = yaml.safe_load((root / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]

    unit_to_component: dict[str, str] = {}
    for component_id, spec in registry.items():
        for unit in spec.get("deployment_units") or []:
            unit_to_component[str(unit)] = component_id

    intended = str(state.get("intended_retrieval_authority") or "")
    exception = str((state.get("direct_qdrant_exception") or {}).get("component_id") or "")
    rows: list[DirectConsumer] = []

    for component_id, spec in sorted(registry.items()):
        source_path = str(spec.get("source_path") or "")
        units = tuple(str(v) for v in (spec.get("deployment_units") or []))
        source_direct = _source_has_direct_qdrant(root, source_path)
        deployment_direct = any(
            _deployment_has_direct_qdrant(compose[unit]) for unit in units if unit in compose
        )
        if not (source_direct or deployment_direct):
            continue

        kind = str(spec.get("component_kind") or "")
        authority = str(spec.get("authority_kind") or "")
        if component_id == intended:
            role = "canonical_retrieval"
        elif component_id == exception:
            role = "temporary_response_path_exception"
        elif kind == "init_job":
            role = "bootstrap_writer"
        else:
            role = "unauthorized_runtime_direct"
        rows.append(
            DirectConsumer(
                component_id=component_id,
                component_kind=kind,
                authority_kind=authority,
                source_path=source_path,
                deployment_units=units,
                source_direct=source_direct,
                deployment_direct=deployment_direct,
                role=role,
            )
        )

    # A deployment that is wired to Qdrant but not mapped into the component registry is
    # itself a governance gap.  Ignore the infrastructure server, which is not a consumer.
    mapped_units = set(unit_to_component)
    for unit, service in sorted(compose.items()):
        if unit == "sahool-qdrant" or unit in mapped_units:
            continue
        if _deployment_has_direct_qdrant(service):
            rows.append(
                DirectConsumer(
                    component_id=f"UNREGISTERED:{unit}",
                    component_kind="unregistered",
                    authority_kind="unknown",
                    source_path="",
                    deployment_units=(unit,),
                    source_direct=False,
                    deployment_direct=True,
                    role="unauthorized_runtime_direct",
                )
            )
    return rows


def findings(root: Path = ROOT, state: dict[str, Any] | None = None) -> list[str]:
    state = state or _load_json(root / "docs/architecture/rag_authority_convergence.json")
    rows = inventory(root, state)
    out: list[str] = []
    stage = str(state.get("stage") or "")
    intended = str(state.get("intended_retrieval_authority") or "")
    exc = state.get("direct_qdrant_exception") or {}
    exception = str(exc.get("component_id") or "")

    canonical = [r for r in rows if r.component_id == intended]
    if len(canonical) != 1:
        out.append(
            f"canonical retrieval direct-Qdrant consumer must resolve exactly once: {intended}"
        )

    for row in rows:
        if row.role == "unauthorized_runtime_direct":
            out.append(f"unauthorized direct Qdrant runtime consumer: {row.component_id}")
        if row.role == "bootstrap_writer":
            if row.authority_kind != "stateless_compute":
                out.append(
                    f"Qdrant bootstrap job must not own domain authority: {row.component_id}"
                )
            if row.component_kind != "init_job":
                out.append(f"Qdrant bootstrap allowance requires init_job: {row.component_id}")

    if stage in {"expand_shadow", "parity"}:
        if not exception:
            out.append("pre-cutover state must name the temporary direct-Qdrant exception")
        exception_rows = [r for r in rows if r.component_id == exception]
        if len(exception_rows) != 1:
            out.append(f"temporary direct-Qdrant exception must resolve exactly once: {exception}")
        elif exception_rows[0].role != "temporary_response_path_exception":
            out.append(f"temporary direct-Qdrant exception role mismatch: {exception}")
    elif stage in {"cutover", "revoked"}:
        if exception:
            out.append("direct_qdrant_exception must be removed after cutover")
        for row in rows:
            if row.component_id != intended and row.component_kind != "init_job":
                out.append(f"post-cutover direct Qdrant response path remains: {row.component_id}")
    else:
        out.append(f"unknown convergence stage: {stage!r}")

    policy = state.get("direct_qdrant_policy") or {}
    if policy.get("canonical_component") != intended:
        out.append("direct_qdrant_policy canonical_component must match intended authority")
    if policy.get("bootstrap_component_kind") != "init_job":
        out.append("direct_qdrant_policy bootstrap_component_kind must be init_job")
    if policy.get("new_runtime_exceptions_forbidden") is not True:
        out.append("direct_qdrant_policy must forbid new runtime exceptions")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = inventory(args.root)
    errs = findings(args.root)
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "sahool.rag-direct-qdrant-boundary/v1",
                    "status": "PASS" if not errs else "FAIL",
                    "consumers": [asdict(r) for r in rows],
                    "findings": errs,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for row in rows:
            print(
                "rag_direct_qdrant_consumer",
                row.component_id,
                f"role={row.role}",
                f"source={int(row.source_direct)}",
                f"deployment={int(row.deployment_direct)}",
            )
        for err in errs:
            print("rag_direct_qdrant_boundary_fail", err)
        if not errs:
            print(f"rag_direct_qdrant_boundary_ok consumers={len(rows)}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
