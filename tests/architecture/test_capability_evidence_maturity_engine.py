from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/capability_evidence_maturity_engine.py"
OUT = ROOT / "docs/capability-registry/generated/evidence"
MATRIX = OUT / "capability_evidence_matrix.json"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True
    )


def test_evidence_maturity_has_no_drift() -> None:
    result = run("--check")
    assert result.returncode == 0, result.stderr


def test_matrix_covers_registry_exactly() -> None:
    registry = json.loads(
        (ROOT / "docs/capability-registry/generated/capability_registry.json").read_text()
    )
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    assert {c["id"] for c in registry["capabilities"]} == {
        c["capability_id"] for c in matrix["capabilities"]
    }
    assert matrix["summary"]["capability_count"] == 81


def test_fail_closed_maturity_rules() -> None:
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    assert matrix["constraints"]["automatic_registry_update"] is False
    assert matrix["constraints"]["runtime_required_for_level_4"] is True
    assert matrix["constraints"]["production_required_for_level_5"] is True
    for record in matrix["capabilities"]:
        assert 0 <= record["assessed_maturity"] <= 5
        if record["assessed_maturity"] >= 4:
            assert record["runtime_verified"] is True
        if record["assessed_maturity"] == 5:
            assert record["production_certified"] is True
        assert record["automatic_registry_update"] is False


def test_runtime_instrumentation_is_not_runtime_proof() -> None:
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    instrumented = [r for r in matrix["capabilities"] if r["evidence"]["runtime_instrumentation"]]
    assert instrumented
    assert all(not r["runtime_verified"] for r in matrix["capabilities"])
    assert all(not r["production_certified"] for r in matrix["capabilities"])


def test_manifest_covers_all_generated_files() -> None:
    manifest = json.loads((OUT / "evidence_manifest.json").read_text())
    assert set(manifest) == {
        "CAPABILITY_EVIDENCE_MATURITY_REPORT.md",
        "capability_evidence_matrix.csv",
        "capability_evidence_matrix.json",
        "capability_maturity_baseline.csv",
        "capability_maturity_baseline.json",
        "domain_maturity_summary.json",
    }


# --- C-40 (#1428): a test's evidence type comes from its explicit pytest markers -------------
# classify_tests used to count any path containing "contract" as integration evidence, checked
# before the unit tokens, so a `pytestmark = pytest.mark.unit` source-only test could lift a
# capability to assessed maturity 3. These cases pin the marker-first taxonomy, the
# "contract"-alone rule, and the fail-closed consistency gate.

# Verified marker/category mismatches from the issue: each is unit-marked and reads source only.
UNIT_MARKED_CONTRACT_TESTS = {
    "tests_v9/test_canonical_field_geometry_contract.py": "FM-003",
    "tests_v9/test_frontend_tilejson_date_contract_guard.py": "SAT-009",
    "tests_v9/test_mfa_migration_contract_guard.py": "SEC-004",
    "services/sahool-platform/tests/test_router_registry_contract.py": "SEC-006",
}
# True live-PG integration positive controls (module ``pytestmark`` carries ``integration``).
LIVE_PG_INTEGRATION = "tests_v9/test_v237_tenant_isolation_live_pg.py"
LIVE_PG_CONTRACT_INTEGRATION = "tests_v9/test_sql_prepare_contract_live_pg.py"


