"""Shared model of the decision-C farm grants: identities, the backfill plan and the comparison.

Owner decision C (Service Center SC-1): ``farm_access_grants.user_id`` is the JWT ``sub``, which
the AUTH service mints as ``str(users.id)`` from ITS database. The platform database also has a
``users`` table; when auth has a database of its own the two ids are different numbers, so
identities are always read through auth's own connection (``AUTH_DATABASE_URL``) and never
taken from the platform's ``users.id``. The platform's users only feed the identity report:
each one must map to exactly one auth identity, by e-mail, in the same tenant.

Used by ``farm_access_backfill.py`` (the plan and its apply) and ``farm_access_diff.py`` (the
before/after comparison). The pure functions here take plain rows; the ``fetch_*`` helpers read
them, each in a read-only transaction.
"""

from __future__ import annotations

import importlib
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

GRANTED_BY = "backfill:decision-C"

_PLATFORM = Path(__file__).resolve().parents[2] / "services" / "sahool-platform"


def _platform_module(name: str):
    """A platform module: the permission model is the platform's own (core.authorization)."""
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    return importlib.import_module(name)


# The platform normalises the JWT role claim with api.main._ROLE_ALIASES (unknown => viewer).
# Mirrored here so the scripts need not import api.main (which builds the app); the copy is
# pinned to the source by tests_v9/test_farm_access_backfill_diff.py.
ROLE_ALIASES: dict[str, str] = {
    "owner": "owner",
    "admin": "owner",
    "platform_admin": "platform_admin",
    "manager": "manager",
    "agronomist": "agronomist",
    "expert": "agronomist",
    "worker": "worker",
    "farmer": "worker",
    "viewer": "viewer",
}


@dataclass(frozen=True)
class Identity:
    """A ``users`` row of either database. ``id`` is text: for auth it is the JWT sub."""

    id: str
    email: str
    tenant_id: str | None
    role: str
    active: bool


@dataclass(frozen=True)
class Farm:
    farm_id: str
    tenant_id: str


@dataclass(frozen=True)
class Grant:
    """``granted_by`` is required: provenance decides how a colliding key is judged."""

    tenant_id: str
    user_id: str
    farm_id: str
    granted_by: str
    is_active: bool = True


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_role(raw: str | None) -> str:
    return ROLE_ALIASES.get(str(raw or "").strip().lower(), "viewer")


# ── identity report ───────────────────────────────────────────────────────────


def identity_report(platform_users: list[Identity], auth_users: list[Identity]) -> dict:
    """Map every platform user to its auth identity (the JWT sub), by e-mail.

    * ``resolved``: exactly one auth identity with that e-mail, in the same tenant;
    * ``unresolved``: no auth identity with that e-mail (or the platform row has none);
    * ``mismatched``: the e-mail matches but the tenant disagrees, or several auth identities
      share the e-mail (``ambiguous_email``).

    The platform users.id is reported next to the sub on purpose: they are different
    identifiers, and only the sub can key a grant.
    """
    by_email: dict[str, list[Identity]] = defaultdict(list)
    for a in auth_users:
        by_email[normalize_email(a.email)].append(a)
    rows: list[dict] = []
    for p in sorted(platform_users, key=lambda u: (str(u.tenant_id), u.id)):
        email = normalize_email(p.email)
        matches = by_email.get(email, []) if email else []
        row = {
            "platform_user_id": p.id,
            "email": email,
            "platform_tenant_id": p.tenant_id,
            "sub": None,
            "auth_tenant_id": None,
            "status": "resolved",
            "reasons": [],
        }
        if not matches:
            row["status"] = "unresolved"
            row["reasons"].append("no_auth_identity" if email else "no_email")
        elif len(matches) > 1:
            row["status"] = "mismatched"
            row["reasons"].append("ambiguous_email")
        else:
            a = matches[0]
            row["sub"], row["auth_tenant_id"] = a.id, a.tenant_id
            if str(a.tenant_id) != str(p.tenant_id):
                row["status"] = "mismatched"
                row["reasons"].append("tenant")
        rows.append(row)
    return {
        "users": rows,
        "resolved": sum(r["status"] == "resolved" for r in rows),
        "unresolved": [r for r in rows if r["status"] == "unresolved"],
        "mismatched": [r for r in rows if r["status"] == "mismatched"],
    }


# ── backfill plan ─────────────────────────────────────────────────────────────


