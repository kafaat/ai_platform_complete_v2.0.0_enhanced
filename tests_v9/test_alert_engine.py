"""Unit tests: proactive alert engine — operational_truths + change/FVC.

يحرس: تصنيف التنبيهات، ربط change_detection/FVC، وكبح الإنذار الكاذب (ثقة
منخفضة لا تُطلق «حرج»؛ تغطية سحابيّة منخفضة لا تُطلق تدهور/تصحّر).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


def _ae():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(
        "alert_engine", os.path.join(ROOT, "services/sahool-platform/core/alert_engine.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _state(truths, confidence="high", contradictions=None):
    return SimpleNamespace(
        operational_truths=truths, confidence=confidence, contradictions=contradictions or []
    )


@pytest.mark.unit
def test_salinity_critical_fires():
    ae = _ae()
    alerts = ae.evaluate_alerts(_state({"salinity_class": "critical"}))
    sal = [a for a in alerts if a["code"] == "salinity_critical"]
    assert sal and sal[0]["severity"] == "critical"


@pytest.mark.unit
def test_low_confidence_suppresses_critical():
    ae = _ae()
    alerts = ae.evaluate_alerts(_state({"salinity_risk": 0.9}, confidence="low"))
    sal = [a for a in alerts if a["code"] == "salinity_critical"][0]
    assert sal["severity"] == "warning"  # خُفِّض من حرج
    assert "ثقة منخفضة" in sal["message_ar"]


@pytest.mark.unit
def test_change_detection_degradation_and_cloud_suppression():
    ae = _ae()
    healthy = _state({"crop_vigor": 0.7})
    change = {"coverage_pct": 90.0, "areas": {"degraded_pct": 30.0, "severe_degraded_pct": 12.0}}
    alerts = ae.evaluate_alerts(healthy, change_result=change)
    deg = [a for a in alerts if a["code"] == "spatial_degradation"]
    assert deg and deg[0]["severity"] == "critical"  # severe>=10 ⇒ حرج
    # تغطية منخفضة (سحاب) ⇒ يُكبَح
    cloudy = {"coverage_pct": 30.0, "areas": {"degraded_pct": 30.0, "severe_degraded_pct": 12.0}}
    assert not [
        a
        for a in ae.evaluate_alerts(healthy, change_result=cloudy)
        if a["code"] == "spatial_degradation"
    ]


@pytest.mark.unit
def test_fvc_desertification_and_cloud_suppression():
    ae = _ae()
    s = _state({"crop_vigor": 0.7})
    fvc = {"coverage_pct": 95.0, "areas": {"desertification_pct": 55.0}}
    assert [a for a in ae.evaluate_alerts(s, fvc_result=fvc) if a["code"] == "desertification"]
    low_cov = {"coverage_pct": 20.0, "areas": {"desertification_pct": 55.0}}
    assert not [
        a for a in ae.evaluate_alerts(s, fvc_result=low_cov) if a["code"] == "desertification"
    ]


@pytest.mark.unit
def test_healthy_field_no_alerts_and_summary():
    ae = _ae()
    alerts = ae.evaluate_alerts(_state({"crop_vigor": 0.7, "salinity_class": "low"}))
    assert alerts == []
    summ = ae.summarize_alerts(alerts)
    assert summ["total"] == 0 and summ["has_critical"] is False and summ["top_priority"] is None


@pytest.mark.unit
def test_summary_ranks_top_priority():
    ae = _ae()
    alerts = ae.evaluate_alerts(
        _state({"salinity_class": "critical", "crop_vigor": 0.3, "ndvi_trend": "decreasing"})
    )
    summ = ae.summarize_alerts(alerts)
    assert summ["has_critical"] is True
    assert summ["top_priority"]["severity"] == "critical"
    assert summ["by_severity"]["critical"] >= 1


@pytest.mark.unit
def test_engine_wired_into_endpoint():
    main = open(os.path.join(ROOT, "services/sahool-platform/api/main.py"), encoding="utf-8").read()
    assert "from core.alert_engine import evaluate_alerts" in main
    assert '"alerts": alerts' in main and '"alerts_summary"' in main
