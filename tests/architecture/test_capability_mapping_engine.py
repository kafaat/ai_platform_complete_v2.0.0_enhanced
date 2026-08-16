from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/capability_mapping_engine.py"
OUT = ROOT / "docs/capability-registry/generated/mapping"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True
    )


def test_mapping_has_no_drift() -> None:
    result = run("--check")
    assert result.returncode == 0, result.stderr


def test_mapping_covers_canonical_registry_without_runtime_claims() -> None:
    registry = json.loads(
        (ROOT / "docs/capability-registry/generated/capability_registry.json").read_text()
    )
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    assert {c["id"] for c in registry["capabilities"]} == {
        c["capability_id"] for c in mapping["capabilities"]
    }
    assert mapping["constraints"] == {
        "runtime_claims": False,
        "production_certification": False,
        "automatic_maturity_upgrade": False,
    }
    assert all(c["runtime_verified"] is False for c in mapping["capabilities"])
    assert all(c["production_certified"] is False for c in mapping["capabilities"])


def test_mapping_outputs_review_queues_and_manifest() -> None:
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    assert mapping["summary"]["files_scanned"] > 0
    assert mapping["summary"]["capabilities_mapped"] > 0
    assert (OUT / "unmapped_artifacts.json").exists()
    assert (OUT / "ambiguous_artifacts.json").exists()
    manifest = json.loads((OUT / "mapping_manifest.json").read_text())
    assert set(manifest) == {
        "CAPABILITY_MAPPING_REPORT.md",
        "ambiguous_artifacts.json",
        "capability_mapping.csv",
        "capability_mapping.json",
        "unmapped_artifacts.json",
    }


def test_each_mapping_record_has_all_evidence_dimensions() -> None:
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    dimensions = {
        "backend",
        "routes",
        "database",
        "events",
        "web",
        "mobile",
        "tests",
        "governance",
        "other_evidence",
    }
    for record in mapping["capabilities"]:
        assert dimensions <= record.keys()
        assert set(record["evidence_counts"]) == dimensions
        assert 0 <= record["coverage_dimensions"] <= 7


def test_raw_mapping_is_marked_non_authoritative() -> None:
    # The raw scanner artifact must self-declare that it is NOT the canonical mapped
    # state, so a downstream reader can never mistake it for the management matrix.
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    assert mapping["authoritative"] is False
    assert mapping["authoritative_mapped_state_source"] == (
        "docs/capability-registry/generated/management/coverage_dashboard.json"
    )


def test_raw_mapped_never_promoted_by_governance_or_other_evidence() -> None:
    # HONESTY INVARIANT: a capability is raw-``mapped`` iff it has >=1 SPECIFIC
    # implementation dimension. ``governance``/``other_evidence`` (bare ID mentions,
    # narrative, generated files) must never promote a capability on their own — the
    # exact contradiction the forensic review flagged (e.g. INT-001/WX-001 lifted by a
    # stray mention while declaring zero implementation evidence).
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    specific = ("backend", "routes", "database", "events", "web", "mobile", "tests")
    for c in mapping["capabilities"]:
        spec_dims = sum(bool(c[k]) for k in specific)
        assert c["mapped"] == (spec_dims > 0), c["capability_id"]
        if c["mapped"]:
            assert spec_dims > 0, c["capability_id"]


def test_raw_scanner_mapped_is_subset_of_authoritative_management() -> None:
    # Cross-artifact invariant: the raw scanner is an honest LOWER BOUND. Every
    # capability the scanner maps MUST also be mapped by the authoritative management
    # matrix (scanner evidence ⊆ scanner ∪ registry-declared). Equality is intentionally
    # NOT required: management additionally credits registry-declared on-disk evidence the
    # content scanner cannot attribute (e.g. IRR-010/OPS-001/OPS-006/OPS-008), so it may
    # map strictly more. A scanner-mapped capability that management leaves unmapped would
    # mean the scanner invented evidence — that is the failure this guards against.
    mapping = json.loads((OUT / "capability_mapping.json").read_text())
    matrix = json.loads(
        (
            ROOT / "docs/capability-registry/generated/management/capability_management_matrix.json"
        ).read_text()
    )
    mgmt_mapped = {r["id"] for r in matrix["capabilities"] if r["mapped"]}
    raw_mapped = {c["capability_id"] for c in mapping["capabilities"] if c["mapped"]}
    invented = sorted(raw_mapped - mgmt_mapped)
    assert not invented, f"raw scanner maps caps the authoritative matrix does not: {invented}"


