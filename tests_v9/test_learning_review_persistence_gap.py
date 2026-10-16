"""U07: exercise the real writer, preserving review and tenant independently."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-4111-8111-111111111111"
pytestmark = pytest.mark.unit


@pytest.fixture
def writer(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "services/sahool-platform"))
    from api import decision_service_client, phase_runtime_store

    monkeypatch.setenv("DECISION_SOR_MODE", "platform_sor")
    monkeypatch.setattr(decision_service_client, "record_learning_update", AsyncMock())
    return phase_runtime_store


@pytest.mark.parametrize(
    ("review", "status", "approved"),
    [
        (None, "unreviewed", False),
        (
            {"reviewer_id": " agronomist ", "verdict": "approved", "evidence_ids": [" e1 "]},
            "approved",
            True,
        ),
        ({"reviewer_id": "agronomist", "verdict": "rejected"}, "rejected", False),
        ({"reviewer_id": "agronomist", "verdict": "approved"}, "unreviewed", False),
    ],
)
def test_writer_binds_review_and_tenant(writer, review, status, approved):
    calls = []
    active = False
    scoped = []

    class Connection:
        @asynccontextmanager
        async def transaction(self):
            nonlocal active
            assert not active
            active = True
            scoped.append("BEGIN")
            try:
                yield
            except Exception:
                scoped.append("ROLLBACK")
                raise
            else:
                scoped.append("COMMIT")
            finally:
                active = False

        async def execute(self, query, *args):
            calls.append((query, args))
            if active:
                scoped.append(query)

    from api import decision_service_client

    async def mirror_after_commit(*args, **kwargs):
        assert not active
        assert scoped[-1] == "COMMIT"

    decision_service_client.record_learning_update.side_effect = mirror_after_commit

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Connection()

    request = SimpleNamespace(
        headers={"x-tenant-id": TENANT}, app=SimpleNamespace(state=SimpleNamespace(db_pool=Pool()))
    )
    update = {
        "update_id": "u1",
        "model_id": "m1",
        "feature_set_id": "f1",
        "source_type": "human_feedback",
        "source_id": "s1",
        "review": review,
    }
    asyncio.run(
        writer.persist_phase10_learning_outputs(request, {"online_learning_update": update})
    )
    query, args = next((q, a) for q, a in calls if "INSERT INTO online_learning_updates" in q)
    columns = query.split("(", 1)[1].split(")", 1)[0].replace("\n", "").split(",")
    row = dict(zip((c.strip() for c in columns), args, strict=True))
    assert row["tenant_id"] == UUID(TENANT)
    assert row["traceability_status"] == "traceable"
    assert row["review_status"] == status
    assert row["agronomically_approved"] is approved
    payload = json.loads(row["agronomic_review"]) if row["agronomic_review"] is not None else None
    assert payload is None if review is None else payload["reviewer_id"] == "agronomist"
    assert "ON CONFLICT (tenant_id, update_id)" in query
    for column in ("review_status", "agronomically_approved", "agronomic_review"):
        assert f"{column} = EXCLUDED.{column}" in query
    assert any("app.current_tenant" in q and a == (TENANT,) for q, a in calls)
    assert scoped[0] == "BEGIN" and scoped[-1] == "COMMIT"
    assert len(scoped) == 5  # BEGIN, both local GUCs, INSERT, COMMIT.
    assert "app.current_tenant" in scoped[1]
    assert "app.tenant_id" in scoped[2]
    assert "INSERT INTO online_learning_updates" in scoped[3]
    decision_service_client.record_learning_update.assert_awaited_once()


def test_learning_write_failure_rolls_back_and_never_mirrors(writer):
    events = []

    class Connection:
        @asynccontextmanager
        async def transaction(self):
            events.append("BEGIN")
            try:
                yield
            except RuntimeError:
                events.append("ROLLBACK")
                raise
            else:
                events.append("COMMIT")

        async def execute(self, query, *args):
            if "INSERT INTO online_learning_updates" in query:
                raise RuntimeError("synthetic write failure")

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Connection()

    request = SimpleNamespace(
        headers={"x-tenant-id": TENANT}, app=SimpleNamespace(state=SimpleNamespace(db_pool=Pool()))
    )
    with pytest.raises(RuntimeError, match="synthetic write failure"):
        asyncio.run(
            writer.persist_phase10_learning_outputs(
                request, {"online_learning_update": {"update_id": "u1"}}
            )
        )
    assert events == ["BEGIN", "ROLLBACK"]
    from api import decision_service_client

    decision_service_client.record_learning_update.assert_not_awaited()


def test_review_migration_registered_before_final_rls():
    name = "v234_learning_agronomic_review.sql"
    for path in ("migrations/MANIFEST.txt", "scripts_v9/run_migrations.sql"):
        text = (ROOT / path).read_text(encoding="utf-8")
        entries = [
            line.removeprefix("\\i ").strip()
            for line in text.splitlines()
            if line.startswith("\\i ") or (line.startswith("v") and line.endswith(".sql"))
        ]
        entries = [entry.removeprefix("migrations/") for entry in entries]
        assert entries.count(name) == 1
        assert entries.index(name) < entries.index("v206_rls_final_hardening.sql")
