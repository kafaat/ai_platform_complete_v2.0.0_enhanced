"""The field-season state reads its platform sources from a migrated Postgres (live PG).

An archived season is read by its own dates: the 7/14-day water deficit window ends at the
season end, not today, and a closed season reports no open operations. After the decision
cutover, outcomes come only from decision-service, and only when its reply is authoritative
and scoped to this tenant, field and season; otherwise the reconciliation is unavailable,
never a platform fallback. Before cutover, an optional source that fails (here the water
ledger, unreadable for the runtime role) rolls back its own savepoint, so the outcome reads
that follow in the same transaction still succeed. Before cutover the platform does not read
decision_record (S5-EXEC-01 freezes that surface), and outcome_record has no season of its
own: decision outcomes are reported unbound (counted, never reconciled into the season), and
only recommendation_outcomes, which carry season_id, feed the platform summary.

These were asserted against connection doubles (``SimpleNamespace(fetchrow, transaction)``
and a patched ``tenant_connection``), which cannot show what a failed statement does to the
enclosing transaction. Here the router runs against the real schema through a pool that
runs as a NOBYPASSRLS role. Only the HTTP owner (decision-service) and the raster scene
lookup are replaced.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
START = date(2024, 11, 1)
END = date(2025, 3, 20)
TABLES = ("seasons", "water_ledger", "decision_record", "outcome_record", "recommendation_outcomes")


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api import decision_service_client, decision_sor_mode
    from api.routers import seasons

    return main, seasons, decision_service_client, decision_sor_mode


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{uuid.uuid4().hex[:8]}", tenant_id=tenant, role=UserRole.OWNER, name_ar="مالك"
    )


class Live:
    """Owner connection for setup + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant = str(uuid.uuid4())
        tag = uuid.uuid4().hex[:10]
        self.field_id = f"ss-field-{tag}"
        self.season_id = f"ss-season-{tag}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"ss_rls_{uuid.uuid4().hex[:10]}"
            await self.owner.execute(
                f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
                f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
            )
        role = self.role

        async def setup(conn):
            if role:
                await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
        o = self.owner
        await o.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, 'Season field', $2::uuid)",
            self.field_id,
            self.tenant,
        )
        await o.execute(
            """INSERT INTO seasons (season_id, tenant_id, field_id, crops, cultivar, sowing_date,
                                    season_end, status)
               VALUES ($1, $2::uuid, $3, $4::jsonb, 'الحبيب', $5, $6, 'closed')""",
            self.season_id,
            self.tenant,
            self.field_id,
            json.dumps(["wheat"]),
            START,
            END,
        )
        # Days 7..20 March fall in the 14-day window ending at the season end; 14..20 in the
        # 7-day one. Days 6 and 21 lie outside both and must not be summed.
        for day, deficit in ((6, 100.0), (7, 1.0), (13, 2.0), (14, 3.0), (20, 4.0), (21, 100.0)):
            await o.execute(
                "INSERT INTO water_ledger (tenant_id, field_id, ledger_date, deficit_mm)"
                " VALUES ($1::uuid, $2, $3, $4)",
                self.tenant,
                self.field_id,
                date(2025, 3, day),
                deficit,
            )
        return self

    async def platform_outcomes(self):
        """A failed decision outcome of this season (bound only through its decision), and an
        accepted, not yet matured recommendation of this season."""
        o = self.owner
        decision_id = f"d-{uuid.uuid4().hex[:10]}"
        await o.execute(
            """INSERT INTO decision_record (decision_id, tenant_id, field_id, decision_type,
                                            decision_value)
               VALUES ($1, $2::uuid, $3, 'irrigation', $4::jsonb)""",
            decision_id,
            self.tenant,
            self.field_id,
            json.dumps({"season_id": self.season_id}),
        )
        await o.execute(
            """INSERT INTO outcome_record (outcome_id, tenant_id, decision_id, field_id, region,
                                           planned, actual, metrics, success)
               VALUES ($1, $2::uuid, $3, $4, 'jawf', '{}', '{}', '{}', false)""",
            f"o-{uuid.uuid4().hex[:10]}",
            self.tenant,
            decision_id,
            self.field_id,
        )
        await o.execute(
            """INSERT INTO recommendation_outcomes (tenant_id, field_id, farm_id, season_id, crop,
                   recommendation_id, predicted_yield_t_ha, actual_yield_t_ha, accepted,
                   matured_within_lag, issued_at)
               VALUES ($1::uuid, $2, 'farm', $3, 'wheat', 'r', 2, 3, true, false, now())""",
            self.tenant,
            self.field_id,
            self.season_id,
        )

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            for table in ("recommendation_outcomes", "outcome_record", "decision_record"):
                await o.execute(f"DELETE FROM {table} WHERE tenant_id = $1::uuid", self.tenant)
            await o.execute("DELETE FROM water_ledger WHERE field_id = $1", self.field_id)
            await o.execute("DELETE FROM seasons WHERE field_id = $1", self.field_id)
            await o.execute("DELETE FROM fields WHERE field_id = $1", self.field_id)
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()


