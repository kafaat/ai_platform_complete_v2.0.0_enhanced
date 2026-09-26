"""Fresh authentication, role safety and redaction of the SSH diagnostic."""

import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "railway_platform_db_probe", ROOT / "deploy/railway/probe_platform_db.py"
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)

IDENTITY = {
    "session_user": "sahool_app",
    "current_user": "sahool_app",
    "database": "sahool",
    "rolcanlogin": True,
    "rolsuper": False,
    "rolbypassrls": False,
}


@pytest.mark.parametrize(
    "dsn", ["", "postgresql://sahool_app:${{shared.APP_DB_PASSWORD}}@db/sahool"]
)
async def test_missing_or_unresolved_url_does_not_connect(dsn):
    connect = AsyncMock()
    result = await diagnostic.probe({"DATABASE_URL": dsn}, connect)
    assert result["ok"] is False
    assert result["error"] == "missing_or_unresolved_database_url"
    connect.assert_not_called()


async def test_auth_error_is_redacted():
    class InvalidPasswordError(Exception):
        sqlstate = "28P01"

    secret = "DO_NOT_PRINT"
    connect = AsyncMock(side_effect=InvalidPasswordError(f"password={secret}"))
    result = await diagnostic.probe(
        {"DATABASE_URL": f"postgresql://app:{secret}@db/sahool"}, connect
    )
    assert result["ok"] is False
    assert result["sqlstate"] == "28P01"
    assert secret not in json.dumps(result)


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({}, True),
        ({"rolsuper": True}, False),
        ({"rolbypassrls": True}, False),
        ({"session_user": "postgres"}, False),
        ({"database": "other"}, False),
    ],
)
async def test_fresh_readonly_connection_checks_role_and_closes(override, expected):
    class Connection:
        fetchrow = AsyncMock(return_value={**IDENTITY, **override})
        close = AsyncMock()

        @asynccontextmanager
        async def transaction(self, *, readonly):
            assert readonly is True
            yield

    connection = Connection()
    connect = AsyncMock(return_value=connection)
    result = await diagnostic.probe({"DATABASE_URL": "postgresql://unused/sahool"}, connect)
    connect.assert_awaited_once()
    assert result["ok"] is expected
    connection.close.assert_awaited_once()
    assert "FROM pg_roles" in connection.fetchrow.call_args.args[0]
