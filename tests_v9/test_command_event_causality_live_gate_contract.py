from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/e2e/command_event_causality_live_gate.sql"


def test_live_gate_uses_fixed_uuids_not_undefined_stubs():
    text = GATE.read_text(encoding="utf-8")
    assert "uuid_generate_v5_stub" not in text
    assert "11111111-1111-5111-8111-111111111111" in text


def test_live_gate_uses_a_legal_command_source():
    text = GATE.read_text(encoding="utf-8")
    assert "'scheduler'" in text
    # commands.source does not permit system; system is valid only for events.source.
    command_insert = text.split("INSERT INTO commands", 1)[1].split(");", 1)[0]
    assert "'system'" not in command_insert


def test_live_gate_proves_fk_dedup_outbox_and_rollback():
    text = GATE.read_text(encoding="utf-8")
    for required in (
        "foreign_key_violation",
        "dedup failed: events %, outbox %",
        "duplicate emit_event should return NULL",
        "ROLLBACK TO SAVEPOINT rollback_probe",
        "event command_id mismatch",
    ):
        assert required in text