def _run(monkeypatch, *, platform_writes_required, case):
    main, seasons, client, sor_mode = _platform()
    monkeypatch.setattr(seasons, "_season_state_scene", AsyncMock(return_value={}))
    monkeypatch.setattr(
        sor_mode,
        "get_platform_decision_sor_mode",
        lambda: SimpleNamespace(platform_writes_required=platform_writes_required),
    )

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, seasons, client)

    asyncio.run(body())


@pytest.mark.parametrize(
    "variant", ["confirmed", "empty", "unavailable", "other_season", "other_tenant", "mirror"]
)
def test_archived_season_reads_its_own_window_and_uses_the_owner_after_cutover(
    monkeypatch, variant
):
    from fastapi import HTTPException

    async def case(live, seasons, client):
        payload = {
            "tenant_id": live.tenant,
            "field_id": live.field_id,
            "season_id": live.season_id,
            "authoritative": True,
            "outcome_records": [],
            "recommendation_outcomes": [],
        }
        if variant == "confirmed":
            payload["outcome_records"] = [
                {
                    "outcome_id": "o",
                    "tenant_id": live.tenant,
                    "field_id": live.field_id,
                    "success": False,
                }
            ]
        if variant == "other_season":
            payload["season_id"] = "another-season"
        if variant == "other_tenant":
            payload["outcome_records"] = [
                {"tenant_id": str(uuid.uuid4()), "field_id": live.field_id, "success": True}
            ]
        if variant == "mirror":
            payload["authoritative"] = False
        caller = AsyncMock(
            side_effect=HTTPException(503) if variant == "unavailable" else None,
            return_value=payload,
        )
        monkeypatch.setattr(client, "decision_get_json", caller)
        result = await seasons.field_season_state_endpoint(
            live.field_id, live.season_id, _user(live.tenant)
        )
        caller.assert_awaited_once_with(
            "/v1/outcomes/reconciled",
            tenant_id=live.tenant,
            params={
                "field_id": live.field_id,
                "season_id": live.season_id,
                "season_inputs": "true",
            },
        )
        assert result["as_of"] == END.isoformat()
        assert result["days_after_sowing"] == (END - START).days
        assert result["open_operations"] is None
        assert (result["water_deficit_7d_mm"], result["water_deficit_14d_mm"]) == (7.0, 10.0)
        summary = result["outcome_reconciliation"]
        assert summary["source"] == "decision-service"
        assert summary["available"] == (variant in ("confirmed", "empty"))
        assert summary["complete"] == (variant in ("confirmed", "empty"))
        assert summary["missing_sources"] == (
            []
            if variant in ("confirmed", "empty")
            else ["outcome_record", "recommendation_outcomes"]
        )
        assert summary["unbound_outcome_records"] is None
        assert summary["total"] == {"confirmed": 1, "empty": 0}.get(variant)
        assert summary["success_rate"] == (0.0 if variant == "confirmed" else None)

    _run(monkeypatch, platform_writes_required=False, case=case)


def test_failed_optional_water_read_rolls_back_its_savepoint_and_keeps_platform_outcomes(
    monkeypatch,
):
    async def case(live, seasons, _client):
        if not live.role:
            pytest.skip("declared skip (not a pass): the DSN role cannot create a runtime role")
        await live.platform_outcomes()
        # The runtime role cannot read the water ledger: that statement fails inside the
        # tenant transaction. Without its savepoint the outcome reads after it would fail too.
        await live.owner.execute(f'REVOKE SELECT ON water_ledger FROM "{live.role}"')
        result = await seasons.field_season_state_endpoint(
            live.field_id, live.season_id, _user(live.tenant)
        )
        assert (result["water_deficit_7d_mm"], result["water_deficit_14d_mm"]) == (None, None)
        summary = result["outcome_reconciliation"]
        # Both outcome reads ran after the failed water read: without its savepoint they
        # would fail too and the summary would be unavailable with null counts.
        assert summary["available"] is True
        assert summary["source"] == "platform"
        # The failed decision outcome exists for this field but has no season without its
        # decision: it is counted as unbound and never reconciled into this season.
        assert summary["complete"] is False
        assert summary["missing_sources"] == ["outcome_record"]
        assert summary["unbound_outcome_records"] == 1
        assert summary["by_source"] == {"recommendation_outcomes": 1}
        assert (summary["total"], summary["failed"], summary["pending"]) == (1, 0, 1)
        assert "outcomes" in result["evidence_used"]

    _run(monkeypatch, platform_writes_required=True, case=case)


def test_another_tenants_season_is_404(monkeypatch):
    from fastapi import HTTPException

    async def case(live, seasons, _client):
        with pytest.raises(HTTPException) as caught:
            await seasons.field_season_state_endpoint(
                live.field_id, live.season_id, _user(str(uuid.uuid4()))
            )
        assert caught.value.status_code == 404

    _run(monkeypatch, platform_writes_required=False, case=case)
