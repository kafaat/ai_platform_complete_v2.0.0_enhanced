"""RZ-VARIETY-POLICY-RESOLUTION-01: two-tier, fail-closed root-policy resolution.

The fake DB routes crop_root_policies lookups by the query ARGUMENTS
(tenant, crop, variety) — never by call order — so a resolver that queries the
wrong tier, the wrong variety, or skips the tenant filter selects the wrong row
and fails loudly, instead of being handed the next row regardless.
"""

from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.unit


def _policy(policy_id: str, variety: str, version: str = "v1", **overrides):
    row = {
        "policy_id": policy_id,
        "initial_depth_m": 0.2,
        "maximum_depth_m": 1.0,
        "effective_fraction": 0.8,
        "policy_version": version,
        "evidence_ids": [f"evidence-{policy_id}"],
        "variety": variety,
    }
    row.update(overrides)
    return row


class _PolicyDB:
    """Args-routed fake: policies keyed by (tenant_id, crop_id, variety)."""

    def __init__(self, policies):
        self.policies = {
            (p_tenant, p_crop, p["variety"]): p
            for (p_tenant, p_crop), rows in policies.items()
            for p in rows
        }
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        if "FROM soil_lab_tests" in sql:
            return None
        if "FROM crop_root_policies" not in sql:
            raise AssertionError(f"unexpected query: {sql}")
        if "variety=$3" in sql:
            assert len(args) == 3, "exact-tier query must bind the variety"
            key = (args[0], args[1], args[2])
        elif "variety=''" in sql:
            assert len(args) == 2, "generic-tier query must not bind a variety"
            key = (args[0], args[1], "")
        else:
            raise AssertionError("policy query must constrain variety explicitly")
        return self.policies.get(key)

    @property
    def policy_calls(self):
        return [(sql, args) for sql, args in self.calls if "FROM crop_root_policies" in sql]


def _db(*rows, tenant="tenant-1", crop="wheat"):
    return _PolicyDB({(tenant, crop): list(rows)})


async def _resolve(monkeypatch, conn, *, variety, crop="wheat"):
    import api.canonical_root_zone_profile as module
    from api.canonical_root_zone_profile import resolve_canonical_root_zone_profile

    async def soil(**_kwargs):
        return {"profile_id": "soil-1", "layers": []}

    def build(**kwargs):
        return type(
            "Profile",
            (),
            {
                "root_policy_id": kwargs["root_policy"]["policy_id"],
                "root_policy_version": kwargs["root_policy"]["policy_version"],
                "root_policy_variety": kwargs["root_policy"].get("variety"),
                "selected_policy": dict(kwargs["root_policy"]),
            },
        )()

    async def persist(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module, "get_soil_hydraulic_profile", soil)
    monkeypatch.setattr(module, "build_canonical_root_zone_profile", build)
    monkeypatch.setattr(module, "persist_canonical_root_zone_profile", persist)

    return await resolve_canonical_root_zone_profile(
        conn,
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        crop=crop,
        phenology_progress=0.5,
        raw_fraction=0.5,
        variety=variety,
    )


async def test_rz_v01_exact_variety_wins_while_generic_is_present(monkeypatch):
    conn = _db(_policy("exact", "imam"), _policy("generic", ""))
    out = await _resolve(monkeypatch, conn, variety="imam")

    assert out.root_policy_id == "exact"
    assert out.root_policy_variety == "imam"
    assert len(conn.policy_calls) == 1
    assert conn.policy_calls[0][1] == ("tenant-1", "wheat", "imam")


async def test_rz_v02_unknown_variety_falls_back_to_generic_crop_policy(monkeypatch):
    conn = _db(_policy("generic", ""))
    out = await _resolve(monkeypatch, conn, variety="unknown-variety")

    assert out.root_policy_id == "generic"
    assert out.root_policy_variety == ""
    assert [args for _sql, args in conn.policy_calls] == [
        ("tenant-1", "wheat", "unknown-variety"),
        ("tenant-1", "wheat"),
    ]


async def test_rz_v03_variety_a_resolves_a_never_b(monkeypatch):
    conn = _db(
        _policy("policy-A", "A", initial_depth_m=0.30, maximum_depth_m=1.20),
        _policy("policy-B", "B", initial_depth_m=0.25, maximum_depth_m=0.90),
        _policy("generic", ""),
    )
    out = await _resolve(monkeypatch, conn, variety="A")

    assert out.root_policy_id == "policy-A"
    assert out.root_policy_id != "policy-B"
    assert out.root_policy_variety == "A"
    assert out.selected_policy["initial_depth_m"] == 0.30
    assert out.selected_policy["maximum_depth_m"] == 1.20


