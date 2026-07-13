from unittest.mock import AsyncMock, MagicMock

import pytest
import soil_store


class _Tx:
    start = AsyncMock()
    commit = AsyncMock()
    rollback = AsyncMock()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_cutover_readiness_ready():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_Tx())
    conn.fetchrow.side_effect = [
        {"observations_ready": True, "profiles_ready": True},
        {"fields_total": 3, "profiles_ready": 3, "invalid_profiles": 0},
    ]
    result = await soil_store.get_cutover_readiness(
        _Pool(conn), tenant_id="00000000-0000-0000-0000-000000000001"
    )
    assert result["can_enable_strict_soil"] is True
    assert result["coverage_pct"] == 100.0


@pytest.mark.asyncio
async def test_cutover_readiness_fails_closed_on_missing_profile():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_Tx())
    conn.fetchrow.side_effect = [
        {"observations_ready": True, "profiles_ready": True},
        {"fields_total": 4, "profiles_ready": 3, "invalid_profiles": 0},
    ]
    result = await soil_store.get_cutover_readiness(
        _Pool(conn), tenant_id="00000000-0000-0000-0000-000000000001"
    )
    assert result["can_enable_strict_soil"] is False
    assert result["profiles_missing"] == 1
