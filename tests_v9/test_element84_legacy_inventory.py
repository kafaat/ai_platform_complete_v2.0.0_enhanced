"""Read-only inventory safety; these tests do not constitute a production census."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.diagnostics.element84_legacy_inventory import (
    QUERIES,
    TABLES,
    InventoryRefused,
    classify_row,
    collect_inventory,
    validate_policies,
)

pytestmark = pytest.mark.unit
TENANT = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"


@asynccontextmanager
async def transaction(*, readonly, isolation):
    assert readonly is True
    assert isolation == "repeatable_read"
    yield


def connection(rows=None, privileged=False):
    return SimpleNamespace(
        transaction=transaction,
        execute=AsyncMock(),
        fetchval=AsyncMock(
            side_effect=[
                privileged,
                [
                    {
                        "table": table,
                        "enabled": True,
                        "forced": True,
                        "qual": "tenant_id::text = current_setting('app.current_tenant'::text, true)",
                    }
                    for table in TABLES
                ],
            ]
        ),
        fetch=AsyncMock(return_value=rows or []),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", ["", " ", "*", "all", "not-a-uuid", None])
async def test_missing_or_invalid_tenant_refused_before_db(tenant):
    conn = connection()
    with pytest.raises(InventoryRefused, match="tenant"):
        await collect_inventory(conn, tenant)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_privileged_role_refused_before_any_product_read():
    conn = connection(privileged=True)
    with pytest.raises(InventoryRefused, match="privileged"):
        await collect_inventory(conn, TENANT)
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_uses_explicit_tenant_and_bounded_queries():
    conn = connection()
    report = await collect_inventory(conn, TENANT, limit=10)
    assert report["snapshot_complete"] is True
    assert report["production_acceptance"] is False
    assert report["tenant_id"] == TENANT
    conn.execute.assert_any_await("SELECT set_config('app.current_tenant', $1, true)", TENANT)
    for call in conn.fetch.await_args_list:
        assert call.args[1:] == (TENANT, 11)
        assert "tenant_id = $1::uuid" in call.args[0]
        assert "LIMIT $2" in call.args[0]
    assert len(conn.fetch.await_args_list) == len(QUERIES)


@pytest.mark.asyncio
async def test_cross_tenant_result_refuses_entire_report():
    conn = connection([{"tenant_id": OTHER}])
    with pytest.raises(InventoryRefused, match="cross-tenant"):
        await collect_inventory(conn, TENANT)


@pytest.mark.asyncio
async def test_truncation_is_not_zero_or_complete_census():
    conn = connection([{"tenant_id": TENANT}, {"tenant_id": TENANT}])
    report = await collect_inventory(conn, TENANT, limit=1)
    assert report["snapshot_complete"] is False
    assert all(section["truncated"] for section in report["sources"].values())
    assert all(section["row_count_lower_bound"] == 2 for section in report["sources"].values())


@pytest.mark.parametrize("provider", [None, "", "unknown"])
def test_unknown_provider_never_classified_as_unaffected(provider):
    row = classify_row({"provider": provider, "error_evidence": None})
    assert row["provider_attribution"] == "unknown"
    assert row["element84_candidate"] is True
    assert row["http_422_evidence"] == "unavailable"


def test_only_literal_http_evidence_is_attributed_to_422():
    row = classify_row({"provider": "element84", "error_evidence": "HTTP 422 validation failed"})
    assert row["http_422_evidence"] == "explicit_http_status"
    assert "error_evidence" not in row
    assert (
        classify_row({"error_evidence": "job 42201 failed"})["http_422_evidence"] == "unavailable"
    )
    assert classify_row({"error_evidence": "422"})["http_422_evidence"] == "unavailable"


def test_non_element84_provider_preserved_without_damage_claim():
    row = classify_row({"provider": "cdse", "processing_version": None})
    assert row["element84_candidate"] is False
    assert row["processing_version"] is None
    assert "damaged" not in row


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 100001, True])
async def test_invalid_limit_refused(limit):
    conn = connection()
    with pytest.raises(InventoryRefused, match="limit"):
        await collect_inventory(conn, TENANT, limit=limit)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_schema_or_permission_failure_is_not_an_empty_inventory():
    conn = connection()
    conn.fetch.side_effect = RuntimeError("missing relation or permission")
    with pytest.raises(RuntimeError, match="missing relation"):
        await collect_inventory(conn, TENANT)


@pytest.mark.asyncio
async def test_cli_refuses_invalid_scope_before_connecting(monkeypatch, tmp_path):
    import asyncpg

    from scripts.diagnostics.element84_legacy_inventory import _run

    connect = AsyncMock()
    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(InventoryRefused, match="tenant"):
        await _run(SimpleNamespace(tenant_id="all", limit=10, output=tmp_path / "out.json"))
    connect.assert_not_awaited()


@pytest.mark.parametrize(
    "context", ["app.tenant_id", "app.current_tenant_id", "unrecognized_context"]
)
def test_unsupported_rls_context_refused(context):
    policies = [
        {
            "table": table,
            "enabled": True,
            "forced": True,
            "qual": f"tenant_id::text = current_setting('{context}'::text, true)",
        }
        for table in TABLES
    ]
    with pytest.raises(InventoryRefused, match="unsupported tenant"):
        validate_policies(policies)


def test_missing_rls_metadata_refused():
    with pytest.raises(InventoryRefused, match="missing inventory"):
        validate_policies([])
