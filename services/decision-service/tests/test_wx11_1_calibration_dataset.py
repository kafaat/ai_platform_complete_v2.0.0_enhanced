from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()
CLIENT = (ROOT / "services/sahool-platform/api/decision_service_client.py").read_text()


def test_calibration_dataset_is_authoritative_read_only_boundary():
    assert '@app.get("/v1/learning/calibration-dataset")' in MAIN
    assert "if not sor_enabled()" in MAIN
    assert "build_calibration_dataset" in MAIN
    assert '"read_only": True' in PERSISTENCE
    assert "weighted_success_rate" in PERSISTENCE


def test_dataset_uses_verified_attribution_lineage_only():
    for token in (
        "decision_learning_attributions",
        "outcome_record",
        "decision_record",
        "la.learning_state='attributed'",
        "verified_success",
        "verified_failure",
    ):
        assert token in PERSISTENCE


def test_bff_proves_authoritative_dataset():
    assert "/api/v1/learning/calibration-dataset" in ROUTER
    assert "Permission.DECISION_LEARNING_ATTRIBUTE" in ROUTER
    assert "did not prove an authoritative calibration dataset" in ROUTER
    assert "async def get_calibration_dataset" in CLIENT
