#!/usr/bin/env python3
"""Run fail-closed soil production certification probes and emit a signed JSON manifest.

This script never marks a release certified unless every required runtime probe passes
and two distinct approvals are supplied. It is safe to run in dry-run mode without a DB.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOIL = ROOT / "services" / "soil-service"
sys.path[:0] = [str(ROOT), str(SOIL)]
from p6_certification import evaluate_run

from shared.contracts.soil.p6 import (
    CertificationCheck,
    CertificationEvidence,
    RuntimeCertificationRun,
)

REQUIRED_TABLES = [
    "soil_observations",
    "soil_profile_snapshots",
    "soil_profile_projection_jobs",
    "soil_profile_current",
    "soil_runtime_certification_runs",
    "soil_runtime_certification_evidence",
]


def evidence(check_name: str, evidence_type: str, summary: dict, uri: str | None = None):
    raw = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    return CertificationEvidence(
        check_name=check_name,
        evidence_type=evidence_type,
        uri=uri,
        sha256=hashlib.sha256(raw).hexdigest(),
        summary=summary,
    )


async def db_probes(dsn: str):
    import asyncpg

    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    evidence_items = []
    checks = []
    try:
        version = await conn.fetchval("SHOW server_version")
        tables = {
            r["tablename"]
            for r in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename=ANY($1::text[])",
                REQUIRED_TABLES,
            )
        }
        summary = {
            "server_version": version,
            "required_tables": sorted(tables),
            "expected": REQUIRED_TABLES,
        }
        ev = evidence("migrations", "postgresql_schema", summary)
        evidence_items.append(ev)
        checks.append(
            CertificationCheck(
                check_name="migrations",
                status="passed" if tables == set(REQUIRED_TABLES) else "failed",
                evidence_ids=[ev.evidence_id],
                observed_value=len(tables),
                threshold=len(REQUIRED_TABLES),
            )
        )
        rows = await conn.fetch(
            "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY($1::text[])",
            REQUIRED_TABLES,
        )
        ok = len(rows) == len(REQUIRED_TABLES) and all(
            r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows
        )
        ev = evidence("rls", "postgresql_rls", {"tables": [dict(r) for r in rows]})
        evidence_items.append(ev)
        checks.append(
            CertificationCheck(
                check_name="rls", status="passed" if ok else "failed", evidence_ids=[ev.evidence_id]
            )
        )
        lag = await conn.fetchrow(
            "SELECT count(*) FILTER (WHERE status IN ('pending','retry')) AS ready,count(*) FILTER (WHERE status='dead_letter') AS dead,count(*) FILTER (WHERE status='running' AND lease_expires_at<NOW()) AS expired FROM soil_profile_projection_jobs"
        )
        ev = evidence("lease_recovery", "projection_queue", dict(lag))
        evidence_items.append(ev)
        checks.append(
            CertificationCheck(
                check_name="lease_recovery",
                status="passed" if int(lag["expired"] or 0) == 0 else "failed",
                evidence_ids=[ev.evidence_id],
                observed_value=int(lag["expired"] or 0),
                threshold=0,
            )
        )
        checks.append(
            CertificationCheck(
                check_name="retry_dead_letter",
                status="passed" if int(lag["dead"] or 0) == 0 else "failed",
                evidence_ids=[ev.evidence_id],
                observed_value=int(lag["dead"] or 0),
                threshold=0,
            )
        )
    finally:
        await conn.close()
    return checks, evidence_items


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--release-ref", required=True)
    p.add_argument("--environment", default="staging")
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    p.add_argument("--output", required=True)
    p.add_argument("--approval", action="append", default=[])
    p.add_argument(
        "--external-evidence",
        action="append",
        default=[],
        help="JSON files containing check_name,status,summary",
    )
    args = p.parse_args()
    checks = []
    evidence_items = []
    if args.dsn:
        try:
            c, e = await db_probes(args.dsn)
            checks += c
            evidence_items += e
        except Exception as exc:
            ev = evidence(
                "migrations",
                "probe_error",
                {"error": type(exc).__name__, "message": str(exc)[:500]},
            )
            evidence_items.append(ev)
            checks.append(
                CertificationCheck(
                    check_name="migrations",
                    status="failed",
                    evidence_ids=[ev.evidence_id],
                    reasons=["database_probe_failed"],
                )
            )
    else:
        checks.extend(
            [
                CertificationCheck(
                    check_name=n, status="skipped", reasons=["database_dsn_not_supplied"]
                )
                for n in ("migrations", "rls", "lease_recovery", "retry_dead_letter")
            ]
        )
    for path in args.external_evidence:
        data = json.loads(Path(path).read_text())
        ev = evidence(
            data["check_name"],
            data.get("evidence_type", "external"),
            data.get("summary", {}),
            str(path),
        )
        evidence_items.append(ev)
        checks.append(
            CertificationCheck(
                check_name=data["check_name"],
                status=data["status"],
                evidence_ids=[ev.evidence_id],
                observed_value=data.get("observed_value"),
                threshold=data.get("threshold"),
                reasons=data.get("reasons", []),
            )
        )
    existing = {c.check_name for c in checks}
    for name in ("concurrency", "e2e", "lineage", "performance", "calibration", "rollback"):
        if name not in existing:
            checks.append(
                CertificationCheck(
                    check_name=name, status="skipped", reasons=["runtime_evidence_not_supplied"]
                )
            )
    run = RuntimeCertificationRun(
        tenant_id=args.tenant_id,
        release_ref=args.release_ref,
        environment=args.environment,
        migrations_applied_through="v166"
        if any(c.check_name == "migrations" and c.status == "passed" for c in checks)
        else None,
        checks=checks,
        evidence=evidence_items,
        approvals=args.approval,
        status="running",
    )
    run = evaluate_run(run)
    Path(args.output).write_text(
        json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "status": run.status,
                "blockers": run.blockers,
                "manifest_sha256": run.manifest_sha256,
            },
            indent=2,
        )
    )
    return 0 if run.status == "certified" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
