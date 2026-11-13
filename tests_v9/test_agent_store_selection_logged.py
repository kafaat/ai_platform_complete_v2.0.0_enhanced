"""ai-agronomist logs which agent store it chose, so deploy logs can tell Redis from memory.

Before this, only a Redis failure logged ("falling back to memory"); a working Redis and a
memory store configured on purpose looked identical in the logs. Staging's logs of
2026-11-02 show the fallback; later deploys showed nothing either way.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import agent_stores as S  # noqa: E402

_SECRET_URL = "redis://:s3cret-pass@redis.internal:6379/0"


def _selection_lines(caplog):
    return [r for r in caplog.records if "store selected" in r.getMessage()]


def test_memory_by_configuration_is_logged(monkeypatch, caplog):
    monkeypatch.delenv("SAHOOL_AGENT_STORE_BACKEND", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    with caplog.at_level(logging.WARNING, logger="ai_agronomist.agent_stores"):
        assert isinstance(S.build_approval_store(), S.InMemoryApprovalStore)
        assert isinstance(S.build_audit_store(), S.InMemoryAuditStore)
    lines = [r.getMessage() for r in _selection_lines(caplog)]
    assert lines == [
        "agent approval store selected: backend=memory requested=memory production=False",
        "agent audit store selected: backend=memory requested=memory production=False",
    ]


def test_redis_requested_but_unavailable_says_so_and_never_logs_the_url(monkeypatch, caplog):
    monkeypatch.setenv("SAHOOL_AGENT_STORE_BACKEND", "redis")
    monkeypatch.setenv("SAHOOL_AGENT_REDIS_URL", _SECRET_URL)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(S, "_redis_client_or_none", lambda: None)
    with caplog.at_level(logging.WARNING, logger="ai_agronomist.agent_stores"):
        S.build_approval_store()
    (line,) = _selection_lines(caplog)
    assert line.getMessage() == (
        "agent approval store selected: backend=memory requested=redis production=False"
    )
    assert "s3cret" not in caplog.text and "redis.internal" not in caplog.text


def test_redis_selected_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("SAHOOL_AGENT_STORE_BACKEND", "redis")
    monkeypatch.setenv("SAHOOL_ENV", "production")

    class _Client:
        pass

    monkeypatch.setattr(S, "_redis_client_or_none", lambda: _Client())
    with caplog.at_level(logging.WARNING, logger="ai_agronomist.agent_stores"):
        store = S.build_audit_store()
    assert isinstance(store, S.RedisAuditStore)
    (line,) = _selection_lines(caplog)
    assert line.getMessage() == (
        "agent audit store selected: backend=redis requested=redis production=True"
    )
