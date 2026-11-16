"""Helm render acceptance: lint and template for both overlays, with a pinned binary in CI.

Until this file, the chart's render tests ran on whatever helm the GitHub runner image ships
(unpinned, unverified), only the production overlay was ever rendered, nothing ran
`helm lint`, and a runner without helm would have skipped every render test green.

The CI helm-readiness job now installs helm v3.16.4 from get.helm.sh, checks its sha256 before
unpacking, and runs every ``helm_render`` test with HELM_RENDER_REQUIRED=1, where a missing
binary is a failure rather than a skip. The last test proves that switch locally, without helm.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
OVERLAYS = ("values-staging.yaml", "values-production.yaml")

# Read before the binary lookup: the CI helm-render step sets HELM_RENDER_REQUIRED=1, so a
# missing helm fails these tests there instead of skipping them green.
HELM_RENDER_REQUIRED = os.environ.get("HELM_RENDER_REQUIRED") == "1"


def needs_helm(test):
    skip = pytest.mark.skipif(
        not HELM_RENDER_REQUIRED and shutil.which("helm") is None,
        reason="helm binary not installed",
    )
    return pytest.mark.helm_render(skip(test))


def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _values(overlay: str) -> dict:
    base = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    extra = yaml.safe_load((CHART / overlay).read_text(encoding="utf-8")) or {}
    return _deep_merge(base, extra)


def _helm(command: str, overlay: str) -> subprocess.CompletedProcess:
    args = ["helm", command]
    if command == "template":
        args.append("sahool")
    args += [str(CHART), "-f", str(CHART / "values.yaml"), "-f", str(CHART / overlay)]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)


def _render(overlay: str) -> list[dict]:
    result = _helm("template", overlay)
    assert result.returncode == 0, f"helm template with {overlay} failed:\n{result.stderr}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _by_kind(docs: list[dict], kind: str) -> dict[str, dict]:
    return {d["metadata"]["name"]: d for d in docs if d.get("kind") == kind}


@needs_helm
@pytest.mark.parametrize("overlay", OVERLAYS)
def test_helm_lint_passes_for_the_overlay(overlay: str) -> None:
    result = _helm("lint", overlay)
    assert result.returncode == 0, f"helm lint with {overlay}:\n{result.stdout}\n{result.stderr}"
    assert "0 chart(s) failed" in result.stdout, result.stdout


@needs_helm
@pytest.mark.parametrize("overlay", OVERLAYS)
def test_every_enabled_workload_renders_its_deployment_and_service(overlay: str) -> None:
    values = _values(overlay)
    docs = _render(overlay)
    deployments = _by_kind(docs, "Deployment")
    services = _by_kind(docs, "Service")
    enabled = {n: s for n, s in values["workloads"].items() if s.get("enabled")}
    assert enabled, f"{overlay}: no enabled workload"
    assert set(enabled) <= set(deployments), sorted(set(enabled) - set(deployments))
    assert set(deployments) - set(enabled) <= {"sahool-gateway"}, sorted(deployments)
    for name, spec in enabled.items():
        deployment = deployments[name]["spec"]
        assert deployment["replicas"] == spec["replicas"], (overlay, name)
        container = deployment["template"]["spec"]["containers"][0]
        assert container["image"] == spec["image"], (overlay, name, container["image"])
        ports = services[name]["spec"]["ports"]
        assert [p["port"] for p in ports] == [spec["port"]], (overlay, name, ports)


@needs_helm
@pytest.mark.parametrize("overlay", OVERLAYS)
def test_the_render_carries_default_deny_and_the_required_secret_names(overlay: str) -> None:
    values = _values(overlay)
    docs = _render(overlay)
    if values.get("networkPolicy", {}).get("enabled", True):
        assert "sahool-default-deny" in _by_kind(docs, "NetworkPolicy"), overlay
    listing = _by_kind(docs, "Secret")["sahool-runtime-secrets-required"]["stringData"]
    names = listing["required-secrets"]
    for ref, name in values["global"]["secretRefs"].items():
        assert f"{name} (key: value) <- global.secretRefs.{ref}" in names, (overlay, ref)


def test_the_switch_turns_a_missing_helm_into_a_failure(tmp_path: Path) -> None:
    """With HELM_RENDER_REQUIRED=1 and no helm on PATH, a render test fails; without it, skips."""
    target = f"{Path(__file__).relative_to(ROOT)}::test_helm_lint_passes_for_the_overlay"
    base_env = {
        k: v for k, v in os.environ.items() if k not in {"HELM_RENDER_REQUIRED", "PYTEST_ADDOPTS"}
    }
    base_env.update(PATH=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
    command += ["-o", "addopts=", target]

    required = subprocess.run(
        command,
        cwd=ROOT,
        env={**base_env, "HELM_RENDER_REQUIRED": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert required.returncode != 0, required.stdout
    assert "2 failed" in required.stdout and "skipped" not in required.stdout, required.stdout

    relaxed = subprocess.run(command, cwd=ROOT, env=base_env, capture_output=True, text=True)
    assert relaxed.returncode == 0, relaxed.stdout
    assert "2 skipped" in relaxed.stdout, relaxed.stdout
