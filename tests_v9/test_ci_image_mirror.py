"""Executable, fail-closed CI mirror regression witnesses.

The mirror is only trusted by the original OCI index SHA, with no tag lookup
or new digest substituted under the historical PostgreSQL/Redis contracts.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/pull_verified_ci_image.sh"
WORKFLOW = ROOT / ".github/workflows/ci-immutable-image-mirror.yml"
PG15 = (
    "public.ecr.aws/docker/library/postgres@sha256:"
    "d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae"
)
ID = "sha256:" + "f" * 64


def run_resolver(
    tmp_path: Path, *, mirror_ok=False, ecr_ok=False, ecr_error="", config_id=ID, source=PG15
):
    docker = tmp_path / "docker"
    log = tmp_path / "calls.log"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$FAKE_DOCKER_LOG"\n'
        'if [[ "$1" == login ]]; then cat >/dev/null; exit 0; fi\n'
        'if [[ "$1" == pull ]]; then\n'
        '  if [[ "$2" == ghcr.io/* ]]; then '
        '[[ "$MIRROR_OK" == yes ]] && exit 0; echo "mirror missing" >&2; exit 1; fi\n'
        '  if [[ "$ECR_OK" == yes ]]; then exit 0; fi\n'
        '  echo "$ECR_ERROR" >&2; exit 1\n'
        "fi\n"
        'if [[ "$1" == image && "$2" == inspect ]]; then '
        'echo "$CONFIG_ID"; exit 0; fi\n'
        "exit 42\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    receipt = tmp_path / "image-id"
    cause = tmp_path / "harness-cause"
    env = dict(
        os.environ,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        GHCR_TOKEN="test-token-do-not-log",
        GITHUB_ACTOR="test-ci",
        MIRROR_OK="yes" if mirror_ok else "no",
        ECR_OK="yes" if ecr_ok else "no",
        ECR_ERROR=ecr_error,
        CONFIG_ID=config_id,
        FAKE_DOCKER_LOG=str(log),
        CI_MIRROR_PULL_TIMEOUT="4",
        PULL_TIMEOUT="4",
        HARNESS_PRIMARY_CAUSE_FILE=str(cause),
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), source, str(receipt)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls, receipt, cause


def test_ghcr_exact_manifest_wins_without_ecr_pull(tmp_path):
    result, calls, receipt, cause = run_resolver(tmp_path, mirror_ok=True)
    assert result.returncode == 0, result.stderr
    assert receipt.read_text().strip() == ID
    assert any("pull ghcr.io/kafaat/sahool-ci-postgres@sha256:" in s for s in calls)
    assert not any(s.startswith("pull public.ecr") for s in calls)
    assert "GHCR_VERIFIED_INDEX" in result.stderr
    assert "test-token-do-not-log" not in result.stderr
    assert not cause.exists()


def test_absent_mirror_falls_back_to_exact_ecr_image(tmp_path):
    result, calls, receipt, cause = run_resolver(tmp_path, ecr_ok=True)
    assert result.returncode == 0, result.stderr
    pulls = [s for s in calls if s.startswith("pull ")]
    assert len(pulls) == 2 and pulls[1] == f"pull {PG15}"
    assert receipt.read_text().strip() == ID
    assert "ECR_PINNED" in result.stderr
    assert not cause.exists()


def test_both_registries_unavailable_never_emit_a_success_receipt(tmp_path):
    result, calls, receipt, cause = run_resolver(
        tmp_path, ecr_error="toomanyrequests: Data limit exceeded"
    )
    assert result.returncode != 0
    assert len([x for x in calls if x.startswith("pull ")]) == 2
    assert not receipt.exists()
    assert cause.read_text().strip() == "DOCKER_IMAGE_PULL_FAILED"
    assert "failure_class=RATE_LIMIT" in result.stderr
    assert "database_state=NOT_STARTED" in result.stderr


def test_bad_local_config_digest_is_not_accepted(tmp_path):
    result, _, receipt, _ = run_resolver(tmp_path, mirror_ok=True, config_id="sha256:not-a-digest")
    assert result.returncode != 0
    assert not receipt.exists()
    assert "Cannot prove local Docker image config digest" in result.stderr


def test_unknown_immutable_source_fails_before_network(tmp_path):
    bad_image = "public.ecr.aws/docker/library/postgres@sha256:" + "0" * 64
    result, calls, receipt, _ = run_resolver(tmp_path, source=bad_image)
    assert result.returncode == 2
    assert not calls and not receipt.exists()
    assert "allowlist" in result.stderr


def test_bootstrap_requires_preserved_manifest_hash_and_package_write():
    content = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(content)
    job = workflow["jobs"]["mirror"]
    assert job["permissions"]["packages"] == "write"
    assert job["strategy"]["max-parallel"] == 1
    pins = {item["digest"] for item in job["strategy"]["matrix"]["include"]}
    for digest in (
        "d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae",
        "ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d",
        "721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea",
        "858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499",
        "65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10",
    ):
        assert digest in pins
    run = job["steps"][-1]["run"]
    assert "skopeo copy --all --preserve-digests" in run
    assert "sha256sum --check" in run
    assert "docker://$target" in run
    assert "docker.io/library/" in run


def test_railway_ci_build_rewrites_only_reviewed_nginx_and_postgres_pins():
    """The build harness must preserve both production digest locks."""
    path = ROOT / ".github/workflows/railway-dockerfile-pr-build.yml"
    content = path.read_text(encoding="utf-8")
    build = yaml.safe_load(content)["jobs"]["build"]
    assert build["permissions"]["packages"] == "read"
    run = next(s["run"] for s in build["steps"] if s.get("name", "").startswith("Build "))
    pinned = {
        "deploy/railway/Dockerfile.frontend": (
            "nginx", "65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
        ),
        "deploy/railway/Dockerfile.migrate": (
            "postgres", "721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
        ),
    }
    for dockerfile, (kind, digest) in pinned.items():
        original = (ROOT / dockerfile).read_text(encoding="utf-8")
        upstream = f"public.ecr.aws/docker/library/{kind}@sha256:{digest}"
        assert original.count(f"FROM {upstream}") == 1
        assert digest in run
    assert 'pinned_source="public.ecr.aws/docker/library/${pinned_kind}@sha256:${pinned_digest}"' in run
    assert 'verified_source="ghcr.io/kafaat/sahool-ci-${pinned_kind}@sha256:${pinned_digest}"' in run
    assert '"$SERVICE" == "sahool-frontend" || "$SERVICE" == "sahool-migrate-main"' in run
    assert "bash scripts/ci/pull_verified_ci_image.sh" in run
    assert '"$RUNNER_TEMP/railway-from-ref"' in run
    assert "source.count(expected) != 1" in run
    assert "Unverified Railway build image" in run
    assert '-f "$dockerfile_for_build"' in run
    assert "continue-on-error" not in content


def test_bootstrap_apt_is_bounded_and_regeneration_tracks_mirror_workflows():
    bootstrap = WORKFLOW.read_text(encoding="utf-8")
    assert "sudo timeout --signal=TERM --kill-after=15s 180s apt-get update" in bootstrap
    assert "sudo timeout --signal=TERM --kill-after=15s 240s apt-get install" in bootstrap
    content = (ROOT / ".github/workflows/ci-immutable-mirror-regenerate.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    paths = parsed.get("on", parsed.get(True))["push"]["paths"]
    assert ".github/workflows/ci-immutable-image-mirror.yml" in paths
    assert ".github/workflows/railway-dockerfile-pr-build.yml" in paths
    assert "python scripts/ci/verify_all_generated.py --check" in content
    assert "python scripts/release/validate_release_package.py --root ." in content
