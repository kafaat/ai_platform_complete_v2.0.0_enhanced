from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_basic_outcome_replay_does_not_mutate_or_emit_second_event():
    src = (ROOT / "services/decision-service/persistence.py").read_text()
    s = src.index("async def persist_outcome_record(")
    e = src.index("def _recommendation_outcome_request_hash", s)
    b = src[s:e]
    assert "ON CONFLICT (tenant_id, idempotency_key)" in b
    assert "DO NOTHING" in b
    assert "DO UPDATE SET" not in b
    assert "RETURNING outcome_id" in b
    assert 'canonical_outcome_id = existing["outcome_id"]' in b
    assert "else:\n                await emit_outbox_event" in b
    assert '"replayed": replayed' in b
