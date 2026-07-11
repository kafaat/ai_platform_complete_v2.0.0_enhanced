import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agronomic_context as ac

NOW = datetime.now(UTC).isoformat()


def _context():
    return {
        "decision_at": NOW,
        "field_id": "f1",
        "season_id": "s1",
        "crop_id": "wheat",
        "cultivar_id": "cv1",
        "growth_stage": "heading",
        "soil_profile": {"profile_id": "soil1", "data_available_at": NOW},
        "irrigation_profile": {"profile_id": "irr1", "season_applied_mm": 120},
        "weather_snapshot": {"snapshot_id": "wx1", "data_available_at": NOW},
        "climate_profile": {"profile_id": "cl1"},
        "water_quality_snapshot": {"snapshot_id": "wq1", "data_available_at": NOW},
        "vegetation_snapshot": {
            "snapshot_hash": "vhash",
            "data_available_at": NOW,
            "quality_gate": {"executable": True},
            "indices": {"ndvi": {"value": 0.72, "estimated": False}},
        },
        "history_snapshot": {
            "snapshot_hash": "hhash",
            "data_available_at": NOW,
            "window_days": 365,
        },
        "feature_manifest": {"manifest_id": "fm1", "version": "1", "features": ["ndvi", "et0"]},
    }


def test_complete_context_is_accepted():
    out = ac.validate_context(_context(), strict=True)
    assert out["complete"] is True
    assert out["contract_version"] == "agronomic-context.v2"


def test_estimated_vegetation_blocks_execution():
    c = _context()
    c["vegetation_snapshot"]["quality_gate"]["executable"] = False
    assert ac.validate_context(c, strict=True)["complete"] is False


def test_future_data_is_rejected():
    c = _context()
    c["weather_snapshot"]["data_available_at"] = "2999-01-01T00:00:00+00:00"
    out = ac.validate_context(c, strict=True)
    assert out["temporal_integrity"] is False
    assert "weather_snapshot.future_data" in out["temporal_issues"]


def test_irrigation_and_history_are_wired_to_management():
    _, _, _, m = ac.normalized_engine_inputs(_context())
    assert m["irrigation_mm"] == 120
    assert m["history_snapshot"]["snapshot_hash"] == "hhash"
