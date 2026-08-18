#!/usr/bin/env python3
"""Read-only S4 KG live parity collector with deployed-source binding.

The receipt is evidence only.  It never mutates graph state and never promotes authority.
A PASS requires: the canonical service is ready, its shipped source digests match the reviewed
checkout, every governed case returns at least its declared minimum evidence, and REST/GraphQL
normalize to the same edge set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/s4_kg_consumer_freeze.json"
DEFAULT_CASES = ROOT / "docs/architecture/evidence/s4_kg_parity_cases.json"
MAIN = ROOT / "services/knowledge-graph/main.py"
STORE = ROOT / "services/knowledge-graph/kg_store.py"
GATEWAY = ROOT / "shared/security/gateway_deps.py"
SCHEMA = "sahool.s4-kg-runtime-parity/v2"
_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
_HEX = re.compile(r"^[0-9a-fA-F]+$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None) -> Any:
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def norm(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("edge_id", "subject_id", "relation", "object_id", "confidence", "prescriptive")
    return sorted(
        [{k: edge.get(k) for k in keys} for edge in edges],
        key=lambda row: tuple(str(row.get(k, "")) for k in keys),
    )


def _edges(payload: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("edges"), list):
        raise ValueError(f"{source}_response_shape_invalid")
    if not all(isinstance(edge, dict) for edge in payload["edges"]):
        raise ValueError(f"{source}_edges_shape_invalid")
    return payload["edges"]


def _cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("parity_cases_must_be_non_empty_list")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("parity_case_shape_invalid")
        subject = item.get("subject_id")
        relation = item.get("relation")
        if not isinstance(subject, str) or not _ID.fullmatch(subject):
            raise ValueError("parity_case_subject_invalid")
        if relation is not None and (not isinstance(relation, str) or not _ID.fullmatch(relation)):
            raise ValueError("parity_case_relation_invalid")
        minimum = item.get("min_edges")
        if not isinstance(minimum, int) or minimum < 1:
            raise ValueError("parity_case_min_edges_must_be_positive")
        key = (subject, relation)
        if key in seen:
            raise ValueError("duplicate_parity_case")
        seen.add(key)
        out.append({"subject_id": subject, "relation": relation, "min_edges": minimum})
    return out


def expected_source_identity() -> dict[str, str]:
    return {
        "main_sha256": sha256_file(MAIN),
        "kg_store_sha256": sha256_file(STORE),
        "gateway_deps_sha256": sha256_file(GATEWAY),
    }


def local_subject_sha() -> str:
    """Return the exact checkout commit used to compute expected source digests.

    The live receipt is not subject-bound if ``--subject-sha`` is merely operator text.  The
    deployed service is therefore compared to source digests from a real Git checkout whose HEAD
    must equal the supplied subject.  Delivery ZIPs intentionally have no ``.git`` and must not be
    used as provenance-bearing live collectors.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    sha = (proc.stdout or "").strip().lower()
    if proc.returncode != 0 or len(sha) != 40 or not _HEX.fullmatch(sha):
        raise ValueError("live_collector_requires_real_git_checkout")
    return sha


def collect(*, base_url: str, tenant_id: str, subject_sha: str, cases_path: Path) -> dict[str, Any]:
    if len(subject_sha) not in (40, 64) or not _HEX.fullmatch(subject_sha):
        raise ValueError("subject_sha_must_be_full_hex_commit_or_digest")
    if not tenant_id.strip():
        raise ValueError("tenant_id_required")

    local_sha = local_subject_sha()
    if local_sha != subject_sha.lower():
        raise ValueError("checkout_subject_sha_mismatch")

    base = base_url.rstrip("/")
    headers = {"X-Tenant-Id": tenant_id, "Content-Type": "application/json"}
    cases = _cases(cases_path)
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    expected_identity = expected_source_identity()

    ready = get_json(base + "/readyz")
    if not isinstance(ready, dict):
        raise ValueError("ready_response_shape_invalid")
    live_identity = ready.get("source_identity")
    identity_match = live_identity == expected_identity
    ready_ok = ready.get("status") == "ready" and ready.get("service") == "knowledge-graph"

    results: list[dict[str, Any]] = []
    all_cases_pass = True
    for case in cases:
        subject = case["subject_id"]
        relation = case.get("relation")
        query = {"subject_id": subject}
        if relation:
            query["relation"] = relation
        rest = _edges(get_json(base + "/v1/edges?" + urllib.parse.urlencode(query), headers), "rest")
        gql = 'query { edges(subject:"%s"%s) { edge_id subject_id relation object_id confidence prescriptive } }' % (
            subject,
            ', relation:"%s"' % relation if relation else "",
        )
        graph = _edges(
            get_json(base + "/graphql", headers, json.dumps({"query": gql}).encode("utf-8")),
            "graphql",
        )
        nrest = norm(rest)
        ngraph = norm(graph)
        parity = nrest == ngraph
        minimum_met = len(nrest) >= case["min_edges"] and len(ngraph) >= case["min_edges"]
        passed = parity and minimum_met
        all_cases_pass = all_cases_pass and passed
        results.append(
            {
                "case": case,
                "rest_count": len(rest),
                "graphql_count": len(graph),
                "parity": parity,
                "minimum_evidence_met": minimum_met,
                "status": "PASSED" if passed else "FAILED",
                "edge_digest": hashlib.sha256(
                    json.dumps(nrest, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            }
        )

    passed = ready_ok and identity_match and all_cases_pass
    return {
        "schema": SCHEMA,
        "subject_sha": subject_sha.lower(),
        "local_subject_sha": local_sha,
        "local_subject_match": True,
        "status": "PASSED" if passed else "FAILED",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "authority_promotion": False,
        "service": "knowledge-graph",
        "ready": {"status": ready.get("status"), "service": ready.get("service"), "edges": ready.get("edges")},
        "source_identity": live_identity,
        "expected_source_identity": expected_identity,
        "source_identity_match": identity_match,
        "cases_sha256": sha256_file(cases_path),
        "consumer_freeze_sha256": sha256_file(FREEZE),
        "consumer_fingerprint_sha256": freeze.get("consumer_fingerprint_sha256"),
        "case_count": len(cases),
        "non_empty_case_count": sum(1 for row in results if row["rest_count"] > 0),
        "cases": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc = collect(
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            subject_sha=args.subject_sha,
            cases_path=Path(args.cases),
        )
    except Exception as exc:  # live harness failure is evidence, not a traceback-only void
        doc = {
            "schema": SCHEMA,
            "subject_sha": args.subject_sha.lower(),
            "status": "FAILED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "read_only": True,
            "authority_promotion": False,
            "failure_reason": f"collector_error:{type(exc).__name__}:{exc}",
        }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(doc["status"])
    return 0 if doc["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
