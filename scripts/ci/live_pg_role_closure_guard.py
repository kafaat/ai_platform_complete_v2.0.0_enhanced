#!/usr/bin/env python3
"""Fail-closed proof that the dedicated live-PG application role is standalone.

Gap: ``PG-APP-ROLE-TRANSITIVE-PRIVILEGE-CLOSURE-01``.

The existing live-PG evidence guard proves direct attributes on ``sahool_app``.
That is necessary but not sufficient in PostgreSQL 16: membership rows in
``pg_auth_members`` can grant inherited privileges or allow ``SET ROLE`` through
chains of memberships.  For the *dedicated evidence role* we therefore use a
stronger, simpler contract: it must have **no membership at all**, directly or
transitively.

This is intentionally stricter than a general production authorization model.
The CI evidence role is created only to measure database enforcement, so a
membership is unnecessary attack/ambiguity surface.  Rejecting even an inert
membership means a later change to ``INHERIT``, ``SET`` or ``ADMIN`` cannot
silently widen what the evidence role can do without this guard turning red.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_PSQL_SAFE_FLAGS = ["-X", "-v", "ON_ERROR_STOP=1"]

PSQL_CLIENT_MISSING = "PSQL_CLIENT_MISSING"
PSQL_CATALOGUE_QUERY_FAILED = "PSQL_CATALOGUE_QUERY_FAILED"
RESTRICTED_ROLE_NOT_FOUND = "RESTRICTED_ROLE_NOT_FOUND"
ROLE_MEMBERSHIP_CLOSURE_NOT_EMPTY = "ROLE_MEMBERSHIP_CLOSURE_NOT_EMPTY"
EVIDENCE_REASON_UNCLASSIFIED = "UNCLASSIFIED_FAIL_CLOSED_EXIT"


class GuardExit(SystemExit):
    """Carry a raw diagnostic for logs and a stable reason for uploaded evidence."""

    def __init__(self, raw: str, evidence_reason: str) -> None:
        super().__init__(raw)
        self.evidence_reason = evidence_reason


def _sql_literal(value: str) -> str:
    """Return a PostgreSQL string literal without changing the role name."""
    return "'" + value.replace("'", "''") + "'"


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        return "unavailable"
    return proc.stdout.strip() if proc.returncode == 0 else "unavailable"


def psql(sql: str, *, database: str, owner: str) -> str:
    """Query the live catalogue without placing connection values on the command line."""
    try:
        proc = subprocess.run(
            ["psql", *_PSQL_SAFE_FLAGS, "-d", database, "-U", owner, "-qAtc", sql],
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        raise GuardExit(
            "psql is not available in PATH; the dedicated live-PG job cannot be measured",
            PSQL_CLIENT_MISSING,
        ) from None
    if proc.returncode != 0:
        raise GuardExit(
            f"catalogue query failed: {proc.stderr.strip()[:400]}",
            PSQL_CATALOGUE_QUERY_FAILED,
        )
    return proc.stdout.strip()


def role_exists(database: str, owner: str, app_role: str) -> bool:
    out = psql(
        "select exists(select 1 from pg_roles where rolname=" + _sql_literal(app_role) + ")::text",
        database=database,
        owner=owner,
    )
    if out not in {"true", "false"}:
        raise GuardExit(
            "role existence query returned a non-boolean value",
            PSQL_CATALOGUE_QUERY_FAILED,
        )
    return out == "true"


def membership_closure(database: str, owner: str, app_role: str) -> list[dict]:
    """Return every direct/transitive membership reachable from ``app_role``.

    PostgreSQL 16 stores ``ADMIN``, ``INHERIT`` and ``SET`` on each membership
    grant.  Multiple grants for the same member/role pair are legal, so the
    evidence retains the grantor and options instead of deduplicating them.
    """
    role_literal = _sql_literal(app_role)
    sql = f"""
