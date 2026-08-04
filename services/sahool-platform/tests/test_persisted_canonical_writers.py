from __future__ import annotations

import ast
import importlib
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "services/sahool-platform"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

repo = importlib.import_module("api.persisted_canonical_repositories")
phen = importlib.import_module("api.canonical_phenology_state")
sal = importlib.import_module("api.canonical_salinity_state")
nut = importlib.import_module("api.canonical_nutrient_ledger")


class FakeConn:
    def __init__(self, status: str = "INSERT 0 1") -> None:
        self.status = status
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, *args):
        self.calls.append((sql, args))
        return self.status


@pytest.mark.asyncio
async def test_phenology_writer_is_digest_idempotent_and_uses_state_tenant():
    state = phen.CanonicalPhenologyState(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        sowing_date=date(2026, 1, 1),
        days_since_sowing=214,
        observed_stage="mid",
        predicted_stage="mid",
        canonical_stage="mid",
        status="observed",
        confidence=0.9,
        accumulated_gdd=500.0,
        gdd_fraction=0.5,
        stage_divergence="aligned",
        observation_ids=("o1",),
        evidence_digests=("a" * 64,),
        limitations=(),
        state_digest="b" * 64,
    )
    conn = FakeConn()
    assert await repo.persist_phenology_state(conn, state) is True
    sql, args = conn.calls[0]
    assert "ON CONFLICT (tenant_id, state_digest) DO NOTHING" in sql
    assert args[0] == state.tenant_id and args[1] == state.state_digest


@pytest.mark.asyncio
async def test_salinity_writer_reports_duplicate_without_mutation():
    state = sal.CanonicalSalinityState(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        status="blocked",
        soil_class=None,
        water_risk=None,
        sodium_hazard_class=None,
        rsc_hazard_class=None,
        effective_crop_threshold_ece_dsm=None,
        estimated_relative_yield=None,
        leaching_fraction=None,
        leaching_feasible=None,
        drainage_class="unknown",
        operational_recommendation_allowed=False,
        limitations=("MISSING",),
        evidence_digests=(),
        state_digest="c" * 64,
    )
    conn = FakeConn("INSERT 0 0")
    assert await repo.persist_salinity_state(conn, state) is False
    assert "ON CONFLICT (tenant_id, state_digest) DO NOTHING" in conn.calls[0][0]


@pytest.mark.asyncio
async def test_nutrient_writer_serializes_balances_and_digest():
    ledger = nut.CanonicalNutrientLedger(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        status="managed",
        operational_recommendation_allowed=True,
        balances=(nut.NutrientBalance("N", 20.0, 100.0, 30.0, 50.0, 0.0),),
        total_verified_cost=10.0,
        currency="YER",
        verified_operation_ids=("op1",),
        limitations=(),
        evidence_digests=("d" * 64,),
        ledger_digest="e" * 64,
    )
    conn = FakeConn()
    assert await repo.persist_nutrient_ledger(conn, ledger) is True
    sql, args = conn.calls[0]
    assert "ON CONFLICT (tenant_id, field_id, season_id, ledger_digest) DO NOTHING" in sql
    assert '"nutrient": "N"' in args[9]
    assert args[-1] == ledger.ledger_digest


class ProjectionConn(FakeConn):
    def __init__(self, statuses: list[str] | None = None) -> None:
        super().__init__()
        self.statuses = list(statuses or [])
        self.fetchval_calls: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, *args):
        self.calls.append((sql, args))
        return self.statuses.pop(0) if self.statuses else "INSERT 0 1"

    async def fetchval(self, sql: str, *args):
        self.fetchval_calls.append((sql, args))
        return "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_phenology_projection_binds_evidence_state_and_outbox_atomically():
    obs = phen.PhenologyObservation(
        observation_id="o1",
        source="agronomist",
        stage="mid",
        observed_at=datetime(2026, 8, 3, tzinfo=UTC),
        confidence=0.95,
        evidence_digest="a" * 64,
    )
    state = phen.CanonicalPhenologyState(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        sowing_date=date(2026, 1, 1),
        days_since_sowing=214,
        observed_stage="mid",
        predicted_stage="mid",
        canonical_stage="mid",
        status="observed",
        confidence=0.95,
        accumulated_gdd=500.0,
        gdd_fraction=0.5,
        stage_divergence="aligned",
        observation_ids=("o1",),
        evidence_digests=("a" * 64,),
        limitations=(),
        state_digest="b" * 64,
    )
    conn = ProjectionConn()
    inserted, event_id = await repo.persist_phenology_projection(conn, state, [obs])
    assert inserted is True
    assert event_id == "11111111-1111-1111-1111-111111111111"
    assert "INSERT INTO phenology_observations" in conn.calls[0][0]
    assert "INSERT INTO canonical_phenology_states" in conn.calls[1][0]
    assert len(conn.fetchval_calls) == 1
    assert conn.fetchval_calls[0][1][0] == "agronomy.phenology.projected"


