"""WX-12.1 database certification. Requires a real PostgreSQL DATABASE_URL."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys


async def checks():
    import asyncpg

    url = os.environ["DATABASE_URL"]
    c = await asyncpg.connect(url, statement_cache_size=0)
    try:
        role = await c.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        if role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("certification role must not be superuser/BYPASSRLS")
        versions = await c.fetch(
            "SELECT version FROM decision_service_schema_migrations ORDER BY version"
        )
        names = [r["version"] for r in versions]
        expected = [f"{i:03d}_" for i in range(1, 15)]
        missing = [p for p in expected if not any(n.startswith(p) for n in names)]
        if missing:
            raise RuntimeError(f"missing migrations: {missing}")
        tables = await c.fetch(
            "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'decision_%'"
        )
        no_rls = [r["tablename"] for r in tables if not r["rowsecurity"]]
        if no_rls:
            raise RuntimeError(f"RLS disabled: {no_rls}")
        return {
            "ok": True,
            "migrations": names,
            "decision_tables": len(tables),
            "role_safe": True,
            "rls": True,
        }
    finally:
        await c.close()


def main():
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL required")
    subprocess.run(
        [sys.executable, "services/decision-service/migration_runner.py", "--check"], check=True
    )
    print(json.dumps(asyncio.run(checks()), sort_keys=True))


if __name__ == "__main__":
    main()