async def test_rz_v04_no_exact_and_no_generic_is_blocked(monkeypatch):
    conn = _db(_policy("other-variety-only", "B"))
    out = await _resolve(monkeypatch, conn, variety="A")

    assert out == {
        "status": "blocked",
        "reason": "validated_crop_root_policy_missing",
    }
    assert len(conn.policy_calls) == 2


async def test_rz_v05_both_tiers_filter_on_validated_and_validity_window(monkeypatch):
    conn = _db(_policy("generic", ""))
    out = await _resolve(monkeypatch, conn, variety="imam")

    assert out.root_policy_id == "generic"
    assert len(conn.policy_calls) == 2
    for sql, _args in conn.policy_calls:
        assert "status='validated'" in sql
        assert "valid_from <= now()" in sql
        assert "valid_to IS NULL OR valid_to > now()" in sql
        assert "tenant_id=$1::uuid" in sql


async def test_rz_v06_missing_variety_uses_generic_without_exact_lookup(monkeypatch):
    conn = _db(_policy("generic", ""), _policy("exact", "imam"))
    out = await _resolve(monkeypatch, conn, variety=None)

    assert out.root_policy_id == "generic"
    assert len(conn.policy_calls) == 1
    assert conn.policy_calls[0][1] == ("tenant-1", "wheat")


async def test_rz_v07_whitespace_variety_is_treated_as_missing(monkeypatch):
    conn = _db(_policy("generic", ""))
    out = await _resolve(monkeypatch, conn, variety="   ")

    assert out.root_policy_id == "generic"
    assert len(conn.policy_calls) == 1
    assert conn.policy_calls[0][1] == ("tenant-1", "wheat")


# ---------------------------------------------------------------------------
# Real-build evidence: digest/version/variety are measured on the actual
# build_canonical_root_zone_profile, not on a monkeypatched stand-in.
# ---------------------------------------------------------------------------

_SOIL_PROFILE = {
    "executable": True,
    "profile_id": "soil-real-1",
    "source_soil_profile_hash": "a" * 64,
    "generated_at": datetime.now(UTC).isoformat(),
    "layers": [
        {
            "depth_from_cm": 0,
            "depth_to_cm": 200,
            "field_capacity": {"value": 0.32, "origin": "measured", "confidence": 0.9},
            "wilting_point": {"value": 0.12, "origin": "measured", "confidence": 0.9},
            "coarse_fragments": {"value": 5, "origin": "measured", "confidence": 0.9},
            "infiltration": {"value": 12.0, "origin": "measured", "confidence": 0.9},
            "ksat": {"value": 20.0, "origin": "measured", "confidence": 0.9},
        }
    ],
}


def _build(policy):
    from api.canonical_root_zone_profile import (
        CanonicalRootZoneProfile,
        build_canonical_root_zone_profile,
    )

    profile = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        crop="wheat",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=policy,
        soil_profile=_SOIL_PROFILE,
    )
    assert isinstance(profile, CanonicalRootZoneProfile), profile
    return profile


def test_rz_v08_policy_version_change_changes_real_digest_and_is_recorded():
    p1 = _build(_policy("pol-1", "imam", "v1", maximum_depth_m=1.2))
    p2 = _build(_policy("pol-1", "imam", "v2", maximum_depth_m=0.9))

    assert p1.root_policy_version == "v1"
    assert p2.root_policy_version == "v2"
    assert p1.profile_digest != p2.profile_digest
    # The first snapshot is immutable evidence: rebuilding v2 must not mutate it.
    assert p1.root_policy_version == "v1"
    with pytest.raises(AttributeError):
        p1.root_policy_version = "tampered"  # frozen dataclass


def test_rz_v09_selected_variety_is_recorded_in_the_real_snapshot():
    exact = _build(_policy("pol-exact", "imam"))
    generic = _build(_policy("pol-generic", ""))

    assert exact.root_policy_variety == "imam"
    assert generic.root_policy_variety == ""
    assert exact.to_dict()["root_policy_variety"] == "imam"
    assert exact.profile_digest != generic.profile_digest
