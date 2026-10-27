"""حدث «صورة جديدة» يتبع قبول الجودة، بهويّةٍ حتميّة، ولا يُبتلَع فشلُ نشره.

OI-02: كان ``run_analysis`` ينشر حدث القمر الصناعيّ ويعدّ «نجاحاً» **قبل** ``quality_gate``،
ثمّ يُجيب 424 — فيتلقّى المستهلك «صورة جديدة» لمنتجٍ مرفوض ويعدّه المقياس نجاحاً.

EXTRA-6: الحدث بلا هويّة ثابتة (كلّ ``GET /v1/analyze`` يُنتج حدثاً جديداً بتسلسل JetStream
مختلف، فلا يتعرّف المستهلك على التكرار)، وفشل النشر يُبتلَع في تحذير فلا يعرف المُستدعي
أنّ الحدث لم يُسلَّم. لا NATS ولا شبكة هنا: عميل NATS مُسجِّل يُحقَن في ``_nc``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import vegetation_runtime as vr  # noqa: E402

TENANT = "00000000-0000-0000-0000-0000000000a1"
FIELD = "fld_event_admission"


def _bundle(*, quality: float = 0.9, scene: str = "S2B_20261020_T38PNB") -> dict:
    observations = {}
    for name in ("ndvi", "evi", "msavi", "moisture", "msi", "ndwi", "gndvi"):
        observations[name] = {
            "stats": {"mean": 0.61},
            "indicator_product": {
                "source": "raster-service",
                "quality_score": quality,
                "valid_pixel_ratio": 0.93,
                "data_available_at": "2026-10-20T14:00:00Z",
                "provenance": {
                    "scene_id": scene,
                    "acquisition_datetime": "2026-10-20T07:41:00Z",
                    "algorithm_version": "ndvi.v3",
                    "qa_mask_version": "scl.v2",
                },
            },
        }
    return {
        "source": "raster-service",
        "acquisition_dates": ["2026-10-20"],
        "observations": observations,
    }


class _JetStream:
    def __init__(self, fail: bool):
        self.fail = fail
        self.calls: list[dict] = []

    async def publish(self, subject, payload, *args, **kwargs):
        if self.fail:
            raise TimeoutError("no PubAck")
        self.calls.append(
            {"subject": subject, "payload": json.loads(payload), "headers": kwargs.get("headers")}
        )
        return type("PubAck", (), {"duplicate": False, "seq": len(self.calls)})()


class _Nats:
    def __init__(self, fail: bool = False):
        self.js = _JetStream(fail)

    def jetstream(self):
        return self.js


def _install(monkeypatch, bundle: dict, *, fail: bool = False) -> _JetStream:
    async def _field(field_id, tenant_id):
        return {"name": "حقل", "crop": "wheat", "area_ha": 3.0}

    async def _canonical(*args, **kwargs):
        return bundle

    nc = _Nats(fail)
    monkeypatch.setattr(vr, "load_field", _field)
    monkeypatch.setattr(vr, "_canonical_observation_bundle_from_indicators", _canonical)
    monkeypatch.setattr(vr, "VEGETATION_CANONICAL_SHADOW", False)
    monkeypatch.setattr(vr, "VEGETATION_EVIDENCE_PUSH_ENABLED", False)
    monkeypatch.setattr(vr, "VEGETATION_REAL_ONLY", True)
    monkeypatch.setattr(vr, "_nc", nc)
    return nc.js


def _success_count() -> float:
    return vr.ANALYSIS_COUNT.labels(source="raster-service", status="success")._value.get()


@pytest.mark.asyncio
async def test_rejected_quality_emits_no_event_and_no_success_metric(monkeypatch):
    js = _install(monkeypatch, _bundle(quality=0.10))
    before = _success_count()

    with pytest.raises(HTTPException) as exc:
        await vr.run_analysis(FIELD, TENANT, "2026-10-01", "2026-10-27")

    assert exc.value.status_code == 424
    assert js.calls == [], "a quality-rejected product announced a new satellite image"
    assert _success_count() == before, "a 424 analysis was counted as success"


@pytest.mark.asyncio
async def test_admitted_product_event_identity_is_deterministic(monkeypatch):
    js = _install(monkeypatch, _bundle())
    before = _success_count()

    first = await vr.run_analysis(FIELD, TENANT, "2026-10-01", "2026-10-27")
    # إعادة قراءة التحليل نفسه (تحديث الواجهة) — موسمٌ مختلف لا يغيّر هويّة الرصد.
    again = await vr.run_analysis(FIELD, TENANT, "2026-09-01", "2026-10-27", season_id="s-2026")

    assert first["quality_gate"]["executable"] is True
    assert _success_count() == before + 2
    assert len(js.calls) == 2
    ids = [c["payload"].get("event_id") for c in js.calls]
    assert ids[0] and ids[0] == ids[1], "re-reading one observation produced two event identities"
    for call in js.calls:
        assert call["headers"] == {"Nats-Msg-Id": ids[0]}, "no JetStream de-duplication id"
        assert call["payload"]["acquisition_date"] == "2026-10-20"
        assert call["payload"]["scene_id"] == "S2B_20261020_T38PNB"
    assert first["event_publish"] == again["event_publish"]
    assert first["event_publish"]["published"] is True
    assert first["event_publish"]["event_id"] == ids[0]

    _install(monkeypatch, _bundle(scene="S2A_20261025_T38PNB"))
    newer = await vr.run_analysis(FIELD, TENANT, "2026-10-01", "2026-10-27")
    assert newer["event_publish"]["event_id"] != ids[0], "a different scene reused the event id"


@pytest.mark.asyncio
async def test_publish_failure_is_reported_not_swallowed(monkeypatch):
    _install(monkeypatch, _bundle(), fail=True)

    result = await vr.run_analysis(FIELD, TENANT, "2026-10-01", "2026-10-27")

    publish = result["event_publish"]
    assert publish["published"] is False, "a failed publish was reported as delivered"
    assert publish["reason"] == "unreachable:TimeoutError"
    assert publish["event_id"]