with recursive role_walk as (
    select
        m.member,
        m.roleid,
        m.grantor,
        member_role.rolname as member_name,
        granted_role.rolname as role_name,
        grantor_role.rolname as grantor_name,
        m.admin_option,
        m.inherit_option,
        m.set_option,
        array[m.member, m.roleid]::oid[] as path,
        1 as depth
    from pg_auth_members m
    join pg_roles member_role on member_role.oid = m.member
    join pg_roles granted_role on granted_role.oid = m.roleid
    join pg_roles grantor_role on grantor_role.oid = m.grantor
    where member_role.rolname = {role_literal}

    union all

    select
        m.member,
        m.roleid,
        m.grantor,
        member_role.rolname as member_name,
        granted_role.rolname as role_name,
        grantor_role.rolname as grantor_name,
        m.admin_option,
        m.inherit_option,
        m.set_option,
        w.path || m.roleid,
        w.depth + 1
    from role_walk w
    join pg_auth_members m on m.member = w.roleid
    join pg_roles member_role on member_role.oid = m.member
    join pg_roles granted_role on granted_role.oid = m.roleid
    join pg_roles grantor_role on grantor_role.oid = m.grantor
    where not m.roleid = any(w.path)
)
select coalesce(
    json_agg(
        json_build_object(
            'member', member_name,
            'role', role_name,
            'grantor', grantor_name,
            'depth', depth,
            'admin_option', admin_option,
            'inherit_option', inherit_option,
            'set_option', set_option
        ) order by depth, member_name, role_name, grantor_name
    ),
    '[]'::json
)::text
from role_walk
""".strip()
    raw = psql(sql, database=database, owner=owner)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GuardExit(
            f"membership closure query returned invalid JSON: {exc}",
            PSQL_CATALOGUE_QUERY_FAILED,
        ) from None
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise GuardExit(
            "membership closure query returned an unexpected JSON shape",
            PSQL_CATALOGUE_QUERY_FAILED,
        )
    return parsed


def evidence_document(
    *, app_role: str, verdict: str, memberships: list[dict] | None, problems: list[str]
) -> dict:
    return {
        "$comment": (
            "Dedicated live-PG role-closure evidence. Uploaded evidence contains stable reasons, "
            "not libpq diagnostics or connection variables."
        ),
        "schema_version": "1.0.0",
        "gap": "PG-APP-ROLE-TRANSITIVE-PRIVILEGE-CLOSURE-01",
        "verdict": verdict,
        "binding": {
            "checkout_sha": _git("rev-parse", "HEAD"),
            "checkout_tree": _git("rev-parse", "HEAD^{tree}"),
            "github_sha": os.environ.get("GITHUB_SHA", "unset"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID", "unset"),
        },
        "policy": {
            "require_zero_memberships": True,
            "reason": (
                "The dedicated evidence role is not a production authorization role. Any membership "
                "would make the measured privilege boundary depend on pg_auth_members and future "
                "INHERIT/SET/ADMIN option changes."
            ),
        },
        "role": app_role,
        "membership_closure": memberships,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", default=os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"))
    ap.add_argument("--owner", default=os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"))
    ap.add_argument("--app-role", default=os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app"))
    ap.add_argument("--evidence", type=Path)
    a = ap.parse_args(argv)

    def emit(verdict: str, memberships: list[dict] | None, problems: list[str]) -> None:
        if a.evidence is None:
            return
        a.evidence.parent.mkdir(parents=True, exist_ok=True)
        a.evidence.write_text(
            json.dumps(
                evidence_document(
                    app_role=a.app_role,
                    verdict=verdict,
                    memberships=memberships,
                    problems=problems,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    try:
        if not role_exists(a.database, a.owner, a.app_role):
            raise GuardExit(
                f"restricted role {a.app_role!r} does not exist",
                RESTRICTED_ROLE_NOT_FOUND,
            )
        memberships = membership_closure(a.database, a.owner, a.app_role)
    except SystemExit as exc:
        reason = getattr(exc, "evidence_reason", EVIDENCE_REASON_UNCLASSIFIED)
        emit("FAIL", None, [reason])
        raise

    if memberships:
        emit("FAIL", memberships, [ROLE_MEMBERSHIP_CLOSURE_NOT_EMPTY])
        print("live_pg_role_closure FAILED:")
        print(f"  role={a.app_role} reachable_membership_rows={len(memberships)}")
        for item in memberships:
            print(
                "  "
                f"depth={item.get('depth')} member={item.get('member')} role={item.get('role')} "
                f"inherit={item.get('inherit_option')} set={item.get('set_option')} "
                f"admin={item.get('admin_option')}"
            )
        return 1

    emit("PASS", [], [])
    print(f"live_pg_role_closure_ok role={a.app_role} reachable_membership_rows=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
