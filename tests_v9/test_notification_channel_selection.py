"""Unit tests: احترام تفضيلات المستخدم في اختيار قنوات الإشعار (select_channels_for_user).

نقيّ تماماً (بلا قاعدة/شبكة) — يحمّل core/alert_delivery.py مباشرةً عبر importlib،
بنفس نمط test_alert_delivery.py الموجود.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


def _ad():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(
        "alert_delivery", os.path.join(ROOT, "services/sahool-platform/core/alert_delivery.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_no_prefs_returns_channels_unchanged():
    """بلا تفضيلات (None) ⇒ تُعاد القائمة كما هي حرفيّاً (السلوك القائم، لا انحدار)."""
    ad = _ad()
    chans = ad.build_default_channels()
    out = ad.select_channels_for_user(None, "critical", chans)
    assert out is chans  # نفس الكائن — لا نسخ ولا ترشيح


@pytest.mark.unit
def test_empty_prefs_returns_channels_unchanged():
    """تفضيلات فارغة (dict فارغ) تُعامَل كغياب تفضيلات ⇒ لا ترشيح."""
    ad = _ad()
    chans = ad.build_default_channels()
    out = ad.select_channels_for_user({}, "warning", chans)
    assert out is chans


@pytest.mark.unit
def test_always_on_channels_always_pass():
    """log/in_app تشغيليّتان دائمتان — تمرّان حتى مع تفضيلات تُعطّل كلّ شيء."""
    ad = _ad()
    chans = [ad.LogChannel(), ad.InAppChannel()]
    prefs = {"email_enabled": False, "sms_enabled": False, "whatsapp_enabled": False}
    names = [c.name for c in ad.select_channels_for_user(prefs, "critical", chans)]
    assert names == ["log", "in_app"]


@pytest.mark.unit
def test_disabled_external_channel_filtered_out():
    """قناة خارجيّة غير مُفعَّلة لدى المستخدم تُسقَط؛ المُفعَّلة تبقى."""
    ad = _ad()
    chans = [
        ad.LogChannel(),
        ad.ProviderChannel("whatsapp", configured=True),
        ad.ProviderChannel("sms", configured=True),
    ]
    prefs = {"whatsapp_enabled": True, "sms_enabled": False}
    names = [c.name for c in ad.select_channels_for_user(prefs, "critical", chans)]
    assert "whatsapp" in names  # مُفعَّلة
    assert "sms" not in names  # غير مُفعَّلة
    assert "log" in names  # تشغيليّة دائمة


@pytest.mark.unit
def test_min_severity_gates_external_channels():
    """خطورة أدنى من حدّ المستخدم ⇒ لا قنوات خارجيّة (تبقى log/in_app فقط)."""
    ad = _ad()
    chans = [ad.LogChannel(), ad.ProviderChannel("whatsapp", configured=True)]
    prefs = {"whatsapp_enabled": True, "min_severity": "critical"}
    # warning < critical ⇒ تُرشَّح whatsapp
    names_warn = [c.name for c in ad.select_channels_for_user(prefs, "warning", chans)]
    assert "whatsapp" not in names_warn and "log" in names_warn
    # critical ≥ critical ⇒ تمرّ whatsapp
    names_crit = [c.name for c in ad.select_channels_for_user(prefs, "critical", chans)]
    assert "whatsapp" in names_crit


@pytest.mark.unit
def test_unknown_channel_not_silently_dropped():
    """قناة خارج خريطة التفضيلات لا تُسقَط صامتاً (لا ابتلاع)."""
    ad = _ad()

    class _Custom:
        name = "telegram"

        def send(self, alerts, ctx):  # pragma: no cover - بنية فقط
            return {}

    chans = [_Custom()]
    prefs = {"whatsapp_enabled": False}
    names = [c.name for c in ad.select_channels_for_user(prefs, "info", chans)]
    assert names == ["telegram"]


@pytest.mark.unit
def test_deliver_alerts_default_unchanged_without_prefs():
    """deliver_alerts بلا prefs = السلوك القائم تماماً (كلّ القنوات تُستدعى)."""
    ad = _ad()
    alerts = [{"severity": "critical", "code": "salinity", "message_ar": "ملوحة"}]
    res = ad.deliver_alerts(
        alerts,
        channels=[ad.LogChannel(), ad.ProviderChannel("whatsapp", configured=True)],
        context={"field_id": "f1"},
    )
    delivered_channels = {c["channel"] for c in res["channels"]}
    assert "log" in delivered_channels and "whatsapp" in delivered_channels


@pytest.mark.unit
def test_deliver_alerts_respects_prefs_when_passed():
    """deliver_alerts مع prefs ⇒ تُرشَّح القنوات (whatsapp مُعطَّلة تُسقَط)."""
    ad = _ad()
    alerts = [{"severity": "critical", "code": "salinity", "message_ar": "ملوحة"}]
    res = ad.deliver_alerts(
        alerts,
        channels=[ad.LogChannel(), ad.ProviderChannel("whatsapp", configured=True)],
        context={"field_id": "f1"},
        prefs={"whatsapp_enabled": False},
    )
    delivered_channels = {c["channel"] for c in res["channels"]}
    assert "log" in delivered_channels  # تشغيليّة دائمة
    assert "whatsapp" not in delivered_channels  # مُعطَّلة لدى المستخدم


@pytest.mark.unit
def test_deliver_alerts_top_severity_not_muted_by_lighter():
    """الترشيح بأعلى خطورة في الدُّفعة — critical لا يُسكَت بوجود warning أخفّ."""
    ad = _ad()
    alerts = [
        {"severity": "warning", "code": "low_vigor", "message_ar": "حيويّة"},
        {"severity": "critical", "code": "salinity", "message_ar": "ملوحة"},
    ]
    # حدّ المستخدم critical: لو رُشّح بأخفّ (warning) لسقطت whatsapp؛ بأعلى (critical) تمرّ.
    res = ad.deliver_alerts(
        alerts,
        channels=[ad.ProviderChannel("whatsapp", configured=True)],
        context={"field_id": "f1"},
        prefs={"whatsapp_enabled": True, "min_severity": "critical"},
    )
    assert {c["channel"] for c in res["channels"]} == {"whatsapp"}
