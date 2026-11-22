"""Operator CLI: compare farm access before and after farm scope (owner decision C, SC-1).

* before = today's effective scope: every active auth identity, its role's permissions, on
  every farm of its tenant;
* after  = what ``sc_farm_visible`` allows once ``SAHOOL_FARM_SCOPE_ENFORCE`` is on: an owner
  keeps every farm of its tenant, any other role only farms with an active grant keyed by its
  JWT sub (auth ``users.id`` as text).

Reported per (user, tenant, farm, action): ``lost`` (before, not after) and
``newly_permitted`` (after, not before). Identities: each platform user must map, by e-mail, to
exactly one auth identity in the same tenant; ``unresolved`` (no auth identity) and
``mismatched`` (tenant disagrees, or ambiguous e-mail) are listed per user. ``orphan_grants``
are active grants no session can use, such as one keyed by the platform's users.id.

Exit status 1 when any of lost, newly_permitted, unresolved, mismatched or orphan_grants is
non-empty: enforcement may be considered only after a clean (exit 0) run. Exit 2 when the run
cannot be truthful (missing DSN, a role that cannot read every tenant). Read-only throughout.

Usage::

    DATABASE_URL=postgresql://operator@platform-host/db \\
    AUTH_DATABASE_URL=postgresql://operator@auth-host/db \\
      python scripts/ops/farm_access_diff.py [--json report.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import farm_access_common as fac  # noqa: E402


async def collect(platform_dsn: str, auth_dsn: str) -> dict:
    import asyncpg

    platform = await asyncpg.connect(platform_dsn)
    auth = await asyncpg.connect(auth_dsn)
    try:
        await fac.require_full_visibility(platform, "DATABASE_URL (platform)")
        await fac.require_full_visibility(auth, "AUTH_DATABASE_URL (auth)")
        auth_users = await fac.fetch_users(auth)
        platform_users = await fac.fetch_users(platform)
        farms = await fac.fetch_farms(platform)
        # Before v287 there is no grant at all: the comparison then shows what enforcing would
        # take away, which is the point of running it first.
        grants = (
            await fac.fetch_grants(platform) if await fac.grants_table_present(platform) else []
        )
    finally:
        await platform.close()
        await auth.close()
    return fac.compare(platform_users, auth_users, farms, grants)


def render(report: dict) -> list[str]:
    ident = report["identities"]
    lines = [
        "counts: " + json.dumps(report["counts"]),
        f"identities: resolved={ident['resolved']} unresolved={len(ident['unresolved'])} "
        f"mismatched={len(ident['mismatched'])} orphan_grants={len(report['orphan_grants'])}",
    ]
    for row in ident["unresolved"] + ident["mismatched"]:
        lines.append(
            f"  {row['status']}: platform_user_id={row['platform_user_id']} "
            f"tenant={row['platform_tenant_id']} sub={row['sub']} reasons={row['reasons']}"
        )
    for user in report["per_user"]:
        if user["before"] != user["after"]:
            lines.append(
                f"  user sub={user['sub']} tenant={user['tenant_id']}: "
                f"farms before={len(user['before'])} after={len(user['after'])}"
            )
    for grant in report["orphan_grants"]:
        lines.append(f"  orphan grant: {grant}")
    failed = fac.failures(report)
    lines.append("FAIL: " + ", ".join(failed) if failed else "OK: no difference")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--json", type=Path, help="write the full report to this file")
    args = parser.parse_args(argv)
    platform_dsn = os.getenv("DATABASE_URL", "").strip()
    auth_dsn = os.getenv("AUTH_DATABASE_URL", "").strip()
    if not platform_dsn or not auth_dsn:
        print("DATABASE_URL and AUTH_DATABASE_URL are both required", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(collect(platform_dsn, auth_dsn))
    except fac.Precondition as exc:
        print(f"precondition failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(render(report)))
    return 1 if fac.failures(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
