"""Stage D — قيمة NDVI الحقيقيّة في الحالة القانونيّة (Canonical Field State).

يثبّت: (أ) recompute_field_state يُرفِق remote_sensing بصدق؛ (ب) populator أتمتة
الصور يستخرج متوسّط NDVI من نتيجة المهمّة الفرعيّة الحقيقيّة في raster
(GET /jobs/{job_id}_ndvi/result → stats.mean) ويفشل بأمان؛ (ج) v54 في MANIFEST.
يحاكي API raster الفعليّ (نتيجة المهمّة الفرعيّة + valid_pixels)، لا شكلاً مُتخيَّلاً.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _NoopTx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _Conn:
    """conn وهميّ: imagery (NDVI) عبر fetchrow، tenant عبر fetchval، transaction لا-عمل."""

    def __init__(self, *, ndvi_mean=None, ndvi_date=None):
        self._ndvi = {"last_ndvi_mean": ndvi_mean, "last_ndvi_date": ndvi_date}
        self.executed = []

    def transaction(self):
        return _NoopTx()

    async def fetchrow(self, sql, *a):
        if "imagery_automation_fields" in sql:
            return self._ndvi
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


def _patch_job_result(monkeypatch, result_payload):
    """P2 raster facade: ``_collect_ndvi_value`` يقرأ نتيجة المهمّة الفرعيّة عبر
    ``get_job_result`` (واجهة raster) بدل عميل httpx مُمرَّر. نُرقِّع الواجهة كما تستوردها
    الوحدة ونسجّل ``job_id`` المطلوب — النيّة محفوظة: تُقرأ المهمّة الفرعيّة «{job}_ndvi»."""
    from api import imagery_automation as ia_mod

    calls: list[str] = []

    async def _fake_get_job_result(job_id, *, tenant_id=None, timeout_s=10.0):
        calls.append(job_id)
        if job_id.endswith("_ndvi"):
            return result_payload
        return None

    monkeypatch.setattr(ia_mod, "get_job_result", _fake_get_job_result)
    return calls


@pytest.mark.asyncio
async def test_collect_ndvi_value_extracts_mean_from_subjob_result(core_on_path, monkeypatch):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()  # pool=None ⇒ _persist_ndvi لا-عمل، نفحص tf
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1])
    calls = _patch_job_result(
        monkeypatch, {"stats": {"mean": 0.62, "valid_pixels": 1500, "std": 0.1}}
    )
    await ia._collect_ndvi_value(tf, {"datetime": "2026-06-10T08:00:00Z"}, {"job_id": "jb1"})
    assert calls == ["jb1_ndvi"]
    assert tf.last_ndvi_mean == 0.62
    assert tf.last_ndvi_date == "2026-06-10"


@pytest.mark.asyncio
async def test_collect_ndvi_value_skips_when_no_valid_pixels(core_on_path, monkeypatch):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1])
    # valid_pixels=0 ⇒ المتوسّط بلا معنى ⇒ لا حفظ (صدق)
    _patch_job_result(monkeypatch, {"stats": {"mean": 0.0, "valid_pixels": 0}})
    await ia._collect_ndvi_value(tf, {"datetime": "2026-06-10"}, {"job_id": "jb1"})
    assert tf.last_ndvi_mean is None


@pytest.mark.asyncio
async def test_collect_ndvi_value_fails_safe_without_job(core_on_path, monkeypatch):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1])
    calls = _patch_job_result(monkeypatch, {})
    # لا job_id ولا last_indicator_job ⇒ تخطٍّ صامت، لا نداء
    await ia._collect_ndvi_value(tf, {"datetime": "2026-06-10"}, {})
    assert tf.last_ndvi_mean is None
    assert calls == []


def test_v54_migration_in_manifest_before_append_only():
    manifest = os.path.join(ROOT, "migrations", "MANIFEST.txt")
    with open(manifest, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    assert "v54_imagery_ndvi_value.sql" in lines
    assert lines.index("v54_imagery_ndvi_value.sql") < lines.index("v9_append_only_enforcement.sql")
    assert os.path.exists(os.path.join(ROOT, "migrations", "v54_imagery_ndvi_value.sql"))
