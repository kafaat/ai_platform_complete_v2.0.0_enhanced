from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_batch_runner_exists_and_is_fail_closed_on_missing_urls():
    text = (ROOT / "scripts/ci/runtime_probe_batch.py").read_text()
    assert "missing:" in text
    assert "return 1" in text
    assert "--environment-id" in text
    assert "--deployment-manifest" in text


def test_runtime_overlay_mounts_repository_and_uses_profile():
    text = (ROOT / "docker-compose.runtime-verification.yml").read_text()
    assert "runtime-verifier:" in text
    assert ".:/workspace" in text
    assert "runtime-verification" in text
