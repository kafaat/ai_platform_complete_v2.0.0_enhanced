"""Run against two disposable PostgreSQL databases; only create/drop private fixture schemas."""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backfill

SOURCE = os.getenv("PLATFORM_DATABASE_URL")
TARGET = os.getenv("DECISION_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not SOURCE or not TARGET or SOURCE == TARGET, reason="requires two distinct test database URLs"
)


def test_verify_rows_id_content_tenant_destination_and_duplicate(monkeypatch):
    async def exercise():
        schema = "cmp_" + uuid4().hex
        connect = backfill._connect
        src = await connect(SOURCE)
        dst = await connect(TARGET)
        try:
            for conn in (src, dst):
                await conn.execute(f"CREATE SCHEMA {schema}")
                await conn.execute(f"SET search_path TO {schema}")
                for table, logical_id in backfill._LOGICAL_IDS.items():
                    await conn.execute(
                        f"CREATE TABLE {table} (tenant_id uuid, {logical_id} text, value jsonb)"
                    )

            async def scoped(url):
                conn = await connect(url)
                await conn.execute(f"SET search_path TO {schema}")
                return conn

            monkeypatch.setattr(backfill, "_connect", scoped)
            a, b = uuid4(), uuid4()
            table = "recommendation_outcomes"
            identity = backfill._LOGICAL_IDS[table]
            for conn in (src, dst):
                await conn.execute(f"INSERT INTO {table} VALUES ($1,'same','1')", a)
            await dst.execute(f"ALTER TABLE {table} ADD COLUMN note text")
            coverage = await backfill.verify_counts()
            assert coverage["ok"] and coverage["comparisons"][table][
                "destination_only_columns"
            ] == ["note"]
            await dst.execute(f"UPDATE {table} SET {identity}='different'")
            result = await backfill.verify_counts()
            assert not result["ok"] and result["comparisons"][table]["missing"] == 1
            await dst.execute(f"UPDATE {table} SET {identity}='same', tenant_id=$1", b)
            result = await backfill.verify_counts()
            assert not result["ok"] and result["comparisons"][table]["missing"] == 1
            await dst.execute(f"UPDATE {table} SET tenant_id=$1, value='2'", a)
            result = await backfill.verify_counts()
            assert not result["ok"] and result["comparisons"][table]["different"] == 1
            await dst.execute(f"UPDATE {table} SET value='1'")
            await dst.execute(f"INSERT INTO {table} VALUES ($1,'same','4')", b)
            assert (await backfill.verify_counts())["ok"]
            strict = await backfill.verify_counts(exact=True)
            assert not strict["ok"] and strict["comparisons"][table]["destination_only"] == 1
            await src.execute(f"INSERT INTO {table} VALUES ($1,'same','1')", a)
            invalid = await backfill.verify_counts()
            assert not invalid["ok"] and invalid["comparisons"][table]["invalid_keys"] > 0
        finally:
            for conn in (src, dst):
                await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
                await conn.close()

    asyncio.run(exercise())
