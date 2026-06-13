"""Stage D — قيمة NDVI الحقيقيّة في الحالة القانونيّة (Canonical Field State).

يثبّت: (أ) recompute_field_state يُرفِق remote_sensing بصدق (available=false حين لا
قيمة، والقيمة حين تتوفّر)؛ (ب) populator أتمتة الصور يستخرج متوسّط NDVI من نتيجة
raster (best-effort) ويفشل بأمان؛ (ج) هجرة v54 في MANIFEST قبل append-only.
دالّات/conn/client وهميّة بلا قاعدة/شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _Conn:
    """conn وهميّ: imagery يعيد NDVI، الباقي None، يسجّل execute."""

    def __init__(self, *, ndvi_mean=None, ndvi_date=None, last_image_date=None):
        self._img = {
            "last_image_date": last_image_date,
            "last_ndvi_mean": ndvi_mean,
            "last_ndvi_date": ndvi_date,
        }
        self.executed = []

    async def fetchrow(self, sql, *a):
        if "imagery_automation_fields" in sql:
            return self._img
        if "FROM field_state" in sql:
            return None
        return None

    async def fetchval(self, sql, *a):
        if "FROM fields" in sql:
            return "t1"
        return None

    async def execute(self, sql, *a):
        self.executed.append((sql, a))


@pytest.mark.asyncio
async def test_remote_sensing_available_when_ndvi_present(core_on_path):
    from datetime import date

    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.62, ndvi_date=date(2026, 6, 10))
    res = await recompute_field_state(conn, "fld_1")
    rs = res["state"]["remote_sensing"]
    assert rs["available"] is True
    assert rs["ndvi_mean"] == 0.62
    assert rs["ndvi_date"] == "2026-06-10"
    assert "sentinel" in rs["source"].lower()


@pytest.mark.asyncio
async def test_remote_sensing_honest_unavailable_when_absent(core_on_path):
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=None)  # لا قيمة محسوبة
    res = await recompute_field_state(conn, "fld_1")
    rs = res["state"]["remote_sensing"]
    assert rs == {"available": False, "ndvi_mean": None, "ndvi_date": None, "source": None}


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, info_payload):
        self._info = info_payload

    async def get(self, url):
        if "/info/" in url:
            return _Resp(200, self._info)
        if "/jobs/" in url:
            return _Resp(200, {"batch_results": {"ndvi": "layer_x"}})
        return _Resp(404, {})


@pytest.mark.asyncio
async def test_collect_ndvi_value_extracts_mean(core_on_path):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()  # pool=None ⇒ _persist_ndvi لا-عمل، نفحص tf فقط
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1])
    client = _FakeClient({"provenance": {"stats": {"mean": 0.62, "std": 0.1}}})
    image = {"datetime": "2026-06-10T08:00:00Z"}
    await ia._collect_ndvi_value(client, tf, image, {"batch_results": {"ndvi": "layer_x"}})
    assert tf.last_ndvi_mean == 0.62
    assert tf.last_ndvi_date == "2026-06-10"


@pytest.mark.asyncio
async def test_collect_ndvi_value_fails_safe_without_layer(core_on_path):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1])
    client = _FakeClient({})  # لن يُستدعى /info لغياب layer
    # لا batch_results ولا last_indicator_job ⇒ تخطٍّ صامت، القيمة تبقى None
    await ia._collect_ndvi_value(client, tf, {"datetime": "2026-06-10"}, {})
    assert tf.last_ndvi_mean is None


def test_v54_migration_in_manifest_before_append_only():
    manifest = os.path.join(ROOT, "migrations", "MANIFEST.txt")
    with open(manifest, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    assert "v54_imagery_ndvi_value.sql" in lines
    assert lines.index("v54_imagery_ndvi_value.sql") < lines.index("v9_append_only_enforcement.sql")
    assert os.path.exists(os.path.join(ROOT, "migrations", "v54_imagery_ndvi_value.sql"))
