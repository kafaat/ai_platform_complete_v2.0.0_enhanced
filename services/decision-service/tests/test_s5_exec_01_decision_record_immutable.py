from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_decision_record_is_immutable_replay_not_upsert():
    src = (ROOT / "services/decision-service/persistence.py").read_text()
    start = src.index("async def persist_decision_record(")
    end = src.index("async def persist_dispatch_decision", start)
    body = src[start:end]
    assert "ON CONFLICT (decision_id) DO NOTHING" in body
    assert "DO UPDATE SET" not in body
    assert "RETURNING decision_id" in body
    assert "if replayed:" in body
    assert "decision_id collision belongs to another tenant" in body
    assert "if replayed:" in body and "else:\n                await emit_outbox_event" in body
