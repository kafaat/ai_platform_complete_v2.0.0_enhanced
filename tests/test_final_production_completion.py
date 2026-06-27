from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/sahool-platform"))

from core.daily_agronomist_full import BriefSignal, FieldBriefInput, build_farm_brief, build_field_brief, build_zone_brief  # noqa: E402
from core.harvest_feedback import HarvestOutcome, RecommendationPrediction, evaluate_harvest_feedback  # noqa: E402
from core.isoxml_vrt import ISOXMLTask, MachineProfile, ProductProfile, VRTZone, export_taskdata_xml, validate_machine_task  # noqa: E402
from core.mlops_runtime import JsonModelRegistry, RuntimeModelCard, detect_metric_drift, should_promote  # noqa: E402


POLYGON = {"type": "Polygon", "coordinates": [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.1], [44.0, 15.0]]]}


def test_isoxml_export_requires_real_machine_capability_and_approved_recommendation():
    task = ISOXMLTask(
        task_id="fert-rx-1",
        field_id="F-1",
        crop="wheat",
        prescription_kind="fertilizer",
        approved_recommendation_id="REC-APPROVED-1",
        product=ProductProfile("Urea", "fertilizer", "kg/ha"),
        machine=MachineProfile("John Deere", "Gen4", "4.3"),
        zones=[VRTZone("low-zone", 75.0, "kg/ha", POLYGON)],
    )
    report = validate_machine_task(task)
    assert report["ready"] is True
    xml = export_taskdata_xml(task)
    root = ET.fromstring(xml)
    assert root.tag == "ISO11783_TaskData"
    assert root.find("TSK") is not None
    assert root.find("TSK/TZN/VPN").attrib["C"] == "kg/ha"


def test_isoxml_fails_closed_for_unsupported_unit_or_missing_approval():
    try:
        ISOXMLTask(
            task_id="bad",
            field_id="F-1",
            crop="wheat",
            prescription_kind="irrigation",
            approved_recommendation_id="",
            product=ProductProfile("Water", "irrigation", "m3/ha"),
            machine=MachineProfile("John Deere", "Gen4", "4.3"),
            zones=[VRTZone("z", 120.0, "m3/ha", POLYGON)],
        )
    except ValueError as exc:
        assert "approved recommendation" in str(exc) or "does not support unit" in str(exc)
    else:
        raise AssertionError("ISOXML export accepted unsafe task")


def test_daily_agronomist_builds_farm_field_and_zone_briefs_without_deciding_from_rag():
    field = build_field_brief(
        FieldBriefInput(
            field_id="F-1",
            crop="wheat",
            field_state={"lifecycle": "READY", "confidence": "medium"},
            signals=[BriefSignal("irrigation", "action", "نفّذ ريّة خفيفة خلال 24 ساعة", evidence="weather+soil")],
            rag_annotations=["manual says wheat needs nitrogen"],
        )
    )
    assert field.source == "canonical_field_state"
    assert any("ري" in item for item in field.actions_today_ar)
    assert any("معرفة مرجعية" in item for item in field.overnight_changes_ar)

    zone = build_zone_brief("F-1", "Z-low", {"lifecycle": "BLOCKED", "confidence": "low"}, [])
    assert zone.scope == "zone"
    assert zone.blocked_ar

    farm = build_farm_brief("Farm-1", [field, zone])
    assert farm.scope == "farm"
    assert farm.blocked_ar


def test_harvest_feedback_uses_field_state_hash_and_keeps_calibration_locked_until_enough_harvests():
    preds = [
        RecommendationPrediction("R1", "F1", "2026", "state-a", 5.0),
        RecommendationPrediction("R2", "F1", "2026", "state-old", 9.0),
    ]
    outcomes = [HarvestOutcome("F1", "2026", "state-a", 4.0, 10.0)]
    evaluation = evaluate_harvest_feedback(preds, outcomes, min_calibration_pairs=2)
    assert evaluation.n_pairs == 1
    assert evaluation.rmse == 1.0
    assert evaluation.calibration_ready is False
    assert "zone_factor=null" in evaluation.note_ar


def test_harvest_feedback_enables_calibration_only_after_real_pairs():
    preds = [RecommendationPrediction(f"R{i}", f"F{i}", "2026", "s", 4.0) for i in range(3)]
    outcomes = [HarvestOutcome(f"F{i}", "2026", "s", 4.0 + i * 0.1, 1.0) for i in range(3)]
    evaluation = evaluate_harvest_feedback(preds, outcomes, min_calibration_pairs=3)
    assert evaluation.n_pairs == 3
    assert evaluation.calibration_ready is True
    assert evaluation.r2 is not None


def test_json_mlops_registry_persists_champion_and_challenger_policy():
    with tempfile.TemporaryDirectory() as tmp:
        reg = JsonModelRegistry(Path(tmp) / "models.json")
        champion = RuntimeModelCard("yield-xgb", "1", "yield", "champion", 80, {"rmse": 1.0}, ("ndvi", "rain"), "2026-06-25")
        candidate = RuntimeModelCard("yield-xgb", "2", "yield", "challenger", 90, {"rmse": 0.9}, ("ndvi", "rain"), "2026-06-25")
        reg.register(champion)
        reg.register(candidate)
        assert reg.champion_for("yield").version == "1"
        assert should_promote(champion, candidate) is True


def test_mlops_rejects_fake_champion_and_detects_drift():
    bad = RuntimeModelCard("m", "1", "yield", "champion", 5, {"rmse": 1.0}, ("ndvi",), "now")
    try:
        bad.validate()
    except ValueError as exc:
        assert ">=30" in str(exc)
    else:
        raise AssertionError("MLOps accepted fake champion")
    drift = detect_metric_drift({"rmse": 1.0, "mape": 0.2}, {"rmse": 1.4, "mape": 0.21}, tolerance=0.2)
    assert drift["drifted"] is True
    assert "rmse" in drift["metrics"]
