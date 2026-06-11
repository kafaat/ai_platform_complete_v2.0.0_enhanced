"""Conditional deferred-capabilities gate (CI-enforced).

كل قدرة مؤجَّلة خاملة افتراضيّاً (لا اختراع) وتُفعَّل فقط عند تحقّق شرطها. هذه
الاختبارات تُثبِت السلوك المشروط: خاملة بلا تزويد، نشطة معه.
"""

from __future__ import annotations

import os
import sys

import pytest

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")


@pytest.fixture(scope="module")
def caps():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    from core import capabilities

    return capabilities


@pytest.mark.unit
def test_all_dormant_by_default(caps, monkeypatch):
    # بيئة نظيفة من كلّ شروط التفعيل ⇒ كلّ القدرات خاملة (لا تشغيل وهميّ)
    for k in (
        "FCM_SERVER_KEY",
        "FCM_CREDENTIALS_JSON",
        "PEST_MODEL_PATH",
        "YIELD_MODEL_PATH",
        "ALERT_SLACK_WEBHOOK",
        "ALERT_SMTP_HOST",
        "ALERT_TELEGRAM_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)
    rep = caps.capabilities_report()
    assert rep["active_count"] == 0
    assert rep["dormant_count"] == len(rep["capabilities"]) >= 4
    assert all(c["status"] == "dormant" for c in rep["capabilities"])
    # كلّ قدرة خاملة تحمل تعليمات تفعيل + وصف السلوك الخامل الصادق
    for c in rep["capabilities"]:
        assert c["activation_ar"] and c["fallback_ar"]


@pytest.mark.unit
def test_condition_activates_capability(caps, monkeypatch):
    # FCM: يُفعَّل بسرّ
    monkeypatch.setenv("FCM_SERVER_KEY", "secret")
    assert caps.fcm_push_active() is True
    # مستقبِلات التنبيه: أيّ مستقبِل واحد يكفي
    monkeypatch.setenv("ALERT_SLACK_WEBHOOK", "https://hooks.example/x")
    assert caps.alerting_receivers_active() is True


@pytest.mark.unit
def test_ml_requires_real_model_file(caps, monkeypatch, tmp_path):
    # مسار غير موجود ⇒ خامل (لا نموذج مزيّف)
    monkeypatch.setenv("PEST_MODEL_PATH", str(tmp_path / "nope.onnx"))
    assert caps.ml_pest_active() is False
    # ملفّ حقيقيّ موجود ⇒ نشط
    real = tmp_path / "model.onnx"
    real.write_bytes(b"\x00")
    monkeypatch.setenv("PEST_MODEL_PATH", str(real))
    assert caps.ml_pest_active() is True


@pytest.mark.unit
def test_falsey_values_stay_dormant(caps, monkeypatch):
    monkeypatch.delenv("FCM_CREDENTIALS_JSON", raising=False)
    for val in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv("FCM_SERVER_KEY", val)
        assert caps.fcm_push_active() is False, val


@pytest.mark.unit
def test_weather_forecast_adapter_default_and_optout(monkeypatch):
    """محوّل التوقّع الحيّ: افتراضيّ مُفعَّل (keyless)؛ بلا إحداثيّات أو مع انسحاب
    صريح ⇒ None بلا اختراع (لا نختبر نداء الشبكة هنا)."""
    import sys

    core = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
    if core not in sys.path:
        sys.path.insert(0, core)
    from core.field_intelligence_adapters import weather_forecast_adapter

    class _Req:
        lat = None
        lon = None

    # بلا إحداثيّات ⇒ None (لا نداء)
    assert weather_forecast_adapter(_Req()) is None
    # انسحاب صريح (air-gapped) ⇒ None حتى مع إحداثيّات
    monkeypatch.setenv("WEATHER_LIVE_DISABLED", "1")

    class _ReqXY:
        lat = 15.3
        lon = 44.2

    assert weather_forecast_adapter(_ReqXY()) is None
