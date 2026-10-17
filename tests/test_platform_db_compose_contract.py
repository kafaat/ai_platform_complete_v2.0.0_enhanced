from pathlib import Path


def uncommented_lines(path: str) -> list[str]:
    return [
        line
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]


def test_v9_platform_database_url_not_blank_default():
    text = "\n".join(uncommented_lines("docker-compose.v9.yml"))
    assert "DATABASE_URL: ${DATABASE_URL:-}" not in text
    assert "sahool_app:${APP_DB_PASSWORD" in text
    assert "JOBS_DATABASE_URL: ${JOBS_DATABASE_URL:-}" not in text
    assert "sahool_jobs:${JOBS_DB_PASSWORD" in text


def test_platform_database_url_has_local_default():
    """كان يُقاس على docker-compose.fixed.yml — نُقل إلى docs/history/compose/ بقرار مالك
    (COMPOSE-ALTERNATES-UNGUARDED-AND-NAME-INCOMPATIBLE-01، 2026-10-17). الخاصّيّةُ نفسُها
    على خدمة المنصّة في v9: افتراضٌ محلّيّ بدورٍ مقيّد، لا `${DATABASE_URL}` عارٍ."""
    import yaml

    compose = yaml.safe_load(Path("docker-compose.v9.yml").read_text(encoding="utf-8"))
    url = str(compose["services"]["sahool-platform"]["environment"]["DATABASE_URL"])
    assert url != "${DATABASE_URL}", "DATABASE_URL عارٍ بلا افتراضٍ محلّيّ في خدمة المنصّة"
    assert url.startswith("${DATABASE_URL:-postgresql://sahool_app:${APP_DB_PASSWORD"), url
