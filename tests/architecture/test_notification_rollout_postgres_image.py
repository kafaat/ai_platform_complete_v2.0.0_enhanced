from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/notification-rollout.yml"
EXPECTED_IMAGE = (
    "public.ecr.aws/docker/library/postgres@"
    "sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
)


def test_notification_rollout_uses_pinned_docker_official_postgres_image():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    postgres = workflow["jobs"]["notification-rollout"]["services"]["postgres"]

    assert postgres["image"] == EXPECTED_IMAGE
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
