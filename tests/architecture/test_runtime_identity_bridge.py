"""Guards for the runtime identity bridge — governance-only, evidence-gated, inert.

These tests assert the bridge is fail-closed on every identity/evidence gap and that
its mere existence flips nothing. They exercise: a valid committed bridge, unknown
service, ambiguous mapping, conflicting duplicate, and — at the propagation layer —
stale evidence, SHA mismatch, liveness-only evidence, and partial capability coverage.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts/ci/runtime_identity_bridge.py"
SHA = "a" * 40


def _mod():
    spec = importlib.util.spec_from_file_location("runtime_identity_bridge", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_bridge():
    return {
        "schema_version": "1.0",
        "service_identity": [
            {
                "ledger_service": "weather-service",
                "capability_service_path": "services/weather-service/main.py",
                "owner": "target-weather-system-of-record",
                "cardinality": "one-to-one",
                "functional_plan": "weather-service",
            }
        ],
        "capability_functional_coverage": [
            {
                "capability": "WX-004",
                "ledger_service": "weather-service",
                "requires_probes": ["agro-et0-fao56"],
            },
            {
                "capability": "WX-006",
                "ledger_service": "weather-service",
                "requires_probes": ["agro-gdd-accumulation"],
            },
        ],
        "evidence_policy": {
            "require_kind": "functional",
            "reject_liveness_only": True,
            "require_sha_match": True,
            "require_environment": True,
            "max_age_seconds": 2592000,
        },
    }


def _patch_known(m, monkeypatch, services=("weather-service",)):
    monkeypatch.setattr(m, "ledger_service_names", lambda: set(services))
    monkeypatch.setattr(m, "registry_service_paths", lambda: {"services/weather-service/main.py"})
    monkeypatch.setattr(
        m,
        "capability_service_paths",
        lambda: {
            "WX-004": {"services/weather-service/main.py"},
            "WX-006": {"services/weather-service/main.py"},
        },
    )
    monkeypatch.setattr(
        m, "functional_plan_probe_ids", lambda name: {"agro-et0-fao56", "agro-gdd-accumulation"}
    )


def _evidence(probe_ids, *, kind="functional", tested_sha=SHA, env="staging", age_days=0):
    ts = (datetime.now(UTC) - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "kind": kind,
        "service": "weather-service",
        "tested_sha": tested_sha,
        "environment_id": env,
        "generated_at": ts,
        "probe_results": [{"probe_id": p, "status": "passed"} for p in probe_ids],
    }


# ── the real committed bridge is valid and check-mode passes ──────────────────


def test_committed_bridge_is_valid():
    m = _mod()
    errors = m.validate_identity_map(json.loads(m.IDENTITY_MAP.read_text()))
    assert errors == [], errors


def test_check_mode_passes():
    assert _mod().cmd_check() == 0


# ── identity validation is fail-closed ───────────────────────────────────────


def test_unknown_service_is_rejected(monkeypatch):
    m = _mod()
    _patch_known(m, monkeypatch, services=("other-service",))  # weather-service now unknown
    errors = m.validate_identity_map(_valid_bridge())
    assert any("unknown ledger_service" in e for e in errors), errors


def test_ambiguous_mapping_rejected(monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "ledger_service_names", lambda: {"weather-service"})
    monkeypatch.setattr(m, "registry_service_paths", lambda: {"a.py", "b.py"})
    monkeypatch.setattr(m, "capability_service_paths", lambda: {})
    monkeypatch.setattr(m, "functional_plan_probe_ids", lambda name: {"p"})
    b = _valid_bridge()
    b["service_identity"] = [
        {
            "ledger_service": "weather-service",
            "capability_service_path": "a.py",
            "cardinality": "one-to-one",
            "functional_plan": "weather-service",
        },
        {
            "ledger_service": "weather-service",
            "capability_service_path": "b.py",
            "cardinality": "one-to-one",
            "functional_plan": "weather-service",
        },
    ]
    assert any("ambiguous mapping" in e for e in m.validate_identity_map(b))


def test_conflicting_duplicate_path_rejected(monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "ledger_service_names", lambda: {"svc-a", "svc-b"})
    monkeypatch.setattr(m, "registry_service_paths", lambda: {"shared.py"})
    monkeypatch.setattr(m, "capability_service_paths", lambda: {})
    monkeypatch.setattr(m, "functional_plan_probe_ids", lambda name: {"p"})
    b = _valid_bridge()
    b["service_identity"] = [
        {
            "ledger_service": "svc-a",
            "capability_service_path": "shared.py",
            "cardinality": "one-to-one",
            "functional_plan": "weather-service",
        },
        {
            "ledger_service": "svc-b",
            "capability_service_path": "shared.py",
            "cardinality": "one-to-one",
            "functional_plan": "weather-service",
        },
    ]
    assert any("conflicting mapping" in e for e in m.validate_identity_map(b))


# ── propagation is evidence-gated and fail-closed ────────────────────────────


def test_no_evidence_stays_zero():
    m = _mod()
    ev = m.evaluate_propagation(_valid_bridge(), {}, SHA, datetime.now(UTC))
    assert all(not e["would_set_runtime_verified"] for e in ev)
    assert all(e["reason"] == "no_functional_evidence" for e in ev)


def test_liveness_only_evidence_not_eligible():
    m = _mod()
    by = {"weather-service": [_evidence(["agro-et0-fao56"], kind="health")]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_bridge(), by, SHA, datetime.now(UTC))
    }
    assert not ev["WX-004"]["would_set_runtime_verified"]
    assert "functional" in ev["WX-004"]["reason"] or "liveness" in ev["WX-004"]["reason"]


def test_sha_mismatch_evidence_not_eligible():
    m = _mod()
    by = {"weather-service": [_evidence(["agro-et0-fao56"], tested_sha="b" * 40)]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_bridge(), by, SHA, datetime.now(UTC))
    }
    assert not ev["WX-004"]["would_set_runtime_verified"]
    assert "sha_mismatch" in ev["WX-004"]["reason"]


def test_stale_evidence_not_eligible():
    m = _mod()
    by = {"weather-service": [_evidence(["agro-et0-fao56"], age_days=60)]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_bridge(), by, SHA, datetime.now(UTC))
    }
    assert not ev["WX-004"]["would_set_runtime_verified"]
    assert "stale" in ev["WX-004"]["reason"]


def test_partial_coverage_not_eligible():
    m = _mod()
    # valid evidence but only the et0 probe passed; WX-004 covered, WX-006 not.
    by = {"weather-service": [_evidence(["agro-et0-fao56"])]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["WX-004"]["would_set_runtime_verified"] is True
    assert ev["WX-006"]["would_set_runtime_verified"] is False
    assert "partial_coverage" in ev["WX-006"]["reason"]


def test_full_coverage_would_be_eligible_but_bridge_writes_nothing():
    m = _mod()
    by = {"weather-service": [_evidence(["agro-et0-fao56", "agro-gdd-accumulation"])]}
    ev = m.evaluate_propagation(_valid_bridge(), by, SHA, datetime.now(UTC))
    assert all(e["would_set_runtime_verified"] for e in ev)
    # Inertness: evaluation is a pure computation. The committed registry is untouched —
    # no capability is actually runtime_verified just because the bridge exists.
    reg = json.loads(m.CAPABILITY_REGISTRY.read_text())
    for cap in reg["capabilities"]:
        if cap["id"] in ("WX-004", "WX-006"):
            assert not cap.get("runtime_verified"), cap["id"]


# ── multi-service: the bridge generalizes beyond weather, still fail-closed ───────


def _valid_multi_bridge():
    b = _valid_bridge()
    b["service_identity"].append(
        {
            "ledger_service": "soil-service",
            "capability_service_path": "services/soil-service/main.py",
            "owner": "target-soil-system-of-record",
            "cardinality": "one-to-one",
            "functional_plan": "soil-service",
        }
    )
    b["capability_functional_coverage"].append(
        {
            "capability": "SOIL-001",
            "ledger_service": "soil-service",
            "requires_probes": ["soil-texture-loam", "soil-texture-sand"],
        }
    )
    return b


def _patch_known_multi(m, monkeypatch, services=("weather-service", "soil-service")):
    monkeypatch.setattr(m, "ledger_service_names", lambda: set(services))
    monkeypatch.setattr(
        m,
        "registry_service_paths",
        lambda: {"services/weather-service/main.py", "services/soil-service/main.py"},
    )
    monkeypatch.setattr(
        m,
        "capability_service_paths",
        lambda: {
            "WX-004": {"services/weather-service/main.py"},
            "WX-006": {"services/weather-service/main.py"},
            "SOIL-001": {"services/soil-service/main.py"},
        },
    )
    plans = {
        "weather-service": {"agro-et0-fao56", "agro-gdd-accumulation"},
        "soil-service": {"soil-texture-loam", "soil-texture-sand"},
    }
    monkeypatch.setattr(m, "functional_plan_probe_ids", lambda name: plans.get(name))


def _soil_evidence(probe_ids, **kw):
    ev = _evidence(probe_ids, **kw)
    ev["service"] = "soil-service"
    return ev


def test_committed_bridge_is_multi_service():
    # The real committed map must carry every wired service (guards against silently
    # dropping one when another is added) and declare each service's capabilities.
    m = _mod()
    bridge = json.loads(m.IDENTITY_MAP.read_text())
    names = {e["ledger_service"] for e in bridge["service_identity"]}
    assert {"weather-service", "soil-service", "sahool-platform"} <= names
    caps = {c["capability"] for c in bridge["capability_functional_coverage"]}
    assert {"WX-004", "WX-006", "SOIL-001", "IRR-009", "IRR-010"} <= caps


def test_multi_service_bridge_validates(monkeypatch):
    m = _mod()
    _patch_known_multi(m, monkeypatch)
    assert m.validate_identity_map(_valid_multi_bridge()) == []


def test_unknown_second_service_rejected(monkeypatch):
    m = _mod()
    _patch_known_multi(m, monkeypatch, services=("weather-service",))  # soil now unknown
    errors = m.validate_identity_map(_valid_multi_bridge())
    assert any("unknown ledger_service 'soil-service'" in e for e in errors), errors


def test_cross_service_conflicting_path_rejected(monkeypatch):
    m = _mod()
    _patch_known_multi(m, monkeypatch)
    b = _valid_multi_bridge()
    # soil now claims weather's path — one path owned by two services must be rejected.
    b["service_identity"][1]["capability_service_path"] = "services/weather-service/main.py"
    assert any("conflicting mapping" in e for e in m.validate_identity_map(b))


def test_evidence_is_isolated_per_service():
    # Full soil evidence makes SOIL-001 eligible but must NOT make the weather caps
    # eligible — propagation is strictly per declared service.
    m = _mod()
    by = {"soil-service": [_soil_evidence(["soil-texture-loam", "soil-texture-sand"])]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is True
    assert ev["WX-004"]["would_set_runtime_verified"] is False
    assert ev["WX-006"]["would_set_runtime_verified"] is False
    assert ev["WX-004"]["reason"] == "no_functional_evidence"


def test_soil_partial_coverage_not_eligible():
    m = _mod()
    by = {"soil-service": [_soil_evidence(["soil-texture-loam"])]}  # missing the sand probe
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is False
    assert "partial_coverage" in ev["SOIL-001"]["reason"]


def test_soil_stale_evidence_not_eligible():
    m = _mod()
    by = {"soil-service": [_soil_evidence(["soil-texture-loam", "soil-texture-sand"], age_days=60)]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is False
    assert "stale" in ev["SOIL-001"]["reason"]


def test_soil_sha_mismatch_not_eligible():
    m = _mod()
    by = {
        "soil-service": [
            _soil_evidence(["soil-texture-loam", "soil-texture-sand"], tested_sha="b" * 40)
        ]
    }
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is False
    assert "sha_mismatch" in ev["SOIL-001"]["reason"]


def test_soil_liveness_only_not_eligible():
    m = _mod()
    by = {
        "soil-service": [_soil_evidence(["soil-texture-loam", "soil-texture-sand"], kind="health")]
    }
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is False
    assert "functional" in ev["SOIL-001"]["reason"] or "liveness" in ev["SOIL-001"]["reason"]


def test_soil_full_coverage_would_flip_but_registry_untouched():
    m = _mod()
    by = {"soil-service": [_soil_evidence(["soil-texture-loam", "soil-texture-sand"])]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_valid_multi_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["SOIL-001"]["would_set_runtime_verified"] is True
    # inertness: the committed registry's SOIL-001 is not runtime_verified.
    reg = json.loads(m.CAPABILITY_REGISTRY.read_text())
    for cap in reg["capabilities"]:
        if cap["id"] == "SOIL-001":
            assert not cap.get("runtime_verified"), cap["id"]


# ── third service (sahool-platform, JWT-gated) is wired the same fail-closed way ──


def _tri_bridge():
    """The full committed shape: weather + soil + platform."""
    b = _valid_multi_bridge()
    b["service_identity"].append(
        {
            "ledger_service": "sahool-platform",
            "capability_service_path": "services/sahool-platform/api/main.py",
            "owner": "target-platform-system-of-record",
            "cardinality": "one-to-one",
            "functional_plan": "sahool-platform",
        }
    )
    b["capability_functional_coverage"].append(
        {
            "capability": "IRR-009",
            "ledger_service": "sahool-platform",
            "requires_probes": ["water-suitability-multihazard"],
        }
    )
    b["capability_functional_coverage"].append(
        {
            "capability": "IRR-010",
            "ledger_service": "sahool-platform",
            "requires_probes": ["leaching-requirement-fao56"],
        }
    )
    return b


def _platform_evidence(probe_ids, **kw):
    ev = _evidence(probe_ids, **kw)
    ev["service"] = "sahool-platform"
    return ev


def test_platform_two_capabilities_flip_independently():
    # IRR-009 and IRR-010 are backed by DIFFERENT probes on the same service; evidence
    # for one must not flip the other. Only the multi-hazard probe passed here.
    m = _mod()
    by = {"sahool-platform": [_platform_evidence(["water-suitability-multihazard"])]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_tri_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["IRR-009"]["would_set_runtime_verified"] is True
    assert ev["IRR-010"]["would_set_runtime_verified"] is False
    assert "partial_coverage" in ev["IRR-010"]["reason"]


def test_platform_evidence_does_not_touch_other_services():
    # Full platform evidence flips its own caps but leaves weather/soil at zero.
    m = _mod()
    by = {
        "sahool-platform": [
            _platform_evidence(["water-suitability-multihazard", "leaching-requirement-fao56"])
        ]
    }
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_tri_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["IRR-009"]["would_set_runtime_verified"] is True
    assert ev["IRR-010"]["would_set_runtime_verified"] is True
    for cap in ("WX-004", "WX-006", "SOIL-001"):
        assert ev[cap]["would_set_runtime_verified"] is False
        assert ev[cap]["reason"] == "no_functional_evidence"


def test_platform_sha_mismatch_not_eligible():
    m = _mod()
    by = {
        "sahool-platform": [
            _platform_evidence(["water-suitability-multihazard"], tested_sha="b" * 40)
        ]
    }
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_tri_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["IRR-009"]["would_set_runtime_verified"] is False
    assert "sha_mismatch" in ev["IRR-009"]["reason"]


def test_platform_liveness_only_not_eligible():
    m = _mod()
    by = {"sahool-platform": [_platform_evidence(["water-suitability-multihazard"], kind="health")]}
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_tri_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["IRR-009"]["would_set_runtime_verified"] is False
    assert "functional" in ev["IRR-009"]["reason"] or "liveness" in ev["IRR-009"]["reason"]


def test_platform_full_coverage_would_flip_but_registry_untouched():
    m = _mod()
    by = {
        "sahool-platform": [
            _platform_evidence(["water-suitability-multihazard", "leaching-requirement-fao56"])
        ]
    }
    ev = {
        e["capability"]: e
        for e in m.evaluate_propagation(_tri_bridge(), by, SHA, datetime.now(UTC))
    }
    assert ev["IRR-009"]["would_set_runtime_verified"] is True
    assert ev["IRR-010"]["would_set_runtime_verified"] is True
    reg = json.loads(m.CAPABILITY_REGISTRY.read_text())
    for cap in reg["capabilities"]:
        if cap["id"] in ("IRR-009", "IRR-010"):
            assert not cap.get("runtime_verified"), cap["id"]
