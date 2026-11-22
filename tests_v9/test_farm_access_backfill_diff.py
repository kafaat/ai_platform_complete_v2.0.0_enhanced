"""Decision-C backfill and before/after comparison, without a database.

Pins the pure model in ``scripts/ops/farm_access_common.py`` and the exit status of the two
CLIs. The central hazard is identity: the platform database's ``users.id`` and the AUTH
service's ``users.id`` (the JWT ``sub``) are different numbers when auth has its own database,
so every case seeds them DIFFERENT (platform 7, auth 42 for the same person). A grant keyed by
the platform id must not be effective; one keyed by the sub must be. The same claims are proven
against PostgreSQL row-level security in ``test_farm_access_scope_live_pg.py``.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "scripts" / "ops"
PLATFORM = ROOT / "services" / "sahool-platform"
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

import farm_access_common as fac  # noqa: E402

pytestmark = pytest.mark.unit

T1 = "00000000-0000-0000-0000-0000000000a1"
T2 = "00000000-0000-0000-0000-0000000000b2"
FARMS = [fac.Farm("farm-a", T1), fac.Farm("farm-b", T1), fac.Farm("farm-z", T2)]

# Platform users.id and auth users.id differ on purpose for every person.
PLATFORM_USERS = [
    fac.Identity("7", "Manager@Example.org ", T1, "manager", True),
    fac.Identity("8", "agro@example.org", T1, "expert", True),
    fac.Identity("9", "worker@example.org", T1, "farmer", True),
    fac.Identity("10", "owner@example.org", T1, "admin", True),
]
AUTH_USERS = [
    fac.Identity("42", "manager@example.org", T1, "manager", True),
    fac.Identity("43", "agro@example.org", T1, "agronomist", True),
    fac.Identity("44", "worker@example.org", T1, "worker", True),
    fac.Identity("45", "owner@example.org", T1, "owner", True),
    fac.Identity("46", "gone@example.org", T1, "manager", False),
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, OPS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backfilled(existing=()) -> list[fac.Grant]:
    return list(existing) + fac.plan_backfill(AUTH_USERS, FARMS, list(existing))["insert"]


# ── identities ────────────────────────────────────────────────────────────────


def test_identity_report_maps_each_platform_user_to_the_auth_sub_by_email():
    report = fac.identity_report(PLATFORM_USERS, AUTH_USERS)
    assert report["resolved"] == 4 and not report["unresolved"] and not report["mismatched"]
    manager = next(r for r in report["users"] if r["platform_user_id"] == "7")
    assert manager["sub"] == "42", "the key is the auth id, never the platform users.id"


def test_unresolved_and_mismatched_identities_are_listed_per_user():
    platform = PLATFORM_USERS + [
        fac.Identity("11", "nobody@example.org", T1, "worker", True),
        fac.Identity("12", "", T1, "worker", True),
        fac.Identity("13", "moved@example.org", T1, "worker", True),
        fac.Identity("14", "twice@example.org", T1, "worker", True),
    ]
    auth = AUTH_USERS + [
        fac.Identity("50", "moved@example.org", T2, "worker", True),
        fac.Identity("51", "twice@example.org", T1, "worker", True),
        fac.Identity("52", "TWICE@example.org", T1, "worker", True),
    ]
    report = fac.identity_report(platform, auth)
    assert {(r["platform_user_id"], tuple(r["reasons"])) for r in report["unresolved"]} == {
        ("11", ("no_auth_identity",)),
        ("12", ("no_email",)),
    }
    assert {(r["platform_user_id"], tuple(r["reasons"])) for r in report["mismatched"]} == {
        ("13", ("tenant",)),
        ("14", ("ambiguous_email",)),
    }


def test_the_role_alias_copy_matches_the_platforms_jwt_normalisation():
    """``ROLE_ALIASES`` mirrors ``api.main._ROLE_ALIASES`` (read from source, not imported)."""
    tree = ast.parse((PLATFORM / "api" / "main.py").read_text(encoding="utf-8"))
    node = next(
        n
        for n in tree.body
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        and "_ROLE_ALIASES" in ast.unparse(n.targets[0] if isinstance(n, ast.Assign) else n.target)
    )
    sys.path.insert(0, str(PLATFORM))
    from core.canonical_schemas import UserRole

    source = {
        k.value: UserRole[v.attr].value
        for k, v in zip(node.value.keys, node.value.values, strict=True)
    }
    assert source == fac.ROLE_ALIASES
    assert fac.normalize_role("unknown") == "viewer" and fac.normalize_role(None) == "viewer"


# ── the backfill plan ─────────────────────────────────────────────────────────


def test_backfill_keys_every_grant_by_the_auth_sub_never_the_platform_users_id():
    plan = fac.plan_backfill(AUTH_USERS, FARMS, [])
    keys = {(g.tenant_id, g.user_id, g.farm_id) for g in plan["insert"]}
    assert keys == {(T1, sub, f) for sub in ("42", "43", "44", "45") for f in ("farm-a", "farm-b")}
    platform_ids = {u.id for u in PLATFORM_USERS}
    assert not {g.user_id for g in plan["insert"]} & platform_ids
    assert {g.granted_by for g in plan["insert"]} == {"backfill:decision-C"}
    assert "46" not in {g.user_id for g in plan["insert"]}, "inactive identities get nothing"


def test_backfill_keeps_active_grants_and_never_reactivates_a_revocation():
    existing = [
        fac.Grant(T1, "42", "farm-a", True, "owner:1"),
        fac.Grant(T1, "44", "farm-b", False, "owner:1"),
    ]
    plan = fac.plan_backfill(AUTH_USERS, FARMS, existing)
    assert [(g.user_id, g.farm_id) for g in plan["already_active"]] == [("42", "farm-a")]
    assert [(g.user_id, g.farm_id) for g in plan["skipped_revoked"]] == [("44", "farm-b")]
    assert ("44", "farm-b") not in {(g.user_id, g.farm_id) for g in plan["insert"]}


# ── the comparison ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sub", ["42", "43", "44"])  # manager, agronomist, worker
def test_after_the_backfill_each_role_keeps_exactly_the_same_farms(sub):
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, _backfilled())
    user = next(u for u in report["per_user"] if u["sub"] == sub)
    assert user["before"] == user["after"] == ["farm-a", "farm-b"]
    assert fac.failures(report) == []


def test_the_backfilled_comparison_is_clean_action_by_action():
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, _backfilled())
    assert report["counts"]["before"] == report["counts"]["after"] > 0
    assert report["counts"]["lost"] == report["counts"]["newly_permitted"] == 0


def test_negative_control_without_the_backfill_the_comparison_fails_with_lost():
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, [])
    assert fac.failures(report) == ["lost"]
    lost_users = {row["sub"] for row in report["lost"]}
    assert lost_users == {"42", "43", "44"}, "every non-owner loses; the owner keeps all farms"
    assert {row["farm_id"] for row in report["lost"]} == {"farm-a", "farm-b"}


def test_a_grant_keyed_by_the_platform_users_id_is_not_effective():
    """Hospital requirement 3: platform users.id 7 and auth sub 42 are the same manager."""
    by_platform_id = [
        fac.Grant(T1, pid, farm, True, "wrong-key")
        for pid in ("7", "8", "9")
        for farm in ("farm-a", "farm-b")
    ]
    wrong = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, by_platform_id)
    assert {r["sub"] for r in wrong["lost"]} == {"42", "43", "44"}, "the session key is the sub"
    assert {g["user_id"] for g in wrong["orphan_grants"]} == {"7", "8", "9"}
    assert fac.failures(wrong) == ["lost", "orphan_grants"]

    by_sub = [
        fac.Grant(T1, sub, farm, True, "right-key")
        for sub in ("42", "43", "44")
        for farm in ("farm-a", "farm-b")
    ]
    assert fac.failures(fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, by_sub)) == []


def test_a_partial_grant_loses_exactly_the_missing_farm():
    grants = [g for g in _backfilled() if not (g.user_id == "44" and g.farm_id == "farm-b")]
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, grants)
    assert {(r["sub"], r["farm_id"]) for r in report["lost"]} == {("44", "farm-b")}


def test_a_grant_on_another_tenants_farm_is_an_orphan_and_permits_nothing():
    grants = _backfilled() + [fac.Grant(T1, "42", "farm-z", True, "x")]
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, grants)
    assert report["newly_permitted"] == []
    assert [g["reasons"] for g in report["orphan_grants"]] == [["farm_not_in_grant_tenant"]]


def test_newly_permitted_is_reported_when_after_exceeds_before(monkeypatch):
    """Structurally empty while every farm policy is RESTRICTIVE; computed so a change that
    widens access (or a model bug) shows up and fails the run."""
    monkeypatch.setattr(fac, "scope_before", lambda users, farms: set())
    report = fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, _backfilled())
    assert report["newly_permitted"] and "newly_permitted" in fac.failures(report)


# ── the CLIs ──────────────────────────────────────────────────────────────────


def test_diff_exit_status_follows_the_failures(monkeypatch, capsys):
    diff = _load("farm_access_diff")
    monkeypatch.setenv("DATABASE_URL", "postgresql://platform")
    monkeypatch.setenv("AUTH_DATABASE_URL", "postgresql://auth")

    async def clean(platform_dsn, auth_dsn):
        assert (platform_dsn, auth_dsn) == ("postgresql://platform", "postgresql://auth")
        return fac.compare(PLATFORM_USERS, AUTH_USERS, FARMS, _backfilled())

    async def dirty(platform_dsn, auth_dsn):
        return fac.compare(
            PLATFORM_USERS + [fac.Identity("11", "x@y", T1, "w", True)], AUTH_USERS, FARMS, []
        )

    monkeypatch.setattr(diff, "collect", clean)
    assert diff.main([]) == 0
    assert capsys.readouterr().out.strip().endswith("OK: no difference")
    monkeypatch.setattr(diff, "collect", dirty)
    assert diff.main([]) == 1
    assert "FAIL: lost, unresolved" in capsys.readouterr().out


@pytest.mark.parametrize("script", ["farm_access_diff", "farm_access_backfill"])
def test_both_clis_require_the_separate_auth_dsn(monkeypatch, script):
    module = _load(script)
    monkeypatch.setenv("DATABASE_URL", "postgresql://platform")
    monkeypatch.delenv("AUTH_DATABASE_URL", raising=False)
    assert module.main([]) == 2


async def test_a_row_level_security_role_is_refused_instead_of_reporting_clean():
    class _Conn:
        def __init__(self, superuser, bypass):
            self.row = {"rolsuper": superuser, "rolbypassrls": bypass}

        async def fetchrow(self, sql):
            assert "pg_roles" in sql
            return self.row

    with pytest.raises(fac.Precondition):
        await fac.require_full_visibility(_Conn(False, False), "auth")
    await fac.require_full_visibility(_Conn(False, True), "auth")
    await fac.require_full_visibility(_Conn(True, False), "auth")