def _farms_by_tenant(farms: list[Farm]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for f in farms:
        out[str(f.tenant_id)].append(f.farm_id)
    return out


def plan_backfill(auth_users: list[Identity], farms: list[Farm], existing: list[Grant]) -> dict:
    """Decision C: every active auth identity gets every farm of its tenant, keyed by its sub.

    An existing active grant is left as it is; an existing inactive one is a revocation and is
    reported (``skipped_revoked``), never re-activated: the comparison then shows it as lost,
    which is for the owner to decide.
    """
    by_tenant = _farms_by_tenant(farms)
    current = {(g.tenant_id, g.user_id, g.farm_id): g for g in existing}
    insert: list[Grant] = []
    already: list[Grant] = []
    revoked: list[Grant] = []
    for u in sorted(auth_users, key=lambda u: (str(u.tenant_id), u.id)):
        if not u.active or not u.tenant_id:
            continue
        for farm_id in sorted(by_tenant.get(str(u.tenant_id), [])):
            key = (str(u.tenant_id), u.id, farm_id)
            have = current.get(key)
            if have is None:
                insert.append(Grant(*key, GRANTED_BY))
            elif have.is_active:
                already.append(have)
            else:
                revoked.append(have)
    return {"insert": insert, "already_active": already, "skipped_revoked": revoked}


# ── before / after comparison ─────────────────────────────────────────────────


def _role_actions(role: str) -> list[str]:
    """The permissions of ``role``, from the platform's own model."""
    authz = _platform_module("core.authorization")
    schemas = _platform_module("core.canonical_schemas")
    probe = schemas.UserSchema("probe", "probe", schemas.UserRole(role), "probe")
    return sorted(p.value for p in authz.Permission if authz.has_permission(probe, p))


def scope_before(auth_users: list[Identity], farms: list[Farm]) -> set[tuple[str, str, str, str]]:
    """Today: an active user may act on every farm of its tenant within its role."""
    by_tenant = _farms_by_tenant(farms)
    out: set[tuple[str, str, str, str]] = set()
    for u in auth_users:
        if not u.active or not u.tenant_id:
            continue
        actions = _role_actions(normalize_role(u.role))
        for farm_id in by_tenant.get(str(u.tenant_id), []):
            out.update((u.id, str(u.tenant_id), farm_id, a) for a in actions)
    return out


def scope_after(
    auth_users: list[Identity], farms: list[Farm], grants: list[Grant]
) -> set[tuple[str, str, str, str]]:
    """Under enforcement, as sc_farm_visible decides: an owner keeps every farm of its tenant;
    any other role only farms of its tenant with an active grant keyed by its sub."""
    by_tenant = _farms_by_tenant(farms)
    granted = {(g.tenant_id, g.user_id, g.farm_id) for g in grants if g.is_active}
    out: set[tuple[str, str, str, str]] = set()
    for u in auth_users:
        if not u.active or not u.tenant_id:
            continue
        role = normalize_role(u.role)
        actions = _role_actions(role)
        tenant = str(u.tenant_id)
        for farm_id in by_tenant.get(tenant, []):
            if role == "owner" or (tenant, u.id, farm_id) in granted:
                out.update((u.id, tenant, farm_id, a) for a in actions)
    return out


def orphan_grants(auth_users: list[Identity], farms: list[Farm], grants: list[Grant]) -> list:
    """Active grants no session can use: no auth identity with that sub in that tenant (for
    example a grant keyed by the platform's users.id), or a farm outside the grant's tenant."""
    subs = {(str(u.tenant_id), u.id) for u in auth_users}
    farm_tenant = {f.farm_id: str(f.tenant_id) for f in farms}
    out = []
    for g in grants:
        if not g.is_active:
            continue
        reasons = []
        if (g.tenant_id, g.user_id) not in subs:
            reasons.append("no_auth_identity_with_this_sub_in_tenant")
        if farm_tenant.get(g.farm_id) != g.tenant_id:
            reasons.append("farm_not_in_grant_tenant")
        if reasons:
            out.append({**asdict(g), "reasons": reasons})
    return out


def platform_id_keyed_grants(identities: dict, grants: list[Grant]) -> list:
    """Active grants whose key is the platform users.id of a person whose sub is different.

    Both users.id columns are SERIAL from 1, so the id spaces overlap and a grant keyed by a
    platform id usually matches SOME sub: possibly another person in the same tenant, which
    neither orphan_grants (the key is a real sub) nor lost/newly_permitted (a full grant set is
    the same set either way) can see. A key equal to the platform id of a person who resolves
    to another sub is ambiguous by value, so it fails unless the row's provenance is the
    decision-C backfill, which reads identities through auth's own connection only and keys
    by sub by construction (``granted_by='backfill:decision-C'``). A grant written by anyone
    else with such a key must be checked by a person; this check cannot tell which was meant.

    The label is trustworthy only because v287 reserves it to the migration owner (a trigger)
    and the migrator revokes write on the table from the application and jobs roles. Once grant
    administration exists (SC-2) and people write grants routinely, this check needs run
    provenance (for example a backfill_runs table with a digest of what each run wrote) to stay
    a usable gate; a label alone will not scale past a single operator backfill.
    """
    resolved = {
        (str(r["platform_tenant_id"]), r["platform_user_id"]): (
            r["sub"] if r["status"] == "resolved" else None
        )
        for r in identities["users"]
    }
    out = []
    for g in grants:
        if not g.is_active or g.granted_by == GRANTED_BY:
            continue
        key = (g.tenant_id, g.user_id)
        if key in resolved and resolved[key] != g.user_id:
            out.append({**asdict(g), "platform_user_resolves_to_sub": resolved[key]})
    return out


def compare(
    platform_users: list[Identity],
    auth_users: list[Identity],
    farms: list[Farm],
    grants: list[Grant],
) -> dict:
    """The full report; ``failures(report)`` names what must be empty before enforcement."""
    before = scope_before(auth_users, farms)
    after = scope_after(auth_users, farms, grants)
    lost = sorted(before - after)
    new = sorted(after - before)
    identities = identity_report(platform_users, auth_users)
    per_user: dict[tuple[str, str], dict] = {}
    for key, bucket in ((before, "before"), (after, "after")):
        for sub, tenant, farm_id, _action in key:
            entry = per_user.setdefault(
                (sub, tenant), {"sub": sub, "tenant_id": tenant, "before": set(), "after": set()}
            )
            entry[bucket].add(farm_id)
    return {
        "counts": {
            "before": len(before),
            "after": len(after),
            "lost": len(lost),
            "newly_permitted": len(new),
        },
        "lost": [
            dict(zip(("sub", "tenant_id", "farm_id", "action"), k, strict=True)) for k in lost
        ],
        "newly_permitted": [
            dict(zip(("sub", "tenant_id", "farm_id", "action"), k, strict=True)) for k in new
        ],
        "per_user": [
            {**e, "before": sorted(e["before"]), "after": sorted(e["after"])}
            for _, e in sorted(per_user.items())
        ],
        "identities": identities,
        "orphan_grants": orphan_grants(auth_users, farms, grants),
        "platform_id_keyed_grants": platform_id_keyed_grants(identities, grants),
    }


def failures(report: dict) -> list[str]:
    """The non-empty failure categories; enforcement may be considered only when none is."""
    ident = report["identities"]
    found = {
        "lost": report["lost"],
        "newly_permitted": report["newly_permitted"],
        "unresolved": ident["unresolved"],
        "mismatched": ident["mismatched"],
        "orphan_grants": report["orphan_grants"],
        "platform_id_keyed_grants": report["platform_id_keyed_grants"],
    }
    return [name for name, rows in found.items() if rows]


# ── database reads (each in a read-only transaction) ──────────────────────────


class Precondition(RuntimeError):
    """The run cannot produce a truthful report (exit status 2)."""


async def require_full_visibility(conn, label: str) -> None:
    """The reports span tenants. Under FORCE RLS a NOBYPASSRLS role without a tenant context
    sees no row, and an empty read would look like a clean report: refuse it instead."""
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    check_role_reads_every_tenant(dict(row) if row else None, label)


def check_role_reads_every_tenant(role: dict | None, label: str) -> None:
    """``role`` is the session's pg_roles row (rolsuper, rolbypassrls), or None."""
    if not role or not (role["rolsuper"] or role["rolbypassrls"]):
        raise Precondition(
            f"{label}: the role cannot read every tenant (needs BYPASSRLS); "
            "a row-level-security role would read nothing and report a false clean result"
        )


async def require_operator(conn) -> None:
    """--apply only: the session must be the migration owner (v287 reserves the backfill's
    provenance label to it with a trigger, and the migrator revokes write from every other
    role). A BYPASSRLS role such as the jobs role reads, but may not write grants."""
    row = await conn.fetchrow(
        "SELECT (SELECT rolsuper FROM pg_roles WHERE rolname = session_user) AS session_super, "
        "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS current_super, "
        "has_table_privilege('public.farm_access_grants', 'INSERT') AS can_insert"
    )
    check_operator(dict(row) if row else None)


def check_operator(role: dict | None) -> None:
    if not role or not (role["session_super"] and role["current_super"] and role["can_insert"]):
        raise Precondition(
            "--apply must run as the migration owner (a superuser with INSERT on "
            "farm_access_grants, the credentials that apply migrations); this role may only "
            "do the dry run"
        )


async def fetch_users(conn) -> list[Identity]:
    async with conn.transaction(readonly=True):
        rows = await conn.fetch(
            "SELECT id::text AS id, email, tenant_id::text AS tenant_id, role, "
            "(active IS TRUE) AS active FROM users ORDER BY id"
        )
    return [
        Identity(r["id"], r["email"] or "", r["tenant_id"], r["role"] or "", r["active"])
        for r in rows
    ]


async def fetch_farms(conn) -> list[Farm]:
    async with conn.transaction(readonly=True):
        rows = await conn.fetch(
            "SELECT farm_id, tenant_id::text AS tenant_id FROM farms ORDER BY farm_id"
        )
    return [Farm(r["farm_id"], r["tenant_id"]) for r in rows]


async def grants_table_present(conn) -> bool:
    return await conn.fetchval("SELECT to_regclass('public.farm_access_grants') IS NOT NULL")


async def fetch_grants(conn) -> list[Grant]:
    async with conn.transaction(readonly=True):
        rows = await conn.fetch(
            "SELECT tenant_id::text AS tenant_id, user_id, farm_id, is_active, granted_by "
            "FROM farm_access_grants ORDER BY tenant_id, user_id, farm_id"
        )
    return [
        Grant(r["tenant_id"], r["user_id"], r["farm_id"], r["granted_by"], r["is_active"])
        for r in rows
    ]