def _load():
    path = SCRIPT
    spec = importlib.util.spec_from_file_location("capability_evidence_maturity_engine", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def engine():
    return _load()


@pytest.fixture()
def sandbox(engine, tmp_path, monkeypatch):
    """Point the engine at a scratch root so synthetic test files can be classified."""
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    engine.explicit_test_markers.cache_clear()

    def write(name: str, body: str) -> str:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return name

    yield write
    engine.explicit_test_markers.cache_clear()


@pytest.mark.parametrize("path", sorted(UNIT_MARKED_CONTRACT_TESTS))
def test_unit_marked_contract_tests_are_unit_evidence(engine, path: str) -> None:
    assert engine.classify_test_path(path) == ("unit", "pytest.mark.unit")
    unit, integration = engine.classify_tests([{"path": path}])
    assert unit == [path] and integration == []


@pytest.mark.parametrize("path", sorted(UNIT_MARKED_CONTRACT_TESTS))
def test_committed_matrix_no_longer_lists_unit_marked_contract_tests_as_integration(
    path: str,
) -> None:
    cid = UNIT_MARKED_CONTRACT_TESTS[path]
    record = next(
        r
        for r in json.loads(MATRIX.read_text(encoding="utf-8"))["capabilities"]
        if r["capability_id"] == cid
    )
    assert path not in record["integration_test_paths"]
    assert path in record["unit_test_paths"]
    attribution = {a["path"]: a for a in record["test_evidence_attribution"]}
    assert attribution[path] == {
        "path": path,
        "evidence_type": "unit",
        "signal": "pytest.mark.unit",
    }


@pytest.mark.parametrize("path", [LIVE_PG_INTEGRATION, LIVE_PG_CONTRACT_INTEGRATION])
def test_live_pg_integration_marker_is_integration_evidence(engine, path: str) -> None:
    # Positive control: a real live-PG test keeps integration evidence even when its name
    # says "contract" — the marker, not the name, decides.
    assert engine.classify_test_path(path) == ("integration", "pytest.mark.integration")


def test_contract_alone_does_not_promote_an_unmarked_file(engine, sandbox) -> None:
    plain = sandbox("tests/test_payload_contract.py", "def test_shape():\n    assert True\n")
    assert engine.classify_test_path(plain) == (
        "unit",
        "filename:contract_without_integration_signal",
    )
    # Negative control: another integration token in the name still promotes when unmarked.
    e2e = sandbox("tests/test_payload_contract_e2e.py", "def test_shape():\n    assert True\n")
    assert engine.classify_test_path(e2e) == ("integration", "filename:e2e")


def test_explicit_markers_override_the_filename(engine, sandbox) -> None:
    unit_e2e = sandbox(
        "tests/test_flow_e2e.py",
        "import pytest\npytestmark = pytest.mark.unit\ndef test_a():\n    assert True\n",
    )
    assert engine.classify_test_path(unit_e2e) == ("unit", "pytest.mark.unit")
    integ_plain = sandbox(
        "tests/test_store.py",
        "import pytest\n"
        "pytestmark = [pytest.mark.integration, pytest.mark.slow]\n"
        "def test_a():\n    assert True\n",
    )
    assert engine.classify_test_path(integ_plain) == ("integration", "pytest.mark.integration")


def test_per_test_markers_and_unit_precedence(engine, sandbox) -> None:
    class_level = sandbox(
        "tests/test_cls.py",
        "import pytest\n@pytest.mark.integration\nclass TestLive:\n"
        "    def test_a(self):\n        assert True\n"
        "@pytest.mark.unit\ndef test_b():\n    assert True\n",
    )
    assert engine.classify_test_path(class_level) == ("integration", "pytest.mark.integration")
    # A test carrying both markers (module unit + its own integration) is unit evidence:
    # an explicit unit marker never yields integration.
    both = sandbox(
        "tests/test_both_contract.py",
        "import pytest\npytestmark = pytest.mark.unit\n"
        "@pytest.mark.integration\ndef test_a():\n    assert True\n",
    )
    assert engine.classify_test_path(both) == ("unit", "pytest.mark.unit")


def test_markers_are_read_without_importing_the_test(engine, sandbox) -> None:
    exploding = sandbox(
        "tests/test_boom_contract.py",
        "import pytest\nraise SystemExit('imported')\n"
        "pytestmark = pytest.mark.integration\ndef test_a():\n    assert True\n",
    )
    assert engine.classify_test_path(exploding) == ("integration", "pytest.mark.integration")


def _record(path: str, kind: str) -> dict:
    return {
        "capability_id": "X-001",
        "unit_test_paths": [path] if kind == "unit" else [],
        "integration_test_paths": [path] if kind == "integration" else [],
        "test_evidence_attribution": [
            {"path": path, "evidence_type": kind, "signal": "pytest.mark.unit"}
        ],
    }


def test_gate_fails_closed_on_unit_marked_integration_evidence(engine) -> None:
    path = "tests_v9/test_mfa_migration_contract_guard.py"
    errors = engine.taxonomy_conflicts([_record(path, "integration")])
    assert errors == [f"X-001:{path}:integration_evidence_with_explicit_unit_marker"]
    # Negative control: the same file listed as unit evidence passes the gate.
    assert engine.taxonomy_conflicts([_record(path, "unit")]) == []


def test_gate_fails_on_missing_attribution(engine) -> None:
    record = _record(LIVE_PG_INTEGRATION, "integration")
    assert engine.taxonomy_conflicts([record]) == []
    record["test_evidence_attribution"] = []
    assert engine.taxonomy_conflicts([record]) == [
        f"X-001:{LIVE_PG_INTEGRATION}:attribution_mismatch:integration"
    ]


def test_committed_matrix_passes_the_gate_and_attributes_every_path(engine) -> None:
    records = json.loads(MATRIX.read_text(encoding="utf-8"))["capabilities"]
    assert engine.taxonomy_conflicts(records) == []
    for r in records:
        listed = set(r["unit_test_paths"]) | set(r["integration_test_paths"])
        assert {a["path"] for a in r["test_evidence_attribution"]} == listed


def test_build_refuses_a_regressed_filename_classifier(engine, monkeypatch) -> None:
    # Reintroduce the pre-C-40 rule ("contract" checked before unit tokens, markers ignored):
    # build() must fail closed instead of emitting unit-marked integration evidence.
    def filename_only(path: str):
        low = path.lower()
        if any(t in low for t in (*engine.INTEGRATION_TOKENS, "contract")):
            return "integration", "filename"
        if any(t in low for t in engine.UNIT_TOKENS):
            return "unit", "filename"
        return None, "unclassified"

    monkeypatch.setattr(engine, "classify_test_path", filename_only)
    with pytest.raises(ValueError, match="integration_evidence_with_explicit_unit_marker"):
        engine.build()
