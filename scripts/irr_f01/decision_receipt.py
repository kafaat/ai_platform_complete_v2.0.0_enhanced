"""Exercise the decision-service inbox against its own disposable database."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/decision-service"))
import migration_runner  # noqa: E402
import persistence  # noqa: E402


async def certify(tenant, delivery):
    db = "irr_f01_decision_" + uuid4().hex
    owner = urlsplit(os.environ["TEST_DATABASE_ADMIN_URL"])
    service = urlsplit(os.environ["OTHER_TENANT_DATABASE_URL"])
    admin = await asyncpg.connect(owner.geturl())
    try:
        await admin.execute(f'CREATE DATABASE "{db}" TEMPLATE template0')
        try:
            os.environ["DATABASE_URL"] = owner._replace(path="/" + db).geturl()
            os.environ["DECISION_SERVICE_ALLOW_SCHEMA_CHANGE"] = "true"
            await migration_runner.apply_migrations()
            setup = await asyncpg.connect(os.environ["DATABASE_URL"])
            try:
                await setup.execute(
                    "GRANT SELECT, INSERT ON decision_reservation_dispatch_inbox TO irr_f01_decision;"
                    "GRANT SELECT, INSERT, UPDATE ON decision_consumer_heartbeats TO irr_f01_decision;"
                )
            finally:
                await setup.close()
            del os.environ["DECISION_SERVICE_ALLOW_SCHEMA_CHANGE"]
            os.environ["DATABASE_URL"] = service._replace(path="/" + db).geturl()
            args = dict(
                tenant_id=tenant,
                source_event_id=delivery["source_event_id"],
                event_type=delivery["event_type"],
                payload=SimpleNamespace(**delivery),
            )
            first = await persistence.record_reservation_dispatch_intent(**args)
            repeat = await persistence.record_reservation_dispatch_intent(**args)
            assert first["status"] == "received" and repeat["status"] == "duplicate"
            assert first["receipt_id"] == repeat["receipt_id"]
            reader = await asyncpg.connect(os.environ["DATABASE_URL"])
            try:
                query = "SELECT count(*) FROM decision_reservation_dispatch_inbox WHERE source_event_id=$1"
                assert await reader.fetchval("SELECT current_user") == "irr_f01_decision"
                for scope, expected in ((tenant, 1), (str(uuid4()), 0)):
                    async with reader.transaction():
                        await reader.execute("SELECT set_config('app.current_tenant',$1,true)", scope)
                        assert await reader.fetchval(query, delivery["source_event_id"]) == expected
            finally:
                await reader.close()
            return first["receipt_id"]
        finally:
            await persistence.close_pools()
            await admin.execute(f'DROP DATABASE "{db}"')
    finally:
        await admin.close()


if __name__ == "__main__":
    envelope = json.load(sys.stdin)
    print(asyncio.run(certify(envelope["tenant"], envelope["delivery"])))
