from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_live_acceptance_gate_is_fail_closed_and_never_certifies_production():
    text = (ROOT / "scripts/ci/path3_live_acceptance_gate.py").read_text()
    assert "PATH3_ATTESTATION_KEY is required" in text
    assert "selected_evidence_set_mismatch" in text
    assert "production_certification_must_remain_false" in text
    assert "--require-all" in text


def test_runtime_workflow_uploads_attestations_and_uses_secret():
    text = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert "PATH3_ATTESTATION_KEY: ${{ secrets.PATH3_ATTESTATION_KEY }}" in text
    assert "path3-attested-evidence-${{ github.sha }}" in text
    assert "Attest evidence bundle in trusted signer boundary" in text


def test_live_acceptance_enforces_freshness_policy():
    text = (ROOT / "scripts/ci/path3_live_acceptance_gate.py").read_text()
    assert "path3_attestation_policy.py" in text
    assert "--max-age-seconds" in text
