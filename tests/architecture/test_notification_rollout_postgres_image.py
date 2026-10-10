import copy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/notification-rollout.yml"
POSTGRES_16_ALPINE = (
    "public.ecr.aws/docker/library/postgres@"
    "sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
)
POSTGRES_15 = (
    "public.ecr.aws/docker/library/postgres@"
    "sha256:d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae"
)
POSTGRES_16 = (
    "public.ecr.aws/docker/library/postgres@"
    "sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
)
REDIS_7_ALPINE = (
    "public.ecr.aws/docker/library/redis@"
    "sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
)
NGINX_1_27_5 = (
    "public.ecr.aws/docker/library/nginx@"
    "sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
)
POSTGIS_BUILDER = "scripts/ci/build_postgis_test_image.sh"


def _assert_wx12_postgres_provisioning_contract(steps):
    provision_steps = [
        step["run"]
        for step in steps
        if isinstance(step, dict)
        and isinstance(step.get("run"), str)
        and POSTGIS_BUILDER in step["run"]
    ]
    assert len(provision_steps) == 1, "expected one PostgreSQL/PostGIS provisioning step"
    assert POSTGRES_16 in provision_steps[0], "provision step must use the pinned PostgreSQL digest"
    assert "postgis" in provision_steps[0].lower()


def test_notification_rollout_uses_pinned_docker_official_postgres_image():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    postgres = workflow["jobs"]["notification-rollout"]["services"]["postgres"]

    assert postgres["image"] == POSTGRES_16_ALPINE
    assert postgres["env"] == {
        "POSTGRES_DB": "notification_rollout_test",
        "POSTGRES_USER": "notification_test",
        "POSTGRES_PASSWORD": "disposable_test_password",
    }
    assert postgres["ports"] == ["5438:5432"]
    assert (
        '--health-cmd "pg_isready -U notification_test -d notification_rollout_test"'
        in (postgres["options"])
    )


def test_ci_database_and_frontend_images_are_pinned_outside_docker_hub():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    wx12_path = ROOT / ".github/workflows/wx12-runtime-certification.yml"
    wx12 = yaml.safe_load(wx12_path.read_text(encoding="utf-8"))["jobs"]["postgres"]
    assert POSTGRES_15 in ci
    assert POSTGRES_16 in ci
    assert REDIS_7_ALPINE in ci
    _assert_wx12_postgres_provisioning_contract(wx12["steps"])
    assert "services" not in wx12
    assert "postgis/postgis:" not in ci
    assert "postgis/postgis:" not in wx12_path.read_text(encoding="utf-8")
    assert "scripts/ci/build_postgis_test_image.sh" in ci
    assert "scripts/ci/build_postgis_test_image.sh" in wx12_path.read_text(encoding="utf-8")

    assert (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8").count(
        f"FROM {NGINX_1_27_5}"
    ) == 1
    assert (ROOT / "deploy/railway/Dockerfile.frontend").read_text(encoding="utf-8").count(
        f"FROM {NGINX_1_27_5}"
    ) == 1
    assert (ROOT / "deploy/railway/Dockerfile.migrate").read_text(encoding="utf-8").count(
        f"FROM {POSTGRES_16_ALPINE}"
    ) == 1

    postgis_builder = (ROOT / "scripts/ci/build_postgis_test_image.sh").read_text(encoding="utf-8")
    assert "public\\.ecr\\.aws/docker/library/postgres@sha256" in postgis_builder
    assert "postgresql-$pg_major-postgis-3" in postgis_builder
    assert "postgresql-$pg_major-postgis-3-scripts" in postgis_builder


def test_wx12_provisioning_contract_ignores_unrelated_steps_and_order():
    wx12 = yaml.safe_load(
        (ROOT / ".github/workflows/wx12-runtime-certification.yml").read_text(encoding="utf-8")
    )["jobs"]["postgres"]
    steps = copy.deepcopy(wx12["steps"])
    steps.insert(0, {"name": "unrelated setup", "run": "echo setup"})
    steps.extend(
        [
            {"name": "unrelated check A", "run": "echo check-a"},
            {"name": "unrelated check B", "run": "echo check-b"},
        ]
    )
    _assert_wx12_postgres_provisioning_contract(steps)

    steps[-2], steps[-1] = steps[-1], steps[-2]
    _assert_wx12_postgres_provisioning_contract(steps)


def test_wx12_provisioning_contract_rejects_missing_or_duplicate_step():
    wx12 = yaml.safe_load(
        (ROOT / ".github/workflows/wx12-runtime-certification.yml").read_text(encoding="utf-8")
    )["jobs"]["postgres"]
    steps = copy.deepcopy(wx12["steps"])
    steps = [
        step
        for step in steps
        if not isinstance(step, dict) or POSTGIS_BUILDER not in step.get("run", "")
    ]
    with pytest.raises(AssertionError, match="expected one"):
        _assert_wx12_postgres_provisioning_contract(steps)

    steps = copy.deepcopy(wx12["steps"])
    provision_step = next(step for step in steps if POSTGIS_BUILDER in step.get("run", ""))
    steps.append(copy.deepcopy(provision_step))
    with pytest.raises(AssertionError, match="expected one"):
        _assert_wx12_postgres_provisioning_contract(steps)


def test_wx12_provisioning_contract_rejects_changed_digest_or_unpinned_image():
    wx12 = yaml.safe_load(
        (ROOT / ".github/workflows/wx12-runtime-certification.yml").read_text(encoding="utf-8")
    )["jobs"]["postgres"]
    steps = copy.deepcopy(wx12["steps"])
    provision_step = next(step for step in steps if POSTGIS_BUILDER in step.get("run", ""))
    provision_step["run"] = provision_step["run"].replace(
        POSTGRES_16, "public.ecr.aws/docker/library/postgres@sha256:" + "0" * 64
    )
    with pytest.raises(AssertionError, match="pinned PostgreSQL digest"):
        _assert_wx12_postgres_provisioning_contract(steps)

    steps = copy.deepcopy(wx12["steps"])
    provision_step = next(step for step in steps if POSTGIS_BUILDER in step.get("run", ""))
    provision_step["run"] = provision_step["run"].replace(POSTGRES_16, "postgres:16")
    with pytest.raises(AssertionError, match="pinned PostgreSQL digest"):
        _assert_wx12_postgres_provisioning_contract(steps)
