"""مسارُ إدخال الحافّة يكتب نسبَ كلّ كشفٍ ويُعيده في الإيصال (v239) — استدعاءٌ مباشر.

العزلُ بين المستأجرين والقيودُ مقيسةٌ حيّاً في
``tests_v9/test_v239_detection_provenance_live_pg.py``؛ هنا يُقاس **التوصيل**: أنّ
``edge_sync_receive`` يكتب صفّ النسب على اتّصال المعاملة نفسه بعد إدراج النتيجة، وأنّ
كتلةَ نسبٍ مشوَّهة تُرفَض 422 **قبل** فتح أيّ اتّصال.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.edge_models import EdgeSyncRequest
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-0000000002a9"
_USER = UserSchema(user_id="u-edge", tenant_id=_TENANT, role=UserRole.OWNER, name_ar="جهاز")
_SHA = hashlib.sha256(b"pest-bytes").hexdigest()


class _Conn:
    def __init__(self) -> None:
        self.provenance: list[tuple] = []

    async def fetchrow(self, sql, *args):
        assert "INSERT INTO edge_results" in sql
        return {"id": 41}

    async def execute(self, sql, *args):
        assert "INSERT INTO detection_provenance" in sql
        self.provenance.append(args)

    async def fetch(self, sql, *args):
        assert "FROM detection_provenance" in sql and args == (41,)
        return [
            {
                "edge_result_id": a[1],
                "detection_index": a[2],
                "label": a[3],
                "score": a[4],
                "threshold": a[5],
                "model_id": a[6],
                "model_version": a[7],
                "artifact_sha256": a[8],
                "input_sha256": a[9],
                "attestation": a[10],
                "calibrated": a[11],
                "calibration_ref": a[12],
                "tenant_id": a[0],
                "created_at": datetime(2026, 11, 3, tzinfo=UTC),
            }
            for a in self.provenance
        ]


def _wire(monkeypatch) -> _Conn:
    import api.routers.edge as route

    conn = _Conn()

    @contextlib.asynccontextmanager
    async def _tenant_connection(_user):
        yield conn

    async def _field_ok(_conn, _field_id):
        return None

    monkeypatch.setattr(route, "tenant_connection", _tenant_connection)
    monkeypatch.setattr(route, "_assert_field_in_tenant", _field_ok)
    return conn


def _request(provenance) -> EdgeSyncRequest:
    data = {
        "field_id": "field-1",
        "detections": [{"class_name": "aphid", "confidence": 0.93}],
        "model_version": "2026.1-edge",
    }
    if provenance is not None:
        data["provenance"] = provenance
    return EdgeSyncRequest(
        type="pest_detection",
        data=data,
        idempotency_key="a" * 32,
        occurred_at=datetime(2026, 11, 3, 10, tzinfo=UTC),
        device_id="edge-1",
        field_id="field-1",
    )


def _block(**over):
    return {
        "schema": "sahool.detection-provenance/v1",
        "model_id": "pest_detector_int8.onnx",
        "model_version": "2026.1-edge",
        "artifact_sha256": _SHA,
        "input_sha256": hashlib.sha256(b"leaf").hexdigest(),
        "threshold": 0.6,
        "calibrated": True,
        **over,
    }


async def test_stored_detection_gets_a_provenance_row_and_the_receipt_reads_it(monkeypatch):
    from api.routers.edge import edge_sync_receive

    conn = _wire(monkeypatch)
    receipt = await edge_sync_receive(_request(_block()), user=_USER)
    assert receipt["status"] == "stored" and receipt["id"] == 41
    assert len(conn.provenance) == 1
    tenant, result_id, index = conn.provenance[0][:3]
    assert (tenant, result_id, index) == (_TENANT, 41, 0)
    [row] = receipt["provenance"]
    assert row["artifact_sha256"] == _SHA
    assert row["attestation"] == "attested"
    assert row["calibrated"] is False, "المعايرةُ ادّعاها الجهاز ولا سجلَّ لها"
    assert row["created_at"] == "2026-11-03T00:00:00+00:00"


async def test_legacy_detection_without_provenance_is_still_recorded(monkeypatch):
    from api.routers.edge import edge_sync_receive

    conn = _wire(monkeypatch)
    receipt = await edge_sync_receive(_request(None), user=_USER)
    assert [r["attestation"] for r in receipt["provenance"]] == ["unattested_legacy"]
    assert conn.provenance[0][8] is None  # artifact_sha256


async def test_malformed_provenance_is_422_before_any_connection(monkeypatch):
    import api.routers.edge as route
    from api.routers.edge import edge_sync_receive

    @contextlib.asynccontextmanager
    async def _never(_user):
        raise AssertionError("opened a connection for an invalid provenance claim")
        yield

    monkeypatch.setattr(route, "tenant_connection", _never)
    with pytest.raises(HTTPException) as err:
        await edge_sync_receive(_request(_block(artifact_sha256="nope")), user=_USER)
    assert err.value.status_code == 422
    assert "artifact_sha256_invalid" in err.value.detail
