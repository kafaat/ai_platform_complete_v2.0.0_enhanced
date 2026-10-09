from pathlib import Path

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
    assert POSTGRES_16 in wx12["steps"][2]["run"]
    assert "services" not in wx12
    assert "postgis/postgis:" not in ci
    assert "postgis/postgis:" not in wx12_path.read_text(encoding="utf-8")
    assert "scripts/ci/build_postgis_test_image.sh" in ci
    assert "scripts/ci/build_postgis_test_image.sh" in wx12_path.read_text(encoding="utf-8")

    assert (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8").count(
        f"FROM {NGINX_1_27_5}"
    ) == 1
    assert (ROOT / "deploy/railway/Dockerfile.frontend").read_text(
        encoding="utf-8"
    ).count(f"FROM {NGINX_1_27_5}") == 1
    assert (ROOT / "deploy/railway/Dockerfile.migrate").read_text(
        encoding="utf-8"
    ).count(f"FROM {POSTGRES_16_ALPINE}") == 1

    postgis_builder = (ROOT / "scripts/ci/build_postgis_test_image.sh").read_text(
        encoding="utf-8"
    )
    assert "public\\.ecr\\.aws/docker/library/postgres@sha256" in postgis_builder
    assert "postgresql-$pg_major-postgis-3" in postgis_builder
    assert "postgresql-$pg_major-postgis-3-scripts" in postgis_builder
