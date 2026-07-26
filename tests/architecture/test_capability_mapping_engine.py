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


def test_generated_and_release_artifacts_are_not_repository_evidence() -> None:
    spec = __import__("importlib.util").util.spec_from_file_location("capability_mapping", SCRIPT)
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = {path.relative_to(ROOT).as_posix() for path in module.iter_files()}
    assert not any("/generated/" in f"/{path}/" for path in paths)
    assert not any(path.startswith("release/") for path in paths)
    assert not any(".generated." in Path(path).name.lower() for path in paths)
