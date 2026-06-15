"""Unit tests: alert delivery layer (channels, severity filter, dedup, honesty)."""

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


_ALERTS = [
    {"severity": "critical", "code": "salinity_critical", "message_ar": "ملوحة"},
    {"severity": "warning", "code": "low_vigor", "message_ar": "حيويّة"},
    {"severity": "info", "code": "ndvi_decline", "message_ar": "ندفي"},
]


@pytest.mark.unit
def test_severity_filter_drops_info():
    ad = _ad()
    res = ad.deliver_alerts(_ALERTS, channels=[ad.LogChannel()], context={"field_id": "f1"})
    assert res["attempted"] == 2  # critical + warning, info filtered
    assert res["filtered_out"] == 1


@pytest.mark.unit
def test_idempotent_dedup():
    ad = _ad()
    seen: set = set()
    ctx = {"field_id": "f1"}
    first = ad.deliver_alerts(_ALERTS, channels=[ad.LogChannel()], context=ctx, seen=seen)
    second = ad.deliver_alerts(_ALERTS, channels=[ad.LogChannel()], context=ctx, seen=seen)
    assert first["attempted"] == 2 and first["skipped_dedup"] == 0
    assert second["attempted"] == 0 and second["skipped_dedup"] == 2  # لا تكرار إزعاج


@pytest.mark.unit
def test_in_app_channel_rows_and_log():
    ad = _ad()
    res = ad.deliver_alerts(
        _ALERTS,
        channels=[ad.LogChannel(), ad.InAppChannel()],
        context={"field_id": "f1", "tenant_id": "t1", "now": "2026-06-10T00:00:00Z"},
    )
    in_app = [c for c in res["channels"] if c["channel"] == "in_app"][0]
    assert in_app["delivered"] == 2 and len(in_app["rows"]) == 2
    assert in_app["rows"][0]["field_id"] == "f1"


@pytest.mark.unit
def test_honesty_no_external_send_without_config():
    ad = _ad()
    # webhook بلا رابط ⇒ لم يُرسَل (note صريحة، لا ادّعاء)
    wh = ad.WebhookChannel("").send(_ALERTS, {"field_id": "f1"})
    assert wh["delivered"] == 0 and "لم يُرسَل" in wh["note"]
    # مزوّد غير مُهيّأ ⇒ no-op صادق
    prov = ad.ProviderChannel("whatsapp", configured=False).send(_ALERTS, {"field_id": "f1"})
    assert prov["delivered"] == 0 and "غير مُهيّأ" in prov["note"]


@pytest.mark.unit
def test_default_channels_and_endpoint_wired():
    ad = _ad()
    names = [c.name for c in ad.build_default_channels()]
    assert "log" in names and "in_app" in names  # دائماً
    # نقطة field-intelligence نُقلت إلى api/routers/field_intelligence.py (تفكيك main،
    # نمط P0) — نبحث في main.py + موجِّهات api/routers معاً (location-agnostic).
    api_dir = os.path.join(ROOT, "services/sahool-platform/api")
    sources = [os.path.join(api_dir, "main.py")]
    routers_dir = os.path.join(api_dir, "routers")
    if os.path.isdir(routers_dir):
        sources += [
            os.path.join(routers_dir, f) for f in os.listdir(routers_dir) if f.endswith(".py")
        ]
    main = "\n".join(open(p, encoding="utf-8").read() for p in sources if os.path.isfile(p))
    assert "from core.alert_delivery import deliver_alerts" in main
    assert "alerts_delivery" in main and "notify" in main
