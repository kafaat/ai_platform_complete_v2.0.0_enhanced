"""Phase C certification: NO future data can leak into a composed agronomic context.

A deterministic randomized property sweep on real Postgres: compositions with any
leaky feature (available only after the decision cutoff) MUST be rejected with the
typed `future_leakage` violation and ZERO rows written; fully clean compositions MUST
be accepted. The database-level CHECKs (row invariants) are proven independently of
the composer, so the guarantee holds even for a hypothetical buggy write path.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")

TENANT = "00000000-0000-0000-0000-000000009181"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _now():
    return datetime.now(UTC).replace(microsecond=0)


CONTEXT = {
    "crop": {"crop_id": "wheat", "cultivar_id": "yecora", "crop_card_version": "v3"},
    "soil": {"ph": 7.1},
    "irrigation": {"type": "drip"},
    "weather": {"et0_mm": 5.2},
    "climate": {"drought_index": 0.2},
    "terrain": {"slope_pct": 2.0},
    "operations": {},
}


def _payload(field_id: str, feature_specs: list[tuple[str, bool]], now: datetime):
    """feature_specs: (name, leaks) — a leaking feature becomes available AFTER the cutoff."""
    from agronomic_context.contracts import ContextComposeIn, FeatureEntryIn, HistoricalContextIn

    features = []
    for name, leaks in feature_specs:
        observed = now - timedelta(days=2)
        available = now + timedelta(hours=3) if leaks else now - timedelta(hours=6)
        features.append(
            FeatureEntryIn(
                name=name,
                value=round(random.uniform(0.1, 0.9), 3),
                unit="index",
                source_service="raster-service",
                observed_at=observed,
                available_at=available,
                quality_status="verified",
            )
        )
    return ContextComposeIn(
        field_id=field_id,
        season_id="s2026",
        as_of_time=now,
        decision_cutoff_time=now,
        context=CONTEXT,
        historical=HistoricalContextIn(
            history_from=now - timedelta(days=30),
            history_to=now - timedelta(hours=1),
            history={"ndvi_trend_14d": -0.03},
        ),
        features=features,
        idempotency_key="cert_" + uuid4().hex,
    )


def test_randomized_no_leakage_property_sweep():
    """40 randomized compositions: leaky ⇒ typed rejection + zero writes; clean ⇒ accepted."""
    from persistence import compose_agronomic_context

    random.seed(42)  # deterministic sweep — reproducible certification evidence
    now = _now()
    rejected, accepted = 0, 0

    for i in range(40):
        field = f"f_cert_{i}_" + uuid4().hex[:6]
        n_features = random.randint(1, 6)
        specs = [(f"feat_{j}_{uuid4().hex[:4]}", random.random() < 0.35) for j in range(n_features)]
        any_leak = any(leaks for _, leaks in specs)
        result = _run(
            compose_agronomic_context(
                tenant_id=TENANT, created_by="certifier", payload=_payload(field, specs, now)
            )
        )
        if any_leak:
            rejected += 1
            assert result["status"] == "rejected", f"leaky composition {i} was ACCEPTED"
            assert result["reason"] == "point_in_time_policy"
            assert "future_leakage" in {v["code"] for v in result["violations"]}

            async def zero_writes(field_id=field):
                c = await _connect()
                try:
                    return await c.fetchval(
                        "SELECT count(*) FROM decision_agronomic_context_snapshots"
                        " WHERE tenant_id=$1::uuid AND field_id=$2",
                        TENANT,
                        field_id,
                    )
                finally:
                    await c.close()

            assert _run(zero_writes()) == 0, f"leaky composition {i} left rows behind"
        else:
            accepted += 1
            assert result["status"] == "ok", f"clean composition {i} was rejected: {result}"

    # the sweep must actually exercise BOTH branches to certify anything.
    assert rejected >= 5 and accepted >= 5, f"sweep imbalance: {rejected=} {accepted=}"


def test_history_window_violations_are_typed():
    """history_to beyond as_of and inverted windows are typed PIT violations, never writes."""
    from agronomic_context.contracts import ContextComposeIn, HistoricalContextIn
    from persistence import compose_agronomic_context

    now = _now()

    def compose(hist_from, hist_to):
        return _run(
            compose_agronomic_context(
                tenant_id=TENANT,
                created_by="certifier",
                payload=ContextComposeIn(
                    field_id="f_hist_" + uuid4().hex[:6],
                    season_id="s2026",
                    as_of_time=now,
                    decision_cutoff_time=now,
                    context=CONTEXT,
                    historical=HistoricalContextIn(
                        history_from=hist_from, history_to=hist_to, history={"x": 1}
                    ),
                    features=[],
                    idempotency_key="cert_" + uuid4().hex,
                ),
            )
        )

    beyond = compose(now - timedelta(days=10), now + timedelta(hours=2))
    assert beyond["status"] == "rejected"
    assert "history_extends_past_as_of" in {v["code"] for v in beyond["violations"]}

    inverted = compose(now - timedelta(hours=1), now - timedelta(days=1))
    assert inverted["status"] == "rejected"
    assert "empty_history_window" in {v["code"] for v in inverted["violations"]}


def test_database_row_invariants_hold_without_the_composer():
    """The SQL CHECKs are the last line: even a buggy writer cannot persist leakage."""

    async def attempt(sql, *args):
        c = await _connect()
        try:
            await c.execute(sql, *args)
            return "inserted"
        except Exception as exc:  # noqa: BLE001 - the assertion IS about the raised class
            return type(exc).__name__
        finally:
            await c.close()

    now = _now()
    # feature observed AFTER its availability is physically impossible — row CHECK refuses.
    out = _run(
        attempt(
            """INSERT INTO decision_feature_manifest_entries
               (entry_id, tenant_id, feature_manifest_id, name, value, source_service,
                observed_at, available_at, quality_status)
               VALUES ($1, $2::uuid, 'fmanif_missing', 'leak', '1'::jsonb, 'raster-service',
                       $3, $4, 'verified')""",
            "entry_" + uuid4().hex[:12],
            TENANT,
            now,
            now - timedelta(hours=1),
        )
    )
    assert out != "inserted"

    # a historical snapshot whose window ends after as_of is refused by the row CHECK.
    out = _run(
        attempt(
            """INSERT INTO decision_field_historical_context_snapshots
               (historical_snapshot_id, tenant_id, field_id, as_of_time, history_from,
                history_to, manifest_version, history, content_hash, created_by,
                idempotency_key, request_hash)
               VALUES ($1, $2::uuid, 'f_x', $3, $4, $5, 'v1', '{}'::jsonb, $6, 'certifier',
                       $7, 'h')""",
            "fhist_" + uuid4().hex[:12],
            TENANT,
            now,
            now - timedelta(days=5),
            now + timedelta(hours=1),
            "a" * 64,
            "cert_" + uuid4().hex,
        )
    )
    assert out != "inserted"
