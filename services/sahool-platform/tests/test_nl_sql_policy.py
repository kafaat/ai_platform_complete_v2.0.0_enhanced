"""NL→SQL must enforce the tenant's policy before sending a raw question.

The real handler, SQL validator and policy builder run here. Only the database
connection and provider are replaced; no external request or service startup runs.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

# Bootstrap the application before a router imports symbols back from main.
from api import main as platform
from api.routers import nl_sql
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"
USER = UserSchema(user_id="policy-test", tenant_id=TENANT, role=UserRole.VIEWER, name_ar="test")
QUESTION = "أي حقول المزرعة تحتاج مراجعة؟"


@pytest.fixture
def boundary(monkeypatch):
    import anthropic

    monkeypatch.setenv("FEATURE_NATURAL_LANGUAGE_GIS", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-unused-provider-key")
    monkeypatch.setenv("NL_SQL_MODEL", "test-model")
    monkeypatch.setattr(nl_sql, "_calls", defaultdict(list))
    state = SimpleNamespace(
        row=None, db_error=False, read_error=False, db_reads=[], calls=[], closed=0
    )

    class Connection:
        async def fetchrow(self, sql, tenant_id):
            state.db_reads.append((sql, tenant_id))
            if state.read_error:
                raise RuntimeError("policy_query_unavailable")
            return state.row

    @asynccontextmanager
    async def connection(user):
        assert user.tenant_id == TENANT
        if state.db_error:
            raise RuntimeError("policy_database_unavailable")
        yield Connection()

    monkeypatch.setattr(nl_sql, "tenant_connection", connection, raising=False)

    def reply(**kwargs):
        state.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="SELECT field_id FROM fields")]
        )

    class SyncProvider:
        def __init__(self, **kwargs):
            self.messages = SimpleNamespace(create=reply)

    class AsyncProvider:
        def __init__(self, **kwargs):
            self.messages = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            state.closed += 1

        async def create(self, **kwargs):
            await asyncio.sleep(0)
            return reply(**kwargs)

    monkeypatch.setattr(anthropic, "Anthropic", SyncProvider)
    monkeypatch.setattr(anthropic, "AsyncAnthropic", AsyncProvider)
    return state


@pytest.mark.parametrize(
    "row",
    [
        None,
        {},
        {"ai_generation_allowed": True, "external_data_sharing_level": "local_only"},
        {"ai_generation_allowed": True, "external_data_sharing_level": "redacted_external"},
        {"ai_generation_allowed": True, "external_data_sharing_level": "unknown"},
        {"external_data_sharing_level": "full_external"},
        *[
            {"ai_generation_allowed": value, "external_data_sharing_level": "full_external"}
            for value in (False, None, "true", 1, "yes")
        ],
        *[
            {
                "ai_generation_allowed": True,
                "external_data_sharing_level": "full_external",
                **restrictions,
            }
            for restrictions in (
                {"allowed_providers": ["local"]},
                {"allowed_models": ["another-model"]},
                {"allowed_providers": "anthropic"},
                {"allowed_models": "test-model"},
            )
        ],
    ],
)
def test_denied_or_unredacted_questions_never_reach_a_provider(boundary, row):
    boundary.row = row
    with pytest.raises(HTTPException) as failure:
        asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert failure.value.status_code == 403
    assert boundary.calls == []
    assert len(boundary.db_reads) == 1
    assert boundary.db_reads[0][1] == TENANT


def test_policy_connection_failure_does_not_send_the_question(boundary):
    boundary.db_error = True
    with pytest.raises(HTTPException) as failure:
        asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert failure.value.status_code == 503
    assert boundary.calls == []


def test_an_unreadable_policy_cannot_fall_back_to_external_sending(boundary):
    boundary.read_error = True
    with pytest.raises(HTTPException) as failure:
        asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert failure.value.status_code == 403
    assert boundary.calls == []


def test_explicit_permission_still_returns_validated_sql(boundary):
    boundary.row = {"ai_generation_allowed": True, "external_data_sharing_level": "full_external"}
    result = asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert result.sql == "SELECT field_id FROM fields"
    assert boundary.calls[0]["messages"] == [{"role": "user", "content": QUESTION}]
    assert boundary.db_reads[0][1] == TENANT
    assert boundary.closed == 1


def test_permitted_provider_alias_and_model_remain_usable(boundary):
    boundary.row = {
        "ai_generation_allowed": True,
        "external_data_sharing_level": "full_external",
        "allowed_providers": ["claude"],
        "allowed_models": ["test-model"],
    }
    result = asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert result.sql == "SELECT field_id FROM fields"
    assert boundary.calls[0]["model"] == "test-model"


@pytest.mark.parametrize("flag, key, status", [("false", "present", 404), ("true", "", 503)])
def test_configuration_guards_do_not_read_policy_or_call_a_provider(
    boundary, monkeypatch, flag, key, status
):
    monkeypatch.setenv("FEATURE_NATURAL_LANGUAGE_GIS", flag)
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER))
    assert failure.value.status_code == status
    assert boundary.db_reads == boundary.calls == []


def test_provider_io_yields_to_other_requests(boundary, monkeypatch):
    import anthropic

    boundary.row = {"ai_generation_allowed": True, "external_data_sharing_level": "full_external"}

    async def run():
        provider_started = asyncio.Event()
        peer_ran = asyncio.Event()

        class YieldingProvider:
            def __init__(self, **kwargs):
                self.messages = self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def create(self, **kwargs):
                provider_started.set()
                await asyncio.wait_for(peer_ran.wait(), timeout=1)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="SELECT field_id FROM fields")]
                )

        async def peer():
            await provider_started.wait()
            peer_ran.set()

        monkeypatch.setattr(anthropic, "AsyncAnthropic", YieldingProvider)
        task = asyncio.create_task(peer())
        try:
            result = await asyncio.wait_for(
                nl_sql.nl_sql_endpoint(nl_sql.NlSqlQuery(question=QUESTION), USER), timeout=2
            )
            assert peer_ran.is_set()
            assert result.sql == "SELECT field_id FROM fields"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