def test_offline_manifest_fallback_is_fail_closed_allowlist() -> None:
    # P2 audit portability: when run against an extracted ZIP with no .git, the mapper
    # must fall back to the SIGNED release manifest (an allowlist), never scan the raw
    # filesystem. Verify the manifest parser yields real signed paths, and that with
    # neither git nor manifest the enumeration fails closed (raises), not scans.
    util = __import__("importlib.util").util
    spec = util.spec_from_file_location("capability_mapping_fallback", SCRIPT)
    assert spec and spec.loader
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest_paths = module._manifest_files()
    assert manifest_paths, "signed release manifest must enumerate paths for offline audit"
    assert "scripts/ci/capability_mapping_engine.py" in manifest_paths

    import subprocess as _sp

    orig_run, orig_manifest = module.subprocess.run, module._manifest_files
    try:
        module.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
            _sp.CalledProcessError(128, "git")
        )
        module._manifest_files = lambda: []  # simulate: no git AND no manifest
        try:
            module._tracked_files()
            raise AssertionError("expected fail-closed RuntimeError with no git and no manifest")
        except RuntimeError as e:
            assert "fail-closed" in str(e)
    finally:
        module.subprocess.run, module._manifest_files = orig_run, orig_manifest


def test_generated_and_release_artifacts_are_not_repository_evidence() -> None:
    spec = __import__("importlib.util").util.spec_from_file_location("capability_mapping", SCRIPT)
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = {path.relative_to(ROOT).as_posix() for path in module.iter_files()}
    assert not any("/generated/" in f"/{path}/" for path in paths)
    assert not any(path.startswith("release/") for path in paths)
    assert not any(".generated." in Path(path).name.lower() for path in paths)


def _iter_scanned_paths() -> set[str]:
    spec = __import__("importlib.util").util.spec_from_file_location("capability_mapping", SCRIPT)
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {path.relative_to(ROOT).as_posix() for path in module.iter_files()}


def test_meta_governance_witness_files_are_not_capability_evidence() -> None:
    """A witness must not affect what it witnesses.

    Measured on PR #850: one mutation description in the guard mutation registry naming a
    capability ID re-attributed ~40 event signals between two capabilities. The named
    witnesses (mutation/test registries, governance inventories, catalogue artifacts)
    are denied by name — never by subtree.
    """
    paths = _iter_scanned_paths()
    assert "docs/architecture/guard_mutation_registry.json" not in paths
    assert "docs/architecture/capability_core_consumption_registry.json" not in paths
    assert "docs/architecture/source_text_assertion_inventory.json" not in paths
    assert "docs/runbooks/GUARD_CATALOGUE.md" not in paths


def test_legitimate_architecture_evidence_remains_discoverable() -> None:
    """The witness fix must not undercount: a subtree ban was rejected in review.

    Hand-authored contracts, topology inventories and operational runbooks in the same
    directories are real evidence — each measured as contributing legitimate capability
    signals at the pre-slice baseline (schema contract → SOIL-001, topology → INT-002,
    run-lineage runbook → FM-004).
    """
    paths = _iter_scanned_paths()
    assert "docs/architecture/live_pg_schema_contract.json" in paths
    assert "docs/architecture/jetstream_topology_inventory.md" in paths
    assert any(path.startswith("docs/architecture/") for path in paths)
    assert any(path.startswith("docs/runbooks/") for path in paths)


def test_evidence_cap_truncation_is_declared_not_silent() -> None:
    """CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01: القصّ عند سقف المئة
    يعلن عدد محذوفه — **يمرّ بالقاعدة نفسها** (cap_evidence_dimensions) لا
    بمصنوعتها، ثم يقيس المصنوعة المشحونة طبقةً ثانية."""
    import importlib.util as ilu
    import json

    spec = ilu.spec_from_file_location(
        "capability_mapping_engine_under_test", ROOT / "scripts/ci/capability_mapping_engine.py"
    )
    assert spec is not None and spec.loader is not None
    eng = ilu.module_from_spec(spec)
    spec.loader.exec_module(eng)

    def _dedup(items, key):
        return list(items)

    rec = {k: [] for k in eng.EVIDENCE_DIMENSIONS}
    rec["tests"] = [{"value": f"tests_v9/t_{i:03}.py", "score": 1} for i in range(150)]
    rec["routes"] = [{"value": f"/api/r{i}", "score": 1} for i in range(100)]
    eng.cap_evidence_dimensions(rec, _dedup)

    assert len(rec["tests"]) == 100
    assert rec["evidence_truncated"] == {"tests": 50}, (
        "بُعدٌ قُصّ خمسين شاهداً بلا إعلانٍ باسمه وعدده — عاد الاقتطاع الصامت"
    )
    # مئةٌ بلا قصّ لا تعلن شيئاً (لا إعلان كاذب):
    assert "routes" not in rec["evidence_truncated"]

    # الطبقة الثانية: المصنوعة المشحونة تحمل الإعلان حيث السقف مبلوغ.
    mapping = json.loads(
        (ROOT / "docs/capability-registry/generated/mapping/capability_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    sat3 = next(r for r in mapping["capabilities"] if r["capability_id"] == "SAT-003")
    if len(sat3.get("tests", [])) == 100:
        assert sat3.get("evidence_truncated", {}).get("tests", 0) > 0, (
            "SAT-003.tests عند السقف بلا إعلان قصّ في المصنوعة المشحونة"
        )
