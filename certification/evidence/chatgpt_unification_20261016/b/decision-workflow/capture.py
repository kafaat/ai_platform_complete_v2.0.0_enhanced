"""Capture actual scoped writer SQL/transactions; no database connection is made."""

import argparse
import asyncio
import importlib
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.repo.resolve() / "services/decision-service"))
persistence = importlib.import_module("persistence")
queries = []
transactions = []


class Transaction:
    async def __aenter__(self):
        transactions.append({"sql": "BEGIN", "params": []})

    async def __aexit__(self, typ, exc, tb):
        transactions.append({"sql": "ROLLBACK" if typ else "COMMIT", "params": []})


class Connection:
    def transaction(self):
        return Transaction()

    async def execute(self, sql, *params):
        transactions.append({"sql": sql, "params": params})

    async def fetch(self, sql, *params):
        call = {"sql": sql, "params": params}
        queries.append(call)
        transactions.append(call)
        return []

    async def close(self):
        pass


async def connect():
    return Connection()


async def run():
    persistence._connect = connect
    await persistence.list_review_queue(
        tenant_id="00000000-0000-0000-0000-000000000001", field_id="f", season_id="s"
    )
    scoped = list(transactions)
    await persistence.list_review_queue(tenant_id="00000000-0000-0000-0000-000000000001")
    return scoped


scoped = asyncio.run(run())
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "captured-queries.json").write_text(
    json.dumps(queries, indent=2) + "\n", encoding="utf-8"
)
(args.output / "captured-scoped-transaction.json").write_text(
    json.dumps(scoped, indent=2) + "\n", encoding="utf-8"
)
