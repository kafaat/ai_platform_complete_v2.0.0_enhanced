import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
for path in (str(SERVICE), str(REPO)):
    if path not in sys.path:
        sys.path.insert(0, path)
spec = importlib.util.spec_from_file_location(
    "agriai_agronomic_context_contract", SERVICE / "agronomic_context.py"
)
ac = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ac
spec.loader.exec_module(ac)

NOW = datetime.now(UTC).isoformat()


def _context():
    return {
        "decision_at": NOW,
        "field_id": "f1",
        "season_id": "s1",
        "crop_id": "wheat",
        "cultivar_id": "cv1",
        "growth_stage": "heading",
        "soil_profile": {
            "contract_version": "soil-profile.v1",
            "profile_id": "soil1",
            "profile_hash": "a" * 64,
            "field_id": "f1",
            "effective_at": NOW,
            "data_available_at": NOW,
            "status": "verified",
            "evidence_level": "lab_verified",
            "layers": [
                {
                    "depth_from_cm": 0,
                    "depth_to_cm": 30,
                    "properties": {
                        "texture": {
                            "value": "sandy_loam",
                            "evidence_class": "measured",
                            "selected_source": "lab",
                            "confidence": 0.9,
                        }
                    },
                }
            ],
            "completeness_score": 0.8,
            "quality_gate": {"passed": True, "executable": True},
            "selection_policy_version": "soil-policy.v1",
            "allowed_use": ["crop_simulation"],
            "model_inputs": {
                "field_capacity": 0.28,
                "wilting_point": 0.12,
                "rootable_depth_cm": 80,
                "bulk_density": 1.35,
            },
        },
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


def test_strict_context_rejects_legacy_soil_dict():
    c = _context()
    c["soil_profile"] = {"profile_id": "legacy", "data_available_at": NOW}
    out = ac.validate_context(c, strict=True)
    assert out["complete"] is False
    assert out["soil_profile_integrity"] is False


def test_strict_engine_inputs_use_canonical_soil_snapshot(monkeypatch):
    monkeypatch.setenv("AGRIAI_STRICT_CONTEXT", "true")
    _, _, soil, _ = ac.normalized_engine_inputs(_context())
    assert soil["soil_profile_id"] == "soil1"
    assert soil["available_water_mm"] == 128.0
    assert soil["soil_profile_hash"] == "a" * 64
