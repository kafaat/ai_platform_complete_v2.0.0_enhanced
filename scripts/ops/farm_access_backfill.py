"""Operator CLI: backfill farm_access_grants for owner decision C (Service Center SC-1).

Every active identity of the AUTH service gets an active grant on every farm of its tenant,
keyed by its JWT ``sub`` (auth ``users.id`` as text) with ``granted_by='backfill:decision-C'``.
That reproduces today's visibility, so switching ``SAHOOL_FARM_SCOPE_ENFORCE`` on afterwards
changes nothing until an owner narrows a grant; ``farm_access_diff.py`` proves it per
(user, tenant, farm, action) and must report nothing before the flag is considered.

Identities come from auth's OWN connection (``AUTH_DATABASE_URL``), never from the platform's
``users.id``: with a separate auth database they are different numbers, and a grant keyed by
the platform id would match no session (or another person's). If auth really shares the
platform database, give the same DSN twice; that is an operator statement, not an assumption.

Safety:
- dry run by default: reads only, in read-only transactions, and prints the plan;
- ``--apply`` inserts the missing grants through the platform's own writer
  (``api.farm_scope.insert_tenant_grants``: one transaction per tenant with the tenant context
  set, ``ON CONFLICT DO NOTHING``, so a re-run changes nothing). Applying is an owner decision;
  never run it against a database you were not asked to change;
- an existing inactive grant is a revocation and is never re-activated (reported instead);
- both connections must be able to read every tenant (BYPASSRLS), otherwise the run stops
  (exit 2) rather than plan from an empty, row-level-filtered read.

Usage::

    DATABASE_URL=postgresql://operator@platform-host/db \\
    AUTH_DATABASE_URL=postgresql://operator@auth-host/db \\
      python scripts/ops/farm_access_backfill.py [--apply] [--json report.json]

Exit status: 0 done (or planned); 1 refused because a platform user has no auth identity or a
mismatched one (nothing is written, dry run or --apply); 2 precondition failed (missing DSN,
role, or v287 absent).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import farm_access_common as fac  # noqa: E402


async def _insert(conn, grants: list[fac.Grant]) -> int:
    """Insert ``grants`` tenant by tenant through the platform's own writer
    (``api.farm_scope.insert_tenant_grants``), one transaction per tenant."""
    farm_scope = fac._platform_module("api.farm_scope")
    by_tenant: dict[str, list[tuple[str, str, str]]] = {}
    for g in grants:
        by_tenant.setdefault(g.tenant_id, []).append((g.user_id, g.farm_id, g.granted_by))
    written = 0
    for tenant, rows in sorted(by_tenant.items()):
        written += await farm_scope.insert_tenant_grants(conn, tenant, rows)
    return written


def identity_blockers(identities: dict) -> list[str]:
    """The identity-report categories that stop the backfill (dry run and --apply alike)."""
    return [name for name in ("unresolved", "mismatched") if identities[name]]


async def run(platform_dsn: str, auth_dsn: str, *, apply: bool) -> dict:
    import asyncpg

    platform = await asyncpg.connect(platform_dsn)
    auth = await asyncpg.connect(auth_dsn)
    try:
        await fac.require_full_visibility(platform, "DATABASE_URL (platform)")
        await fac.require_full_visibility(auth, "AUTH_DATABASE_URL (auth)")
        if not await fac.grants_table_present(platform):
            raise fac.Precondition("farm_access_grants is missing: apply migration v287 first")
        auth_users = await fac.fetch_users(auth)
        platform_users = await fac.fetch_users(platform)
        farms = await fac.fetch_farms(platform)
        plan = fac.plan_backfill(auth_users, farms, await fac.fetch_grants(platform))
        identities = fac.identity_report(platform_users, auth_users)
        # Hospital condition: an unresolved or mismatched identity stops the run before any write.
        refused = bool(identity_blockers(identities))
        written = await _insert(platform, plan["insert"]) if apply and not refused else 0
    finally:
        await platform.close()
        await auth.close()
    return {
        "mode": "apply" if apply else "dry-run",
        "refused": refused,
        "granted_by": fac.GRANTED_BY,
        "planned_inserts": len(plan["insert"]),
        "written": written,
        "already_active": len(plan["already_active"]),
        "skipped_revoked": [asdict(g) for g in plan["skipped_revoked"]],
        "insert": [asdict(g) for g in plan["insert"]],
        "identities": {
            "resolved": identities["resolved"],
            "unresolved": len(identities["unresolved"]),
            "mismatched": len(identities["mismatched"]),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="write the grants (owner decision)")
    parser.add_argument("--json", type=Path, help="write the full report to this file")
    args = parser.parse_args(argv)
    platform_dsn = os.getenv("DATABASE_URL", "").strip()
    auth_dsn = os.getenv("AUTH_DATABASE_URL", "").strip()
    if not platform_dsn or not auth_dsn:
        print("DATABASE_URL and AUTH_DATABASE_URL are both required", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(run(platform_dsn, auth_dsn, apply=args.apply))
    except fac.Precondition as exc:
        print(f"precondition failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"{report['mode']}: planned={report['planned_inserts']} written={report['written']} "
        f"already_active={report['already_active']} "
        f"skipped_revoked={len(report['skipped_revoked'])} identities={report['identities']}"
    )
    if report["identities"]["unresolved"] or report["identities"]["mismatched"]:
        print(
            "REFUSED: the identity report is not clean (nothing written); "
            "run farm_access_diff.py for the per-user list"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
