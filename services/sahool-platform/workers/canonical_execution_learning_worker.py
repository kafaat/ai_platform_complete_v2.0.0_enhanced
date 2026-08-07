#!/usr/bin/env python3
"""Registered event worker for irrigation closure and season learning.

Consumes identifiers-only events from NATS JetStream. All truth is loaded from
PostgreSQL under ``app.current_tenant``; retries are safe through stable event IDs
and database uniqueness constraints. This worker never auto-promotes a model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# ``CONTAINER-COMMAND-PATH-NOT-IN-IMAGE-01``: هذا الملفّ كان في ``scripts/workers/`` بجذر
# المستودع، و``services/sahool-platform/Dockerfile`` ينسخ ``shared/`` و
# ``services/sahool-platform/`` فقط — فلم يكن في الصورة أصلاً، والحاوية تموت عند الإقلاع
# و``restart: unless-stopped`` يُعيدها إلى الأبد.
#
# ونسخُه كما كان **لم يكن ليكفي**: الصورة تنسخ **محتويات** جذر الخدمة إلى ``/app``، فـ
# ``api/`` تسكن ``/app/api``؛ بينما ``parents[2]`` كان يُنتِج ``/app`` ثمّ يبحث عن
# ``/app/services/sahool-platform`` — مسارٌ لا وجود له في الصورة. إصلاحٌ يبدو ناجحاً ويظلّ مكسوراً.
#
# فسكن العامل **تحت جذر الخدمة**: عندها ``parents[1]`` هو جذر الخدمة في الموضعين معاً —
# ``services/sahool-platform`` في المستودع، و``/app`` في الصورة. الشكلان يتطابقان، فالتعبير
# الواحد يصحّ فيهما بلا فرعٍ لبيئة.
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from api.canonical_nutrient_ledger import (  # noqa: E402  (import after sys.path insertion)
    CanonicalNutrientLedger,
    NutrientBalance,
)
from api.canonical_phenology_state import (  # noqa: E402  (import after sys.path insertion)
    CanonicalPhenologyState,
    PhenologyObservation,
)
from api.canonical_salinity_state import (  # noqa: E402  (import after sys.path insertion)
    CanonicalSalinityState,
)
from api.irrigation_closed_loop_runtime import (  # noqa: E402  (import after sys.path insertion)
    finalize_irrigation_closed_loop,
)
from api.learning_feedback import (  # noqa: E402  (import after sys.path insertion)
    process_season_closed_event,
)
from api.persisted_canonical_repositories import (  # noqa: E402  (import after sys.path insertion)
    decode_jsonb,
    persist_nutrient_projection,
    persist_phenology_projection,
    persist_salinity_projection,
)

LOGGER = logging.getLogger("canonical-execution-learning-worker")
SUBJECTS = (
    "sahool.events.irrigation.execution.completed",
    "sahool.events.season.closed",
    "sahool.events.agronomy.projection.requested",
)
SUBJECT_PREFIX = "sahool.events."
_DURABLE_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def durable_for_subject(base: str, subject: str) -> str:
    """Return this subject's own durable consumer name.

    A JetStream durable consumer binds to exactly ONE subscription. Subscribing a
    second subject under the same durable name is refused by the server — measured
    against nats-server v2.10.22 with nats-py:

        nats.js.errors.Error: nats: JetStream.Error consumer is already bound to
        a subscription

    That raise happened on the *second* iteration of the subscribe loop, before the
    worker reached its idle loop, so the worker never processed a single event. Its
    ``--preflight`` passed throughout: preflight checks that a stream covers each
    subject, which it does, and says nothing about consumer binding.

    The suffix is derived from the whole subject (dots → dashes) rather than from its
    last token: ``season.closed`` and a future ``irrigation.closed`` share a last
    token, and that collision would reinstate the identical crash under a name that
    merely looks distinct. Subjects are unique, so full-subject suffixes are too.

    No migration is owed to any deployment: the shared-name consumer could never be
    created for more than one subject, and the worker it belonged to never started.
    """
    suffix = _DURABLE_UNSAFE.sub("-", subject.removeprefix(SUBJECT_PREFIX)).strip("-")
    if not suffix:
        raise ValueError(f"subject yields no durable suffix: {subject!r}")
    return f"{base}-{suffix}"


async def subscribe_subjects(js: Any, *, durable_base: str, callback: Any) -> dict[str, str]:
    """Bind one durable consumer per subject and return the subject → durable map."""
    bound: dict[str, str] = {}
    for subject in SUBJECTS:
        durable = durable_for_subject(durable_base, subject)
        await js.subscribe(subject, durable=durable, cb=callback, manual_ack=True)
        bound[subject] = durable
        LOGGER.info("subscribed %s as durable %s", subject, durable)
    return bound


async def _tenant_transaction(pool: Any, tenant_id: str):
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()
    try:
        await conn.execute("SELECT set_config('app.current_tenant',$1,true)", tenant_id)
        return conn, tx
    except Exception:
        await tx.rollback()
        await pool.release(conn)
        raise


def _dt(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _date(value: Any) -> date:
    return date.fromisoformat(str(value))


async def _process_projection_request(conn: Any, *, request_id: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT * FROM canonical_projection_requests WHERE request_id=$1::uuid FOR UPDATE",
        request_id,
    )
    if not row:
        raise ValueError("PROJECTION_REQUEST_NOT_FOUND")
    if row["status"] == "processed":
        return {
            "status": "already_processed",
            "event_id": str(row["result_event_id"]) if row["result_event_id"] else None,
        }
    # asyncpg returns jsonb as **str** unless a codec is registered, and this worker's
    # pool registers none. `dict(row["canonical_payload"])` therefore raised
    #   ValueError: dictionary update sequence element #0 has length 1; 2 is required
    # on every projection event — and the callback classifies ValueError as permanent
    # invalid input, so it called `msg.term()`: a decoding bug in our code discarded a
    # perfectly valid event and reported it as bad data.
    #
    # `list(row["evidence_payload"])` was worse than a raise: on the string "[]" it
    # yields ['[', ']'] — two bogus observations, silently.
    #
    # `decode_jsonb` is the repository's existing idiom for this, imported rather than
    # re-declared so there is one definition to fix if jsonb handling ever changes.
    payload = dict(decode_jsonb(row["canonical_payload"], {}))
    evidence = list(decode_jsonb(row["evidence_payload"], []))
    kind = str(row["projection_type"])
    if kind == "phenology":
        payload.update(
            as_of=_dt(payload["as_of"]),
            sowing_date=_date(payload["sowing_date"]),
            observation_ids=tuple(payload.get("observation_ids", [])),
            evidence_digests=tuple(payload.get("evidence_digests", [])),
            limitations=tuple(payload.get("limitations", [])),
        )
        state = CanonicalPhenologyState(**payload)
        observations = [
            PhenologyObservation(**{**x, "observed_at": _dt(x["observed_at"])}) for x in evidence
        ]
        inserted, event_id = await persist_phenology_projection(conn, state, observations)
    elif kind == "salinity":
        payload.update(
            as_of=_dt(payload["as_of"]),
            limitations=tuple(payload.get("limitations", [])),
            evidence_digests=tuple(payload.get("evidence_digests", [])),
        )
        state = CanonicalSalinityState(**payload)
        for x in evidence:
            x["observed_at"] = _dt(x["observed_at"])
        inserted, event_id = await persist_salinity_projection(conn, state, evidence)
    elif kind == "nutrient":
        payload.update(
            as_of=_dt(payload["as_of"]),
            balances=tuple(NutrientBalance(**x) for x in payload.get("balances", [])),
            verified_operation_ids=tuple(payload.get("verified_operation_ids", [])),
            limitations=tuple(payload.get("limitations", [])),
            evidence_digests=tuple(payload.get("evidence_digests", [])),
        )
        ledger = CanonicalNutrientLedger(**payload)
        for x in evidence:
            x["observed_at"] = _dt(x["observed_at"])
        inserted, event_id = await persist_nutrient_projection(conn, ledger, evidence)
    else:
        raise ValueError("UNSUPPORTED_PROJECTION_TYPE")
    await conn.execute(
        "UPDATE canonical_projection_requests SET status='processed', result_event_id=$2::uuid, processed_at=now(), error_code=NULL WHERE request_id=$1::uuid",
        request_id,
        event_id,
    )
    return {"status": "processed", "inserted": inserted, "event_id": event_id}


async def handle_envelope(pool: Any, envelope: dict[str, Any]) -> dict[str, Any]:
    event_type = str(envelope.get("event_type") or "")
    event_id = str(envelope.get("event_id") or "")
    tenant_id = str(envelope.get("tenant_id") or "")
    payload = envelope.get("payload") or {}
    if not event_id or not tenant_id or not isinstance(payload, dict):
        raise ValueError("EVENT_ID_TENANT_AND_PAYLOAD_REQUIRED")

    conn, tx = await _tenant_transaction(pool, tenant_id)
    try:
        if event_type == "agronomy.projection.requested":
            result = await _process_projection_request(conn, request_id=str(payload["request_id"]))
        elif event_type == "season.closed":
            result = await process_season_closed_event(
                conn,
                event_id=event_id,
                tenant_id=tenant_id,
                field_id=str(payload["field_id"]),
                season_id=str(payload["season_id"]),
                minimum_outcomes=int(payload.get("minimum_outcomes", 3)),
            )
        elif event_type == "irrigation.execution.completed":
            required = {"run_id", "expected_depletion_after_mm", "source_digests"}
            missing = sorted(required - payload.keys())
            if missing:
                raise ValueError(f"IRRIGATION_EVENT_FIELDS_REQUIRED:{','.join(missing)}")
            result = await finalize_irrigation_closed_loop(
                conn,
                run_id=str(payload["run_id"]),
                measured_at=datetime.fromisoformat(
                    str(payload.get("measured_at") or datetime.now(UTC).isoformat()).replace(
                        "Z", "+00:00"
                    )
                ),
                expected_depletion_after_mm=float(payload["expected_depletion_after_mm"]),
                source_digests=dict(payload["source_digests"]),
                minimum_samples=int(payload.get("minimum_samples", 5)),
                water_use_efficiency_kg_m3=payload.get("water_use_efficiency_kg_m3"),
                energy_kwh=payload.get("energy_kwh"),
                stress_days_observed=payload.get("stress_days_observed"),
                yield_t_ha=payload.get("yield_t_ha"),
            )
        else:
            raise ValueError(f"UNSUPPORTED_EVENT_TYPE:{event_type}")
        await tx.commit()
        return result
    except Exception:
        await tx.rollback()
        raise
    finally:
        await pool.release(conn)


async def preflight() -> dict[str, Any]:
    """Fail-closed connectivity/schema check and return auditable facts."""
    import asyncpg

    import nats

    database_url = os.environ["DATABASE_URL"]
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    conn = await asyncpg.connect(database_url)
    try:
        missing = await conn.fetch(
            """SELECT required.name FROM (VALUES
               ('decision_learning_runs'),
               ('governed_model_promotion_candidates'),
               ('irrigation_closed_loop_records'),
               ('events'),('event_outbox'),('canonical_projection_requests')
             ) AS required(name)
             WHERE to_regclass('public.' || required.name) IS NULL"""
        )
        if missing:
            raise RuntimeError(
                "missing runtime tables: " + ",".join(str(r["name"]) for r in missing)
            )
        tables = [
            "decision_learning_runs",
            "governed_model_promotion_candidates",
            "irrigation_closed_loop_records",
            "events",
            "event_outbox",
            "canonical_projection_requests",
        ]
    finally:
        await conn.close()

    nc = await nats.connect(nats_url, connect_timeout=5)
    try:
        js = nc.jetstream()
        await js.account_info()
        missing_subjects: list[str] = []
        subject_streams: dict[str, str] = {}
        for subject in SUBJECTS:
            try:
                subject_streams[subject] = await js.find_stream_name_by_subject(subject)
            except Exception:
                missing_subjects.append(subject)
        if missing_subjects:
            raise RuntimeError(
                "JetStream has no stream covering required subjects: " + ",".join(missing_subjects)
            )
    finally:
        await nc.drain()

    return {
        "database": {"required_tables": tables, "status": "passed"},
        "jetstream": {"subject_streams": subject_streams, "status": "passed"},
    }


async def run() -> None:
    import asyncpg

    import nats

    database_url = os.environ["DATABASE_URL"]
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    durable = os.getenv("CANONICAL_LEARNING_DURABLE", "canonical-execution-learning-v1")
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    nc = await nats.connect(nats_url)
    js = nc.jetstream()

    async def callback(msg):
        try:
            envelope = json.loads(msg.data.decode("utf-8"))
            await handle_envelope(pool, envelope)
            await msg.ack()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            LOGGER.exception("permanent event validation failure")
            await msg.term()
        except Exception:
            LOGGER.exception("transient event processing failure")
            await msg.nak(delay=5)

    await subscribe_subjects(js, durable_base=durable, callback=callback)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await nc.drain()
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check PostgreSQL schema and NATS JetStream, then exit",
    )
    parser.add_argument(
        "--preflight-json",
        action="store_true",
        help="emit preflight facts as JSON for SHA-bound runtime evidence",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if args.preflight or args.preflight_json:
        result = asyncio.run(preflight())
        if args.preflight_json:
            print(json.dumps(result, sort_keys=True))
    else:
        asyncio.run(run())
