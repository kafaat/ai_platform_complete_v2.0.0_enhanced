"""v239 — نسبُ كشف الحافّة على PostgreSQL حيّة بدورٍ مقيَّد (NOBYPASSRLS).

يُقاس مسارُ الكتابة والقراءة **نفسه** الذي يستدعيه ``api/routers/edge.py``
(``api/edge_models.record_detection_provenance`` / ``read_detection_provenance``) لا SQL مكتوبٌ بيد الاختبار:

* موجب: المستأجر A يكتب نسبَ كشفه ويقرؤه كما خُزِّن (بصمة المصنوعة · بصمة الصورة · العتبة).
* سالب: المستأجر B لا يرى نسبَ A، ولا يستطيع ربط صفٍّ بنتيجة A (مفتاح مركّب + RLS).
* بلا سياق مستأجر: لا قراءة ولا كتابة.
* سجلّ تدقيق: لا UPDATE، ولا «معايَر» بلا مرجع معايرة، ولا «مُثبَت» بلا بصمة.

الدور في ``TEST_DATABASE_URL`` يجب أن يكون مقيَّداً (يُتحقَّق قبل القياس)؛ الزرع يُحذف في ``finally``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg")

_ROOT = Path(__file__).resolve().parents[1]
_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
_A = "aaaaaaaa-2390-4000-8000-00000000000a"
_B = "bbbbbbbb-2390-4000-8000-00000000000b"
_ARTIFACT = hashlib.sha256(b"pest-model-bytes").hexdigest()
_INPUT = hashlib.sha256(b"leaf-image-bytes").hexdigest()

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً مُهاجَرة ودوراً مقيَّداً",
    )
)


def _module():
    name = "detection_provenance_live_pg"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, _ROOT / "services/sahool-platform/api/edge_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _attested_data() -> dict:
    return {
        "detections": [
            {"class_name": "aphid", "confidence": 0.93},
            {"class_name": "rust", "confidence": 0.71},
        ],
        "model_version": "2026.1-edge",
        "provenance": {
            "schema": "sahool.detection-provenance/v1",
            "model_id": "pest_detector_int8.onnx",
            "model_version": "2026.1-edge",
            "artifact_sha256": _ARTIFACT,
            "input_sha256": _INPUT,
            "threshold": 0.6,
            "calibrated": True,  # ادّعاءُ الحافّة — يجب أن يُتجاهَل
        },
    }


async def _app(tenant: str | None = None):
    conn = await asyncpg.connect(_APP_DSN)
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row is not None and not row["rolsuper"] and not row["rolbypassrls"], (
        "TEST_DATABASE_URL ليس دوراً مقيَّداً — لا يقيس عزلاً"
    )
    if tenant is not None:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return conn


@pytest.fixture
async def seeded():
    """حقلان ونتيجتا كشف (A وB) يزرعهما المالك؛ تُحذَف (ومعها النسب بالتتالي) في finally."""
    tag = f"v239-{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    ids: dict[str, int] = {}
    try:
        for tenant, suffix in ((_A, "a"), (_B, "b")):
            field = f"{tag}-{suffix}"
            await admin.execute(
                "INSERT INTO field_boundaries (field_id, field_name, tenant_id) "
                "VALUES ($1, $1, $2::uuid)",
                field,
                tenant,
            )
            ids[tenant] = await admin.fetchval(
                "INSERT INTO edge_results (field_id, tenant_id, result_type, device, "
                "result_data, idempotency_key, occurred_at) "
                "VALUES ($1, $2::uuid, 'pest_detection', 'edge-v239', $3::jsonb, $4, now()) "
                "RETURNING id",
                field,
                tenant,
                json.dumps(_attested_data()),
                uuid.uuid4().hex,
            )
        yield ids
    finally:
        await admin.execute("DELETE FROM edge_results WHERE field_id LIKE $1", f"{tag}-%")
        await admin.execute("DELETE FROM field_boundaries WHERE field_id LIKE $1", f"{tag}-%")
        await admin.close()


@pytest.mark.asyncio
async def test_tenant_writes_and_reads_its_own_provenance_through_the_write_path(seeded):
    mod = _module()
    rows = mod.provenance_rows("pest_detection", _attested_data())
    app = await _app()
    try:
        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", _A)
            await mod.record_detection_provenance(
                app, tenant_id=_A, edge_result_id=seeded[_A], rows=rows
            )
            stored = await mod.read_detection_provenance(app, seeded[_A])
    finally:
        await app.close()
    assert [r["detection_index"] for r in stored] == [0, 1]
    first = stored[0]
    assert first["artifact_sha256"] == _ARTIFACT
    assert first["input_sha256"] == _INPUT
    assert first["model_id"] == "pest_detector_int8.onnx"
    assert first["model_version"] == "2026.1-edge"
    assert first["threshold"] == 0.6 and first["score"] == 0.93
    assert first["label"] == "aphid"
    assert first["attestation"] == "attested"
    assert first["calibrated"] is False and first["calibration_ref"] is None
    assert first["tenant_id"] == _A and first["created_at"]


@pytest.mark.asyncio
async def test_other_tenant_cannot_read_or_attach_provenance_to_a_foreign_result(seeded):
    mod = _module()
    rows = mod.provenance_rows("pest_detection", _attested_data())
    writer = await _app(_A)
    try:
        await mod.record_detection_provenance(
            writer, tenant_id=_A, edge_result_id=seeded[_A], rows=rows
        )
    finally:
        await writer.close()

    # فهرسٌ لم يُكتَب بعد: وإلّا ابتلع ON CONFLICT المحاولةَ قبل أن يبلغها المفتاحُ الأجنبيّ.
    foreign = [{**rows[0], "detection_index": 7}]
    reader = await _app(_B)
    try:
        assert await mod.read_detection_provenance(reader, seeded[_A]) == []
        assert await reader.fetchval("SELECT count(*) FROM detection_provenance") == 0
        # صفٌّ باسم B على نتيجة A: المفتاح المركّب (edge_result_id, tenant_id) يرفضه.
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await mod.record_detection_provenance(
                reader, tenant_id=_B, edge_result_id=seeded[_A], rows=foreign
            )
        # صفٌّ باسم A من سياق B: RLS WITH CHECK يرفضه.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await mod.record_detection_provenance(
                reader, tenant_id=_A, edge_result_id=seeded[_A], rows=foreign
            )
    finally:
        await reader.close()

    owner = await _app(_A)  # موجب: صاحبُ النتيجة يرى صفّيه
    try:
        assert len(await mod.read_detection_provenance(owner, seeded[_A])) == 2
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_without_tenant_context_nothing_is_read_or_written(seeded):
    mod = _module()
    rows = mod.provenance_rows("pest_detection", _attested_data())
    owner = await _app(_A)
    try:
        await mod.record_detection_provenance(
            owner, tenant_id=_A, edge_result_id=seeded[_A], rows=rows
        )
    finally:
        await owner.close()
    anonymous = await _app()
    try:
        assert await anonymous.fetchval("SELECT count(*) FROM detection_provenance") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await mod.record_detection_provenance(
                anonymous, tenant_id=_B, edge_result_id=seeded[_B], rows=rows[:1]
            )
    finally:
        await anonymous.close()


@pytest.mark.asyncio
async def test_provenance_is_an_audit_record_not_an_editable_claim(seeded):
    mod = _module()
    app = await _app(_B)
    try:
        await mod.record_detection_provenance(
            app,
            tenant_id=_B,
            edge_result_id=seeded[_B],
            rows=mod.provenance_rows("pest_detection", _attested_data()),
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute(
                "UPDATE detection_provenance SET artifact_sha256 = $1 WHERE edge_result_id = $2",
                "0" * 64,
                seeded[_B],
            )
        base = (
            "INSERT INTO detection_provenance (tenant_id, edge_result_id, detection_index, "
            "score, attestation, calibrated, calibration_ref, artifact_sha256, input_sha256, "
            "model_id, model_version, threshold) VALUES ($1::uuid, $2, $3, 0.5, $4, $5, NULL, "
            "$6, $7, 'm', 'v', 0.5)"
        )
        with pytest.raises(asyncpg.CheckViolationError):  # «معايَر» بلا سجلّ معايرة
            await app.execute(base, _B, seeded[_B], 10, "attested", True, _ARTIFACT, _INPUT)
        with pytest.raises(asyncpg.CheckViolationError):  # «مُثبَت» بلا بصمة مصنوعة
            await app.execute(base, _B, seeded[_B], 11, "attested", False, None, _INPUT)
        with pytest.raises(asyncpg.CheckViolationError):  # «قديم» يدّعي بصمة
            await app.execute(
                base, _B, seeded[_B], 12, "unattested_legacy", False, _ARTIFACT, _INPUT
            )
    finally:
        await app.close()
