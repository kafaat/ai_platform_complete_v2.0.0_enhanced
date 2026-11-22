"""Per-farm scope from server-side grants (Service Center SC-1, owner decision C).

``tenant_connection`` calls :func:`load_farm_scope` after it sets the tenant GUCs. Two switches
must both hold before anything changes:

* ``SAHOOL_FARM_SCOPE_ENFORCE`` is on (default off). While it is off nothing is queried, the
  user stays unhydrated and ``app.enforce_farm_scope`` is never set, so the v287 policies pass
  every row and visibility is what it was before v287;
* the v287 objects exist (``farm_access_grants`` and ``sc_farm_visible(text)``). A merge
  deploys the platform while migrations are applied later, with owner approval, so the platform
  must keep working on a database without them. The catalog is asked with ``to_regclass`` /
  ``to_regprocedure``, which every role may read and which never raise, so the probe cannot
  abort the caller's transaction. Only presence is cached, so an applied migration is picked
  up without a restart; before running v287 down, switch the flag off (the down file says so).

Grants are keyed by the JWT ``sub`` (``user.user_id``), the AUTH service's users.id as text,
never the platform database's users.id (decision C). The number v287 is provisional (SHR-02).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

FLAG = "SAHOOL_FARM_SCOPE_ENFORCE"
MIGRATION = "v287"  # provisional: re-allocated at merge (SHR-02)
_ON = frozenset({"1", "true", "on", "yes"})

_PROBE = (
    "SELECT to_regclass('public.farm_access_grants') IS NOT NULL "
    "AND to_regprocedure('public.sc_farm_visible(text)') IS NOT NULL"
)
_GRANTS = (
    "SELECT farm_id FROM farm_access_grants "
    "WHERE tenant_id = $1::uuid AND user_id = $2 AND is_active ORDER BY farm_id"
)

_present = False


def enforcement_requested() -> bool:
    """Whether the operator switched farm scope on. Read per call: no restart to switch off."""
    return os.getenv(FLAG, "").strip().lower() in _ON


async def schema_present(conn) -> bool:
    """Whether v287's objects exist. Presence is cached; absence is asked again."""
    global _present
    if _present:
        return True
    if await conn.fetchval(_PROBE) is True:
        _present = True
        return True
    return False


async def load_farm_scope(conn, user) -> bool:
    """Hydrate ``user``'s farm scope from its active grants; True when the caller must set
    ``app.enforce_farm_scope`` to 'on' inside its transaction.

    Called with the tenant GUCs already set (the grant read is under RLS). An owner keeps every
    farm of the tenant, as ``sc_farm_visible`` does; any other role gets exactly its grants, and
    no grant means no farm.
    """
    if not enforcement_requested():
        return False
    if not await schema_present(conn):
        logger.warning("%s is on but %s is not applied: farm scope stays off", FLAG, MIGRATION)
        return False
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    rows = await conn.fetch(_GRANTS, str(user.tenant_id), str(user.user_id))
    user.farm_ids_access = [str(r["farm_id"]) for r in rows]
    user.farm_access_all = role == "owner"
    user.farm_scope_loaded = True
    return True


async def insert_tenant_grants(conn, tenant_id: str, grants: list[tuple[str, str, str]]) -> int:
    """Insert one tenant's ``(user_id, farm_id, granted_by)`` grants; return how many were new.

    The platform is the only writer of farm_access_grants (owner decision A); the operator
    backfill (scripts/ops/farm_access_backfill.py) calls this instead of carrying its own SQL.
    One transaction with the tenant context and an owner role set, so the grant table's
    policies (tenant isolation, owner-only writes) hold for a NOBYPASSRLS role too. An existing
    row, active or revoked, is left as it is (ON CONFLICT DO NOTHING).
    """
    written = 0
    async with conn.transaction():
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), "
            "       set_config('app.current_user_id', 'farm-access-backfill', true), "
            "       set_config('app.current_role', 'owner', true)",
            str(tenant_id),
        )
        for user_id, farm_id, granted_by in grants:
            status = await conn.execute(
                "INSERT INTO farm_access_grants (tenant_id, user_id, farm_id, is_active, "
                "granted_by) VALUES ($1::uuid, $2, $3, true, $4) "
                "ON CONFLICT (tenant_id, user_id, farm_id) DO NOTHING",
                str(tenant_id),
                user_id,
                farm_id,
                granted_by,
            )
            written += int(status.rsplit(" ", 1)[-1])
    return written
