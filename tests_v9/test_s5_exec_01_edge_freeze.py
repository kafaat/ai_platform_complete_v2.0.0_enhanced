from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/architecture/s5_exec_01_edge_freeze.py"
SPEC = importlib.util.spec_from_file_location("s5_edge_freeze", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_frozen_runtime_surface_and_legacy_receipt_are_stable():
    data = mod.build()
    # The authority-bearing migration surface is unchanged even though end-state tests and
    # destination-service witnesses have legitimately grown since the original freeze.
    assert data["runtime_migration_surface_counts"] == {"total": 31, "reads": 25, "writes": 6}
    assert data["frozen_runtime_migration_surface_counts"] == {
        "total": 31,
        "reads": 25,
        "writes": 6,
    }
    assert data["runtime_migration_surface_fingerprint_sha256"] == (
        "bb8565c7a42368ee57cb01a3b4ec42dec1d2b5c676425b6b62b45df38d7ef7a7"
    )
    assert (
        data["runtime_migration_surface_fingerprint_sha256"]
        == data["runtime_migration_surface_frozen_sha256"]
    )
    assert (
        data["runtime_writer_surface_fingerprint_sha256"]
        == data["runtime_writer_surface_frozen_sha256"]
    )
    # Compatibility receipt remains the original full-graph freeze value. The observed full
    # graph may equal it (as on this main-based forward-port) or may grow via non-authority
    # witnesses; authority is frozen by the runtime migration fingerprint above.
    assert data["edge_fingerprint_sha256"] == (
        "34f240e7e3ca33dcdcc3b54dd88e3ce6c9052b4bb540ee3901ad2f3801088c1a"
    )
    assert isinstance(data["observed_edge_fingerprint_sha256"], str)
    assert len(data["observed_edge_fingerprint_sha256"]) == 64
    assert mod.invariant_findings(data) == []


def test_runtime_writer_cutover_set_is_exact():
    data = mod.build()
    actual = {row["table"]: row["writers"] for row in data["writer_cutover_set_runtime_only"]}
    assert actual == {
        "recommendation_outcomes": ["services/sahool-platform/api/routers/recommendations.py"],
        "outcome_record": ["services/sahool-platform/api/routers/decision_record.py"],
        "decision_record": [
            "services/sahool-platform/api/routers/decision_record.py",
            "services/sahool-platform/api/routers/weather.py",
        ],
        "dispatch_decisions": ["services/sahool-platform/api/routers/decision_dispatch.py"],
        "online_learning_updates": ["services/sahool-platform/api/phase_runtime_store.py"],
    }


def test_generator_owns_edge_class_and_artifact_is_exact():
    generated = mod.build()
    stored = json.loads(
        (ROOT / "docs/architecture/s5_exec_01_edge_freeze.json").read_text(encoding="utf-8")
    )
    assert stored == generated
    assert all(
        edge["edge_class"] in {"runtime", "test_witness"}
        for batch in generated["migration_batches"].values()
        for cls in ("runtime", "test_witness")
        for direction in ("reads", "writes")
        for edge in batch[cls][direction]
    )


def test_test_witnesses_are_not_migration_surface_and_cannot_fall_below_freeze_floor():
    data = mod.build()
    assert (
        data["counts"]["test_witness_total"]
        >= data["non_migration_witness_floor"]["test_witness_total"]
    )
    assert (
        data["counts"]["decision_service_total"]
        >= data["non_migration_witness_floor"]["decision_service_total"]
    )
    assert "NOT migration surface" in data["test_witness_policy"]

    # Growth is allowed; a loss below the original witness receipt is fail-closed.
    mutated = dict(data)
    mutated["counts"] = dict(data["counts"], test_witness_total=18)
    assert any("NON_MIGRATION_WITNESS_FLOOR_BREACH" in x for x in mod.invariant_findings(mutated))


def test_runtime_surface_growth_is_fail_closed_even_if_observed_graph_is_regenerated():
    data = mod.build()
    mutated = dict(data)
    mutated["runtime_migration_surface_fingerprint_sha256"] = "0" * 64
    assert "RUNTIME_MIGRATION_SURFACE_FINGERPRINT_DRIFT" in mod.invariant_findings(mutated)
