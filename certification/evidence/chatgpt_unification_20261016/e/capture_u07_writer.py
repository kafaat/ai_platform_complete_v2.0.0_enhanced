"""Capture real U07 SQL and transaction boundaries for engine execution."""

import asyncio
import importlib
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

repo = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(repo), str(repo / "services/sahool-platform")]
os.environ["DECISION_SOR_MODE"] = "platform_sor"
store = importlib.import_module("api.phase_runtime_store")
client = importlib.import_module("api.decision_service_client")
lineage = importlib.import_module("core.learning_source_lineage")
client.record_learning_update = AsyncMock()
calls = []


class Recorder:
    async def execute(self, query, *args):
        calls.append({"sql": query, "args": args})

    @asynccontextmanager
    async def transaction(self):
        calls.append({"sql": "BEGIN", "args": []})
        try:
            yield
        except Exception:
            calls.append({"sql": "ROLLBACK", "args": []})
            raise
        else:
            calls.append({"sql": "COMMIT", "args": []})


class Pool:
    @asynccontextmanager
    async def acquire(self):
        yield Recorder()


async def main():
    out = []
    for tenant in [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    ]:
        for review in [
            None,
            {"reviewer_id": "expert", "verdict": "approved", "evidence_ids": ["e1"]},
            {"reviewer_id": "expert", "verdict": "rejected"},
            None,
        ]:
            calls.clear()
            update = {
                "update_id": "u1",
                "model_id": "m1",
                "feature_set_id": "f1",
                "action": "defer",
                "source_type": "human_feedback",
                "source_id": "s1",
                "review": review,
            }
            request = SimpleNamespace(
                headers={"x-tenant-id": tenant},
                app=SimpleNamespace(state=SimpleNamespace(db_pool=Pool())),
            )
            await store.persist_phase10_learning_outputs(
                request, {"online_learning_update": update}
            )
            out.append(
                {
                    "tenant": tenant,
                    "expected": lineage.resolve_learning_source(update),
                    "calls": list(calls),
                }
            )
    print(json.dumps(out, default=str))


asyncio.run(main())
