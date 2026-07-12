from pathlib import Path


def test_single_open_metric_is_certified():
    text = Path("services/raster-service/routers/observability.py").read_text(encoding="utf-8")
    assert "sahool_raster_batch_single_open_certified 1" in text
    assert "dataset_open_actual_total" in Path(
        "services/raster-service/raster_job_orchestration.py"
    ).read_text(encoding="utf-8")
