from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unified_gate_is_honest_and_wired_to_critical_checks():
    src = (ROOT / "scripts/ci/unified_production_readiness_gate.py").read_text()
    for required in (
        "production_honesty_guard.py",
        "minio_s3_contract_gate.py",
        "container_image_pin_guard.py",
        "production_certification_blockers_status.py",
    ):
        assert required in src
    assert '"release_candidate"' in src
    assert "--require-certified" in src


def test_production_workflow_archives_unified_evidence():
    workflow = (ROOT / ".github/workflows/sahool-production-gates.yml").read_text()
    assert "unified_production_readiness_gate.py" in workflow
    assert "unified-readiness-evidence" in workflow
