from pathlib import Path


def uncommented_lines(path: str) -> list[str]:
    return [line for line in Path(path).read_text(encoding='utf-8').splitlines() if not line.lstrip().startswith('#')]


def test_v9_platform_database_url_not_blank_default():
    text = '\n'.join(uncommented_lines('docker-compose.v9.yml'))
    assert 'DATABASE_URL: ${DATABASE_URL:-}' not in text
    assert 'sahool_app:${APP_DB_PASSWORD' in text
    assert 'JOBS_DATABASE_URL: ${JOBS_DATABASE_URL:-}' not in text
    assert 'sahool_jobs:${JOBS_DB_PASSWORD' in text


def test_fixed_platform_database_url_has_local_default():
    text = '\n'.join(uncommented_lines('docker-compose.fixed.yml'))
    assert 'DATABASE_URL: ${DATABASE_URL}' not in text
    assert 'sahool_app:${APP_DB_PASSWORD' in text  # تصلّب RLS: دور مقيّد لا sahool_user (كان بائتاً)
