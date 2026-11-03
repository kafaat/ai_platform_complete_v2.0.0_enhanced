"""api/edge_models.py — نماذج مزامنة الحافة (Edge Sync Models)
=====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج نموذج «مزامنة الحافة».

يحوي ``EdgeSyncRequest`` المُستخدَم في ``api/routers/edge.py`` لاستقبال نتائج
أجهزة الحافة (edge) مع منع التكرار (dedup). النموذج مكتفٍ ذاتيّاً (pydantic فقط)
ومنقول حرفيّاً من ``api/main.py`` حفظاً للسلوك والمخطّط (OpenAPI) كما هو.

ويحوي أيضاً نسبَ كشف الآفات/الأمراض (v239 ``detection_provenance``) — منطقٌ صرف لعقد
الإدخال نفسه وكاتبٌ/قارئٌ يأخذان اتّصال المعاملة؛ هنا لا في وحدةٍ جديدة لأنّ عدد وحدات
المنصّة راتشِتٌ لا يصعد (``test_p0_platform_module_growth_guard``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─── استقبال مزامنة edge مع dedup (Hardening مراجعة 7) ───────────
class EdgeSyncRequest(BaseModel):
    type: str
    data: dict
    # max_length يطابق العمود edge_results.idempotency_key = VARCHAR(32) (v9_edge_idempotency):
    # كان 128 فيجتاز مفتاحٌ بطول 33–128 التحقّقَ ثمّ يسقط عند حدّ القاعدة (500 لا 422).
    # توسيعُ العمود هجرةٌ على MANIFEST المجمَّد خلف GATE-01، فيُضبَط العقدُ على المخزَّن
    # (Copilot على #997). الجهازُ يولّد uuid4().hex = 32 حرفاً بالضبط.
    idempotency_key: str = Field(min_length=16, max_length=32)
    occurred_at: datetime
    device_id: str = Field(min_length=1, max_length=50)
    field_id: str = Field(min_length=1, max_length=50)

    @field_validator("occurred_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


# ─── نسبُ كشف الآفات/الأمراض (Detection Provenance, v239) ───────────
# **العطلُ:** نتيجةُ كشفٍ من الحافّة كانت تُكتَب في ``edge_results.result_data`` (JSONB حرّ)
# بلا سجلٍّ دائم يقول **أيُّ مصنوعة نموذج** (الاسم · الإصدار · sha256) و**أيُّ صورة**
# (بصمة المحتوى) و**أيُّ عتبة** وحالةُ المعايرة أنتجتها — فتنبيهٌ لا يُتتبَّع إلى مصدره
# ولا يُدقَّق.
#
# **القاعدة (v239 ``detection_provenance``):** كلُّ كشفٍ مُخزَّن يحمل صفَّ نسبٍ واحداً
# داخل **معاملة الكتابة نفسها** مع صفّ ``edge_results``:
#
# * ``attested`` — الجهازُ أرسل كتلة ``provenance`` بمخطّط ``sahool.detection-provenance/v1``
#   وبصمتين صالحتين (بصمةُ المصنوعة من حكم بوّابة الحافّة ``model_artifact_gate``).
# * ``unattested_legacy`` — نتيجةٌ بلا كتلة نسب (جهازٌ أقدم أو طابورٌ قبل الترقية): يُكتَب
#   الصفُّ مع ذلك بلا بصمات، فيقول الغيابَ صراحةً بدل أن يغيب السجلّ.
# * كتلةُ نسبٍ **حاضرةٌ ومشوَّهة** ⇒ ``ValueError`` ⇒ 422: ادّعاءُ هويّةٍ لا يُقبَل نصفَ صالح.
#
# **المعايرةُ قرارُ المنصّة لا ادّعاءُ الحافّة:** ``calibrated`` يُكتَب ``False`` دائماً
# ما لم يوجد سجلُّ معايرةٍ مرتبط (``calibration_ref``)، ولا سجلَّ معايرةٍ لمصنوعات نماذج
# الحافّة في المخطّط اليوم — فقيمةُ ``calibrated`` المرسَلة من الجهاز تُتجاهَل.


#: أنواعُ نتائج الحافّة التي تحمل كشوفاً تحتاج نسباً.
PROVENANCE_RESULT_TYPES = frozenset({"pest_detection"})
PROVENANCE_SCHEMA = "sahool.detection-provenance/v1"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_DETECTIONS = 500
_TEXT_MAX = 200


def _unit_interval(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}_not_a_number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"{name}_out_of_range")
    return number


def _short_text(value: object, name: str, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > _TEXT_MAX:
        raise ValueError(f"{name}_invalid")
    return value


def _attested_block(block: object) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        raise ValueError("provenance_not_an_object")
    if block.get("schema") != PROVENANCE_SCHEMA:
        raise ValueError("provenance_schema_unknown")
    shas: dict[str, str] = {}
    for key in ("artifact_sha256", "input_sha256"):
        value = block.get(key)
        if not isinstance(value, str) or not _SHA256_HEX.match(value):
            raise ValueError(f"{key}_invalid")
        shas[key] = value
    return {
        "model_id": _short_text(block.get("model_id"), "model_id", required=True),
        "model_version": _short_text(block.get("model_version"), "model_version", required=True),
        **shas,
        "threshold": _unit_interval(block.get("threshold"), "threshold"),
        "attestation": "attested",
    }


def _legacy_block(data: Mapping[str, Any]) -> dict[str, Any]:
    version = data.get("model_version")
    return {
        "model_id": None,
        "model_version": (
            version
            if isinstance(version, str) and version.strip() and len(version) <= _TEXT_MAX
            else None
        ),
        "artifact_sha256": None,
        "input_sha256": None,
        "threshold": None,
        "attestation": "unattested_legacy",
    }


def provenance_rows(result_type: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """صفُّ نسبٍ لكلّ كشف — منطقٌ صرف بلا قاعدة.

    نوعٌ لا يحمل كشوفاً ⇒ ``[]``. والمعايرةُ ``False`` بلا مرجع، أيّاً كان ما أرسله الجهاز.
    """
    if result_type not in PROVENANCE_RESULT_TYPES:
        return []
    detections = data.get("detections")
    if detections is None:
        detections = []
    if not isinstance(detections, Sequence) or isinstance(detections, (str, bytes)):
        raise ValueError("detections_not_a_list")
    if len(detections) > _MAX_DETECTIONS:
        raise ValueError("detections_too_many")
    block = data.get("provenance")
    common = _legacy_block(data) if block is None else _attested_block(block)
    rows: list[dict[str, Any]] = []
    for index, detection in enumerate(detections):
        if not isinstance(detection, Mapping):
            raise ValueError("detection_not_an_object")
        rows.append(
            {
                "detection_index": index,
                "label": _short_text(detection.get("class_name"), "label", required=False),
                "score": _unit_interval(detection.get("confidence"), "score"),
                **common,
                "calibrated": False,
                "calibration_ref": None,
            }
        )
    return rows


_INSERT = """
INSERT INTO detection_provenance
    (tenant_id, edge_result_id, detection_index, label, score, threshold,
     model_id, model_version, artifact_sha256, input_sha256, attestation,
     calibrated, calibration_ref)
VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
ON CONFLICT (edge_result_id, detection_index) DO NOTHING
"""

_SELECT = """
SELECT edge_result_id, detection_index, label, score, threshold, model_id,
       model_version, artifact_sha256, input_sha256, attestation, calibrated,
       calibration_ref, tenant_id, created_at
FROM detection_provenance
WHERE edge_result_id = $1
ORDER BY detection_index
"""


async def record_detection_provenance(
    conn, *, tenant_id: str, edge_result_id: int, rows: Sequence[Mapping[str, Any]]
) -> None:
    """يكتب صفوف النسب على اتّصال المعاملة نفسه (RLS: سياقُ المستأجر مضبوطٌ مسبقاً)."""
    for row in rows:
        await conn.execute(
            _INSERT,
            tenant_id,
            edge_result_id,
            row["detection_index"],
            row["label"],
            row["score"],
            row["threshold"],
            row["model_id"],
            row["model_version"],
            row["artifact_sha256"],
            row["input_sha256"],
            row["attestation"],
            row["calibrated"],
            row["calibration_ref"],
        )


def _serialise(record: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(record)
    for key in ("score", "threshold"):
        if out.get(key) is not None:
            out[key] = float(out[key])
    if out.get("tenant_id") is not None:
        out["tenant_id"] = str(out["tenant_id"])
    created = out.get("created_at")
    if created is not None and hasattr(created, "isoformat"):
        out["created_at"] = created.isoformat()
    return out


async def read_detection_provenance(conn, edge_result_id: int) -> list[dict[str, Any]]:
    """صفوفُ النسب لنتيجة واحدة كما خُزِّنت — مرشَّحةً بـRLS المستأجر."""
    records = await conn.fetch(_SELECT, edge_result_id)
    return [_serialise(r) for r in records]
