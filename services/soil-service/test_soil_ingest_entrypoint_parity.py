"""تكافؤُ أبواب الابتلاع — `INGEST-ENTRYPOINT-PARITY` (مراجعة `b9c5aceb`).

**العطلُ المقيس:** `/v1/fields/{id}/soil/evidence` كان يرفض `true` بـ422 بينما
`/v1/soil/observations` يقبل القيمةَ نفسَها بـ201 ويُمرّرها إلى الحفظ؛ وبابٌ ثالث
`/v1/soil/ingest` يُحوِّل `true` إلى `1.0` في المخطّط قبل أن يبلغ العقد. الحارسُ
صار في **العقد** (`SoilObservation`) فيبلغه كلُّ باب، والمخطّطُ الثالث يرفض `bool` قبل
التحويل.

HTTP حقيقيّ على `APIRouter` وPydantic؛ المصادقةُ والمستأجرُ والتخزينُ مُستبدَلة
بمُثبِّتات — لا PostgreSQL حيّ. وصولُ القيمة إلى دالّة الحفظ هو المقياس.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (HERE, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

pytestmark = pytest.mark.unit

_TENANT = "11111111-1111-1111-1111-111111111111"
#: المستأجرُ يُحقَن عبر الترويسة الموثوقة كما تفعل البوّابة — لا عبر ContextVar لا يعبر خيطَ العميل.
_HEADERS = {"X-Tenant-Id": _TENANT, "X-Agent-Token": "review-agent-token"}


@pytest.fixture(scope="module")
def loaded_main():
    """يُحمَّل مرّةً للوحدة: الراوترات تلتقط كائنَ `main` عند أوّل استيراد، فتحميلٌ لكلّ
    اختبارٍ يجعل الرقعَ تقع على كائنٍ غيرِ الذي تنظر إليه الراوترات (قِيس: 503 توكن)."""
    os.environ["SAHOOL_AGENT_TOKEN"] = "review-agent-token"
    spec = importlib.util.spec_from_file_location("main", HERE / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main
    assert spec.loader is not None
    spec.loader.exec_module(main)
    return main


@pytest.fixture
def service(monkeypatch, loaded_main):
    import soil_store

    main = loaded_main
    writes: list[object] = []

    async def _persist(pool, observation):
        writes.append(observation.value)
        return True

    class _Snapshot:
        profile_id = "prof_stub"
        profile_hash = "hash_stub"

    async def _rebuild(pool, *, tenant_id, field_id):
        return _Snapshot()

    async def _field_ok(field_id):
        return None

    monkeypatch.setattr(main, "_require_field_tenant", _field_ok)
    monkeypatch.setattr(main, "_pool", object())
    monkeypatch.setattr(soil_store, "persist_observation", _persist)
    monkeypatch.setattr(soil_store, "rebuild_snapshot_locked", _rebuild)
    return main, writes


def _direct_body(value):
    return {
        "tenant_id": _TENANT,
        "field_id": "review-field",
        "property": "soil_moisture",
        "value": value,
        "unit": "vwc_pct",
        "observed_at": datetime(2026, 9, 6, 8, tzinfo=UTC).isoformat(),
        "source_type": "sensor",
        "idempotency_key": f"k-{value!r}",
    }


@pytest.mark.parametrize("bad", [True, False, "NaN", "Infinity", "-Infinity"])
def test_every_door_rejects_a_non_measurement_before_it_reaches_storage(service, bad):
    main, writes = service
    client = TestClient(main.app, headers=_HEADERS)
    batch = client.post(
        "/v1/fields/review-field/soil/evidence",
        json={"source_type": "sensor", "source_id": "dev_1", "properties": {"soil_moisture": bad}},
    )
    direct = client.post("/v1/soil/observations", json=_direct_body(bad))
    assert batch.status_code == 422, batch.text
    assert direct.status_code == 422, direct.text
    assert writes == []


@pytest.mark.parametrize("good", [0.0, 1.0, 23.5])
def test_numeric_controls_pass_both_doors_and_reach_storage(service, good):
    main, writes = service
    client = TestClient(main.app, headers=_HEADERS)
    batch = client.post(
        "/v1/fields/review-field/soil/evidence",
        json={"source_type": "sensor", "source_id": "dev_1", "properties": {"soil_moisture": good}},
    )
    direct = client.post("/v1/soil/observations", json=_direct_body(good))
    assert batch.status_code == 201, batch.text
    assert direct.status_code == 201, direct.text
    assert writes == [good, good]


def test_a_boolean_on_another_property_is_still_legitimate(service):
    main, writes = service
    client = TestClient(main.app, headers=_HEADERS)
    body = {**_direct_body(True), "property": "salinity_flag", "unit": None}
    direct = client.post("/v1/soil/observations", json=body)
    assert direct.status_code == 201, direct.text
    assert writes == [True]


def test_the_third_door_does_not_coerce_true_into_one_percent(service):
    """`SoilReading.moisture_pct: float` كان يقبل `true` كـ`1.0` قبل أن يبلغ العقد."""
    main, writes = service
    client = TestClient(main.app, headers=_HEADERS)
    response = client.post(
        "/v1/soil/ingest",
        json={"field_id": "review-field", "sensor_id": "s1", "moisture_pct": True},
    )
    assert response.status_code == 422, response.text
    assert writes == []


def test_a_sensor_reading_without_a_quality_declaration_never_seeds_from_any_door(service):
    """مراجعة `703607bf`: الافتراضُ `accepted` كان يجعل الغيابَ أهليّةً عبر الباب المباشر.

    من الطلب حتّى الوصلة: الكائنُ الذي يبلغ الحفظَ يُسقَط إلى القارئ ثمّ الوصلة كما يفعل
    `_latest_soil_moisture`، ويجب ألّا يهيّئ التوأمَ من أيّ باب.
    """
    platform = ROOT / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    import soil_store
    from api.soil_telemetry import pick_latest_soil_moisture
    from api.water_twin_seed import join_sensor_with_ledger_seed, sensor_depletion_mm

    main, _writes = service
    stored: list[object] = []

    async def _capture(pool, observation):
        stored.append(observation)
        return True

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(soil_store, "persist_observation", _capture)
        client = TestClient(main.app, headers=_HEADERS)
        body = _direct_body(25.0)
        assert "quality_status" not in body
        assert client.post("/v1/soil/observations", json=body).status_code == 201
        assert (
            client.post(
                "/v1/fields/review-field/soil/evidence",
                json={
                    "source_type": "sensor",
                    "source_id": "dev_1",
                    "properties": {"soil_moisture": 25.0},
                },
            ).status_code
            == 201
        )
    assert len(stored) == 2
    for observation in stored:
        assert observation.quality_status.value == "uncalibrated", observation
        reading = pick_latest_soil_moisture(
            [
                {
                    "value": observation.value,
                    "unit": observation.unit,
                    "recorded_at": observation.observed_at,
                    "device_id": observation.source_id,
                    "observation_id": observation.observation_id,
                    "quality_status": observation.quality_status.value,
                    "calibration_id": observation.calibration_id,
                    "confidence": observation.confidence,
                }
            ]
        )
        depletion, _limit = sensor_depletion_mm(
            value_pct=reading.value_pct,
            unit_kind=reading.unit_kind,
            taw_mm=100.0,
            root_depth_m=0.6,
            theta_fc=0.32,
        )
        join = join_sensor_with_ledger_seed(
            ledger_depletion_mm=None,
            ledger_source="unavailable",
            sensor=reading.as_dict(),
            sensor_depletion=depletion,
            sensor_limitation=None,
            sensor_age_s=300.0,
            max_reading_age_s=4 * 3600,
            taw_mm=100.0,
        )
        assert join["depletion_mm"] is None and join["source"] == "unavailable"
        assert join["sensor"]["seed_eligible"] is False
        assert "soil_moisture_sensor_quality_not_seed_eligible:uncalibrated" in join["limitations"]


def test_an_explicit_accepted_declaration_still_governs(service):
    """الضابطُ المضادّ: القبولُ الصريح يعمل وفق السياسة — الحسمُ يمسّ الغيابَ وحدَه."""
    import soil_store

    main, _writes = service
    stored: list[object] = []

    async def _capture(pool, observation):
        stored.append(observation)
        return True

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(soil_store, "persist_observation", _capture)
        client = TestClient(main.app, headers=_HEADERS)
        body = {**_direct_body(25.0), "quality_status": "accepted", "idempotency_key": "k-explicit"}
        assert client.post("/v1/soil/observations", json=body).status_code == 201
    assert stored[0].quality_status.value == "accepted"