def test_the_outbox_intent_never_synthesizes_a_command_id():
    """A fabricated command id is not a free idempotency key — it is an FK violation.

    ``events.command_id`` is ``UUID REFERENCES commands(command_id)``
    (migrations/v11_events_bus.sql:39, never dropped). Reproduced on PostgreSQL 16
    against that schema, an invented id fails with::

        insert or update on table "events" violates foreign key constraint
        "events_command_id_fkey"

    A projection has no originating command row — only ``api/command_store.py`` writes
    ``commands`` — so the emit binds NULL. The fake-connection tests around this one
    cannot see it: a stub ``fetchval`` accepts any argument. This reads the parsed
    module instead, so the prose above (which names ``uuid5`` to record why) cannot
    satisfy a substring check on behalf of the code it warns about.
    """
    tree = ast.parse(Path(repo.__file__).read_text(encoding="utf-8"))
    minted = sorted(
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"uuid1", "uuid4", "uuid5"}
    )
    assert not minted, (
        f"minting a command id ({minted}) would break the events_command_id_fkey constraint"
    )


def test_projection_idempotency_rests_on_deterministic_dedup_inputs():
    """Retry safety comes from ``dedup_key``, so its inputs must be state-derived.

    ``emit_event`` deduplicates on tenant + event_type + entity_id + payload_hash +
    the DATE of ``occurred_at``. Omitting ``occurred_at`` (letting it default to NOW())
    or serialising the payload unsorted would make two replays hash differently and
    emit twice.
    """
    source = Path(repo.__file__).read_text(encoding="utf-8")
    assert "timestamptz" in repo._EMIT_PROJECTION_SQL, "occurred_at must be supplied"
    assert "json.dumps(payload, sort_keys=True)" in source, (
        "an unsorted payload changes payload_hash between identical replays"
    )


@pytest.mark.asyncio
async def test_projection_replay_does_not_emit_second_outbox_event():
    state = sal.CanonicalSalinityState(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        status="blocked",
        soil_class=None,
        water_risk=None,
        sodium_hazard_class=None,
        rsc_hazard_class=None,
        effective_crop_threshold_ece_dsm=None,
        estimated_relative_yield=None,
        leaching_fraction=None,
        leaching_feasible=None,
        drainage_class="unknown",
        operational_recommendation_allowed=False,
        limitations=("MISSING",),
        evidence_digests=("c" * 64,),
        state_digest="d" * 64,
    )
    evidence = [
        {
            "tenant_id": state.tenant_id,
            "field_id": "f1",
            "season_id": "s1",
            "evidence_id": "ev1",
            "evidence_type": "soil_ece",
            "observed_at": state.as_of,
            "evidence_digest": "c" * 64,
            "payload": {"ece_dsm": 4.2},
        }
    ]
    conn = ProjectionConn(["INSERT 0 0", "INSERT 0 0"])
    inserted, event_id = await repo.persist_salinity_projection(conn, state, evidence)
    assert inserted is False
    assert event_id is None
    assert conn.fetchval_calls == []


@pytest.mark.asyncio
async def test_projection_rejects_cross_tenant_evidence_before_writing():
    ledger = nut.CanonicalNutrientLedger(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="mid",
        as_of=datetime(2026, 8, 3, tzinfo=UTC),
        status="managed",
        operational_recommendation_allowed=True,
        balances=(nut.NutrientBalance("N", 20.0, 100.0, 30.0, 50.0, 0.0),),
        total_verified_cost=None,
        currency=None,
        verified_operation_ids=(),
        limitations=(),
        evidence_digests=("e" * 64,),
        ledger_digest="f" * 64,
    )
    conn = ProjectionConn()
    with pytest.raises(ValueError, match="tenant_id"):
        await repo.persist_nutrient_projection(
            conn,
            ledger,
            [
                {
                    "tenant_id": "00000000-0000-0000-0000-000000000002",
                    "field_id": "f1",
                    "season_id": "s1",
                    "evidence_type": "soil_lab",
                    "observed_at": ledger.as_of,
                    "evidence_digest": "e" * 64,
                    "payload": {},
                }
            ],
        )
    assert conn.calls == []
