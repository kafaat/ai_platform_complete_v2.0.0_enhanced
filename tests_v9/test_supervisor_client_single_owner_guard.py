"""The generic hook registry must not resurrect the dead duplicate supervisor client."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_no_duplicate_supervisor_client_in_generic_hooks() -> None:
    src = (ROOT / "frontend/src/hooks/useApi.ts").read_text(encoding="utf-8")
    assert "useAgentQuery" not in src
    assert "useFarmOptimize" not in src
    assert "kongApi.post('/api/agent/query'" not in src
    assert "kongApi.post('/api/agent/optimize'" not in src
