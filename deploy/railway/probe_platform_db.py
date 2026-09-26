"""Read-only fresh-connection proof, run via Railway SSH (never prints a DSN)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import UTC, datetime

IDENTITY_SQL = """
SELECT session_user::text AS session_user, current_user::text AS current_user,
       current_database() AS database, rolcanlogin, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname = current_user
"""


async def probe(env, connect) -> dict:
    """Use the container's resolved credential, without inspecting password hashes."""
    result = {
        "ok": False,
        "checked_at": datetime.now(UTC).isoformat(),
        "environment_id": env.get("RAILWAY_ENVIRONMENT_ID", ""),
        "service_id": env.get("RAILWAY_SERVICE_ID", ""),
        "deployment_id": env.get("RAILWAY_DEPLOYMENT_ID", ""),
    }
    dsn = env.get("DATABASE_URL", "").strip()
    if not dsn or "${{" in dsn:
        return {**result, "error": "missing_or_unresolved_database_url"}
    connection = None
    try:
        async with asyncio.timeout(8):
            connection = await connect(dsn, timeout=4, command_timeout=2, statement_cache_size=0)
            async with connection.transaction(readonly=True):
                row = await connection.fetchrow(IDENTITY_SQL)
            if row is None:
                return {**result, "error": "role_not_found"}
            identity = dict(row)
            result["identity"] = identity
            result["ok"] = (
                identity["session_user"] == identity["current_user"] == "sahool_app"
                and identity["database"] == "sahool"
                and identity["rolcanlogin"] is True
                and identity["rolsuper"] is False
                and identity["rolbypassrls"] is False
            )
            if not result["ok"]:
                result["error"] = "unexpected_database_or_role"
    except Exception as exc:  # noqa: BLE001 — never serialize credential-bearing messages
        result["error"] = type(exc).__name__
        result["sqlstate"] = getattr(exc, "sqlstate", None)
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                await connection.close(timeout=1)
    return result


def main() -> int:
    try:
        import asyncpg

        result = asyncio.run(probe(os.environ, asyncpg.connect))
    except Exception as exc:  # noqa: BLE001 — no traceback or environment dump
        result = {"ok": False, "error": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
