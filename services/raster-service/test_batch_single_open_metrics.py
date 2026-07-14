from pathlib import Path

# جذر المستودع مثبَّت على __file__ كي يعمل الفحص من أيّ cwd (بوّابة raster تُشغّل
# pytest من داخل services/raster-service، والمسارات هنا جذر-مستودعيّة).
_ROOT = Path(__file__).resolve().parents[2]


def test_single_open_metric_is_certified():
    text = (_ROOT / "services/raster-service/routers/observability.py").read_text(encoding="utf-8")
    assert "sahool_raster_batch_single_open_certified 1" in text
    assert "dataset_open_actual_total" in (
        _ROOT / "services/raster-service/raster_job_orchestration.py"
    ).read_text(encoding="utf-8")
