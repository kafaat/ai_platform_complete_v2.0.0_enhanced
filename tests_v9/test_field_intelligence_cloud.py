"""Unit tests: live wiring of cloud_cover → fuse_health (field-intelligence).

يحرس إصلاح ثغرتي wiring مؤكَّدتين بقراءة الكود:
  • Gap 1: sensing_adapter كان ينادي /indices غير موجودة (تُضاف النقطة).
  • Gap 2: cloud_cover لم يكن يصل أبداً (cloud=0 دائماً) ⇒ تحويل الوزن للرادار
    في fuse_health لا يُفعَّل. الآن normalize_signals يولّد إشارة cloud_cover،
    sensing_adapter يمرّرها، وتظهر في الحالة الموحّدة (crop_vigor_notes).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


def _load(modname: str, relpath: str):
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def _coordinator():
    return _load("fic", "services/sahool-platform/core/field_intelligence_coordinator.py")


@pytest.mark.unit
def test_normalize_emits_cloud_signal_only_when_present():
    fic = _coordinator()
    # مع غطاء سحب
    res = fic.CollectorResult(raw={"sensing": {"ndvi": 0.6, "cloud_cover": 60.0}})
    sigs = fic.normalize_signals(res)
    cloud = [s for s in sigs if s.source == "cloud_cover"]
    assert len(cloud) == 1 and cloud[0].value == 60.0
    # بلا غطاء سحب ⇒ لا إشارة (لا اختراع)
    res2 = fic.CollectorResult(raw={"sensing": {"ndvi": 0.6}})
    assert not [s for s in fic.normalize_signals(res2) if s.source == "cloud_cover"]


@pytest.mark.unit
def test_cloud_reaches_fuse_health_via_compose_state():
    """end-to-end: إشارة cloud_cover عالية ⇒ ملاحظة تحويل الوزن للرادار في الحالة."""
    fic = _coordinator()
    ase = _load("ase", "services/sahool-platform/core/agronomic_state_engine.py")
    # بلا observed_at ⇒ normalize_signals يستخدم now (tz-aware) فلا تختلط naive/aware
    collected = fic.CollectorResult(
        raw={"sensing": {"ndvi": 0.6, "ndre": 0.4, "cloud_cover": 60.0}}
    )
    signals = fic.normalize_signals(collected)
    state = ase.compose_field_state("field-x", signals)
    truths = state.operational_truths
    assert truths.get("cloud_cover_pct") == 60.0, "cloud لم يصل لـfuse_health (cloud=0 ثابت)"
    notes = " ".join(truths.get("crop_vigor_notes", []))
    assert "SAR" in notes or "رادار" in notes, f"تحويل الوزن للرادار لم يُفعَّل: {notes!r}"


@pytest.mark.unit
def test_sar_rvi_dominates_under_cloud():
    """مقاومة السحاب الكاملة: صحوٌ ⇒ optical مهيمن؛ سحابٌ ⇒ SAR(rvi) مهيمن."""
    fic = _coordinator()
    ase = _load("ase", "services/sahool-platform/core/agronomic_state_engine.py")
    clear = fic.CollectorResult(raw={"sensing": {"ndvi": 0.6, "ndre": 0.4, "rvi": 0.55}})
    s_clear = ase.compose_field_state("f", fic.normalize_signals(clear))
    assert s_clear.operational_truths.get("crop_vigor_dominant") == "optical"
    cloudy = fic.CollectorResult(
        raw={"sensing": {"ndvi": 0.6, "ndre": 0.4, "rvi": 0.55, "cloud_cover": 60.0}}
    )
    s_cloudy = ase.compose_field_state("f", fic.normalize_signals(cloudy))
    assert s_cloudy.operational_truths.get("crop_vigor_dominant") == "sar"


@pytest.mark.unit
def test_sensing_adapter_passes_cloud_cover(monkeypatch):
    adapters = _load("fia", "services/sahool-platform/core/field_intelligence_adapters.py")
    # **kw يتقبّل agent_token الجديد (توكن الخدمة لـ/indices) دون تغيير نيّة الاختبار.
    monkeypatch.setattr(
        adapters, "_get_json", lambda url, params=None, **kw: {"ndvi": 0.55, "cloud_cover": 42.0}
    )

    class _Req:
        field_id, lat, lon = "f1", 15.3, 44.2

    out = adapters.sensing_adapter(_Req())
    assert out is not None and out["cloud_cover"] == 42.0 and out["ndvi"] == 0.55


@pytest.mark.unit
def test_indices_endpoint_wired_and_guarded():
    from raster_route_source import raster_combined_source

    main = raster_combined_source(ROOT)  # main.py + routers/ (بعد التفكيك)
    _dec = (
        '@router.get("/indices")' if '@router.get("/indices")' in main else '@app.get("/indices")'
    )
    assert _dec in main, "نقطة /indices مفقودة (Gap 1)"
    # محميّة بتوكن الخدمة + صدق (real_data / note)
    seg = main[main.index(_dec) :]
    assert "require_service_token" in seg[:1200], "/indices غير محميّة بتوكن الخدمة"
    assert "real_data" in seg[:1200], "/indices لا يُعلن صدق البيانات"
