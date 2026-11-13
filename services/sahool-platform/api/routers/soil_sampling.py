"""api/routers/soil_sampling.py — بروتوكول أخذ عيّنة التربة (Soil Sampling)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ النطاق (``soil_sampling_protocol``) كانت مُستورَدة على مستوى وحدة ``main``
وتُستخدَم حصريّاً من هذه الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً)
لتفادي استيراد يتيم في ``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from core.authorization import has_permission
from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition
from core.irrigation_water_analysis import WaterSample, analyze_water_sample
from core.lab_sampling import (
    SoilLabResult,
    analyze_soil_lab_result,
    lab_decision_context,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from api import lab_store
from api.idempotency import request_digest
from api.main import (
    CommandStore,
    Permission,
    UserSchema,
    _idem_key,
    _idempotent,
    get_current_user,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.soil_evidence_bridge import publish_soil_lab_evidence, stored_lab_publication_receipt
from api.soil_sampling_protocol import (
    sampling_depth,
    sampling_protocol,
    subsamples_for_area,
)
from shared.soil_texture import normalize_texture_label, usda_texture_class

router = APIRouter()


@router.get("/api/v1/soil-sampling/subsamples")
def soil_subsamples_endpoint(area_ha: float):
    """عدد العيّنات الفرعيّة الموصى بها حسب مساحة الحقل."""
    return subsamples_for_area(area_ha)


@router.get("/api/v1/soil-sampling/depth")
def soil_depth_endpoint(purpose: str = "general"):
    """العمق المناسب لأخذ العيّنة حسب الغرض (general/nitrate/no_till/orchard)."""
    return sampling_depth(purpose)


@router.get("/api/v1/soil-sampling/protocol")
def soil_protocol_endpoint(area_ha: float | None = None, purpose: str = "general"):
    """البروتوكول الكامل لأخذ عيّنة تربة صحيحة (خطوات + تحذيرات + توقيت)."""
    return sampling_protocol(area_ha, purpose)


# ── Lab Sampling v3: durable sample/custody/result workflow ─────────────────
_COMPAT_STATUS = {
    "planned": "requested",
    "collected": "sampled",
    "submitted": "in_lab",
    "analyzed": "result_received",
    "approved": "approved",
}


def _reject_boolean_measurement(value):
    if isinstance(value, bool):
        raise ValueError("expected a numeric measurement")
    return value


Coordinate = Annotated[float, BeforeValidator(_reject_boolean_measurement)]
GPSAccuracy = Annotated[Coordinate, Field(ge=0, allow_inf_nan=False)]


class SamplingIndicatorSource(BaseModel):
    scene_id: str | None = Field(default=None, min_length=1, max_length=256)
    acquisition_date: date | None = None
    asset_id: str | None = Field(default=None, min_length=1, max_length=256)


class SamplingOrigin(BaseModel):
    sampling_purpose: (
        Literal["fertility", "nitrate", "salinity", "orchard", "texture", "no_till"] | None
    ) = None
    composite: bool | None = None
    location_id: str | None = Field(default=None, min_length=1, max_length=80)
    planned_depth_cm: tuple[float, float] | None = None
    point_id: str = Field(min_length=1, max_length=80)
    zone_id: str = Field(min_length=1, max_length=80)
    longitude: Coordinate = Field(ge=-180, le=180)
    latitude: Coordinate = Field(ge=-90, le=90)
    indicators: list[Literal["ndvi", "ndmi", "reci", "msavi", "slope"]] = Field(
        default_factory=list, max_length=5
    )

    indicator_sources: dict[
        Literal["ndvi", "ndmi", "reci", "msavi", "slope"], SamplingIndicatorSource
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_indicator_sources(self):
        if self.planned_depth_cm is not None:
            start, end = self.planned_depth_cm
            if not (0 <= start < end < float("inf")):
                raise ValueError("invalid planned depth interval")
        spectral_identity = None
        for name, source in self.indicator_sources.items():
            if name not in self.indicators:
                raise ValueError("source requires matching indicator")
            if name == "slope" and not (source.asset_id or "").strip():
                raise ValueError("slope requires a terrain asset")
            if name != "slope":
                if not (source.scene_id or "").strip() or not source.acquisition_date:
                    raise ValueError("spectral source requires a scene ID and acquisition date")
                identity = (source.scene_id, source.acquisition_date)
                if spectral_identity is not None and spectral_identity != identity:
                    raise ValueError(
                        "spectral sources must reference the same scene and acquisition date"
                    )
                spectral_identity = identity
        return self


class LabSampleIn(BaseModel):
    field_id: str
    kind: Literal["soil", "water"]
    latitude: Coordinate = Field(ge=-90, le=90)
    longitude: Coordinate = Field(ge=-180, le=180)
    sampled_on: date | None = None
    depth_cm_from: int | None = Field(default=None, ge=0)
    depth_cm_to: int | None = Field(default=None, ge=0)
    source: str | None = None
    status: Literal["planned", "collected", "submitted"] = "collected"
    gps_accuracy_m: GPSAccuracy | None = None
    sampling_plan_id: str | None = Field(default=None, min_length=1, max_length=64)
    sampling_origin: SamplingOrigin | None = None

    @field_validator("sampling_plan_id", mode="before")
    @classmethod
    def blank_plan_is_none(cls, value):
        # Older clients sent "" for "no plan"; keep those requests (and replays) valid.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def validate_collection(self):
        if self.kind == "soil" and (self.depth_cm_from is None or self.depth_cm_to is None):
            raise ValueError("soil collection requires both sampling depths")
        if (
            self.depth_cm_from is not None
            and self.depth_cm_to is not None
            and self.depth_cm_to <= self.depth_cm_from
        ):
            raise ValueError("ending depth must exceed starting depth")
        if self.sampling_origin and (self.kind != "soil" or not self.sampling_plan_id):
            raise ValueError("sampling_origin requires a soil sample and a plan ID")
        return self

    barcode: str | None = None
    collected_by: str | None = None


class SoilLabResultIn(BaseModel):
    sample_id: str
    ph: float | None = None
    ec_dsm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ec_extraction_method: (
        Literal[
            "saturated_paste", "soil_water_1_1", "soil_water_1_2_5", "soil_water_1_5", "unspecified"
        ]
        | None
    ) = None
    organic_matter_pct: float | None = None
    nitrogen_mg_kg: float | None = None
    phosphorus_mg_kg: float | None = None
    potassium_mg_kg: float | None = None
    cec_cmol_kg: float | None = None
    calcium_carbonate_pct: float | None = None
    sand_pct: float | None = Field(default=None, ge=0, le=100)
    silt_pct: float | None = Field(default=None, ge=0, le=100)
    clay_pct: float | None = Field(default=None, ge=0, le=100)
    texture: str | None = None

    @model_validator(mode="after")
    def classify_measured_texture(self):
        if self.ec_extraction_method and self.ec_dsm is None:
            raise ValueError("ec_extraction_method requires an EC measurement")
        # The class is decided on fractions normalised to 100; the fractions are stored as
        # measured. Within the ±1 tolerance a point on a class boundary can therefore get
        # the class of its normalised position, not of the raw numbers.
        written = (self.texture or "").strip() or None
        label = normalize_texture_label(written)
        if written and label is None:
            raise ValueError("texture must be one of the 12 USDA texture classes")
        self.texture = label
        fractions = (self.clay_pct, self.sand_pct, self.silt_pct)
        if any(value is not None for value in fractions):
            if None in fractions or abs(sum(fractions) - 100) > 1:
                raise ValueError("sand, silt and clay percentages must total 100 ± 1")
            result = usda_texture_class(*fractions)
            if label and label != result["key"]:
                raise ValueError("texture conflicts with measured fractions")
            self.texture = result["key"]
        return self

    # فصل الواجبات: لا يُقبَل «approved» من نموذج الإدخال — الإدخال العاديّ يُنشئ نتيجة
    # غير مُعتمَدة (result_received)، والاعتماد انتقال حالة منفصل مُصرَّح به
    # (POST /lab/samples/{id}/transition → approved) بهويّة مُعتمِد مُصادَقة. حذف الحقل
    # يمنع تصديق المُدخِل نتيجته بنفسه في خطوة واحدة (fail-closed على مستوى العقد).
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    method_code: str | None = None
    detection_limit: float | None = Field(default=None, ge=0)
    uncertainty: float | None = Field(default=None, ge=0)
    supersedes_result_ids: dict[str, UUID] = Field(default_factory=dict)
    correction_reason: str | None = Field(default=None, max_length=160)


class LabTransitionIn(BaseModel):
    reviewed_result_ids: list[UUID] | None = None
    target_status: Literal[
        "requested",
        "sampled",
        "in_lab",
        "result_received",
        "approved",
        "published",
        "rejected",
        "cancelled",
    ]
    location: str | None = None
    condition_notes: str | None = None
    seal_id: str | None = None


def _analytes(payload: SoilLabResultIn) -> list[dict]:
    units = {
        "ph": "1",
        "ec_dsm": "dS/m",
        "organic_matter_pct": "%",
        "nitrogen_mg_kg": "mg/kg",
        "phosphorus_mg_kg": "mg/kg",
        "potassium_mg_kg": "mg/kg",
        "cec_cmol_kg": "cmol(+)/kg",
        "calcium_carbonate_pct": "%",
        "sand_pct": "%",
        "silt_pct": "%",
        "clay_pct": "%",
        "texture": None,
    }
    out = []
    for name, unit in units.items():
        value = getattr(payload, name)
        if value is not None:
            out.append(
                {
                    "analyte": name,
                    "value": value,
                    "unit": unit,
                    "method_code": (
                        payload.ec_extraction_method or payload.method_code
                        if name == "ec_dsm"
                        else payload.method_code
                    ),
                    "detection_limit": payload.detection_limit,
                    "uncertainty": payload.uncertainty,
                    "supersedes_result_id": payload.supersedes_result_ids.get(name),
                }
            )
    return out


# Sand, silt and clay are validated together and texture is derived from them, so a
# correction resends the whole group. Each resent member supersedes its current row;
# otherwise the unchanged fractions and the new texture reuse the old idempotency key
# in soil-service with a different value/time (409) and the old texture stays approved.
_TEXTURE_GROUP = ("sand_pct", "silt_pct", "clay_pct", "texture")


async def _link_texture_group(conn, tenant_id: str, sample_id: str, analytes: list[dict]) -> None:
    unlinked = [
        a["analyte"]
        for a in analytes
        if a["analyte"] in _TEXTURE_GROUP and not a.get("supersedes_result_id")
    ]
    if not unlinked:
        return
    current = await lab_store.current_soil_result_ids(
        conn, tenant_id=tenant_id, sample_id=sample_id, analytes=unlinked
    )
    for item in analytes:
        if item["analyte"] in current and not item.get("supersedes_result_id"):
            item["supersedes_result_id"] = current[item["analyte"]]


@router.get("/api/v1/lab/samples")
async def list_lab_samples(
    field_id: str | None = None,
    sample_id: str | None = None,
    include_review: bool = False,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Samples of the tenant, optionally of one field or one sample.

    ``include_review`` with ``sample_id`` adds the current review cycle of that soil sample
    under ``review``: the results a reviewer is shown and must name when approving, and
    whether this user may approve or publish them. It is read here, not from a route of
    its own, because the platform domain-route budget is already above its ceiling.
    """
    if include_review and not sample_id:
        raise HTTPException(422, "include_review requires sample_id")
    tenant = str(user.tenant_id)
    async with tenant_connection(user) as conn:
        rows = await lab_store.list_samples(
            conn, tenant_id=tenant, field_id=field_id, sample_id=sample_id
        )
        if not include_review:
            return rows
        if not rows or rows[0]["kind"] != "soil":
            raise HTTPException(404, "soil sample not found")
        sample = rows[0]
        results = await lab_store.review_results(conn, tenant, sample["sample_id"])
        reviewer = has_permission(user, Permission.INSPECTION_REVIEW)
        authors = await lab_store.result_entry_actors(conn, tenant, sample["sample_id"])
        review = {
            "results": results,
            "can_approve": bool(
                results
                and reviewer
                and sample["status"] == "result_received"
                and authors
                and str(user.user_id) not in authors
            ),
            "can_publish": bool(results and reviewer and sample["status"] == "approved"),
        }
        return [{**sample, "review": review}]


def _sample_request_digest(payload: LabSampleIn) -> str:
    """بصمة الحمولة (JSON مرتَّب) — تُميِّز الإعادةَ الصادقة عن إعادة استعمال المفتاح."""
    data = payload.model_dump(mode="json")
    if data["sampling_origin"] is None:
        del data["sampling_origin"]  # preserve pre-migration retry fingerprints
    else:
        origin = payload.sampling_origin.model_dump(mode="json", exclude_none=True)
        if not origin["indicator_sources"]:
            del origin["indicator_sources"]
        data["sampling_origin"] = origin
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/api/v1/lab/samples")
async def create_lab_sample(
    payload: LabSampleIn,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """ينشئ عيّنة مختبر. idempotent عند وجود Idempotency-Key (UUID): صندوق الإرسال
    دون اتّصال في الموبايل يُعيد الطلب نفسه بعد انقطاع، وبلا مفتاح كانت كلّ إعادة
    عيّنةً جديدة بمعرّف جديد. الإعادة الصادقة تُعيد العيّنة الأولى؛ والمفتاح نفسه بحمولة
    مختلفة ⇒ 409."""
    data = payload.model_dump(mode="python")
    if payload.sampling_origin is not None:
        origin = payload.sampling_origin.model_dump(mode="json", exclude_none=True)
        if not origin["indicator_sources"]:
            del origin["indicator_sources"]
        data["sampling_origin"] = origin
    data["status"] = _COMPAT_STATUS[payload.status]
    async with tenant_connection(user) as conn:

        async def _work():
            try:
                row = await lab_store.create_sample(
                    conn, tenant_id=str(user.tenant_id), created_by=str(user.user_id), payload=data
                )
            except lab_store.SampleFieldNotFound as exc:
                raise HTTPException(404, "sample field not found") from exc
            await lab_store.add_custody_event(
                conn,
                tenant_id=str(user.tenant_id),
                sample_id=row["sample_id"],
                actor_id=str(user.user_id),
                event_type="sample_created",
            )
            # تُخزَّن نتيجةَ أمرٍ وتُعاد حرفيّاً عند الإعادة ⇒ قيم قابلة للتسلسل.
            return json.loads(json.dumps(dict(row), default=str))

        if idem:
            return await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                _work,
                command_type="lab_sample.create",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={},
                request_digest=_sample_request_digest(payload),
            )
        return await _work()


@router.post("/api/v1/lab/soil-results")
async def submit_soil_lab_result(
    payload: SoilLabResultIn,
    idem: str | None = Depends(_idem_key),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analytes = _analytes(payload)
    if not analytes:
        raise HTTPException(422, "at least one analyte is required")
    if payload.supersedes_result_ids.keys() - {item["analyte"] for item in analytes}:
        raise HTTPException(422, "a replacement value is required for each superseded analyte")
    async with tenant_connection(user) as conn:

        async def record_result():
            return await _record_soil_result(conn, payload, user, analytes)

        if idem:
            # An omitted observation time is assigned on the first successful write.
            # Replays must identify that same request even after the server clock advances.
            excluded = set() if "observed_at" in payload.model_fields_set else {"observed_at"}
            digest = request_digest(
                {
                    "actor_id": str(user.user_id),
                    "result": payload.model_dump(mode="json", exclude=excluded),
                }
            )
            return await _idempotent(
                CommandStore(get_pool(), conn=conn),
                idem,
                record_result,
                command_type="lab_soil_result.submit",
                actor_id=str(user.user_id),
                tenant_id=str(user.tenant_id),
                payload={},
                request_digest=digest,
            )
        return await record_result()


async def _record_soil_result(
    conn, payload: SoilLabResultIn, user: UserSchema, analytes: list[dict]
):
    sample = await lab_store.get_sample(
        conn, tenant_id=str(user.tenant_id), sample_id=payload.sample_id
    )
    if not sample or sample["kind"] != "soil":
        raise HTTPException(404, "soil sample not found")
    current = sample["status"]
    is_correction = bool(payload.supersedes_result_ids)
    if is_correction:
        await _link_texture_group(conn, str(user.tenant_id), payload.sample_id, analytes)
    # A published sample can reopen only for a correction with a matching parent.
    # Every replacement still requires fresh approval before republication.
    if not (is_correction and current == "published"):
        if current == "sampled":
            await lab_store.set_status(
                conn,
                tenant_id=str(user.tenant_id),
                sample_id=payload.sample_id,
                status="in_lab",
            )
            current = "in_lab"
        try:
            validate_soil_transition(current, "result_received", has_result=True)
        except SoilWorkflowError as exc:
            raise HTTPException(exc.http_status, exc.message_ar) from exc
    # فصل الواجبات: الإدخال العاديّ يُنشئ نتيجة غير مُعتمَدة (quality_status='unreviewed')
    # بحالة عيّنة result_received. لا اعتماد ذاتيّ من مُدخِل البيانات — الاعتماد انتقال
    # حالة منفصل مُصرَّح به (/transition → approved) يَختِم الصفوف بهويّة المُعتمِد.
    try:
        await lab_store.insert_soil_results(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            analytes=analytes,
            observed_at=payload.observed_at,
            approved=False,
            approved_by=None,
            correction_reason=payload.correction_reason,
        )
    except lab_store.InvalidResultReplacement as exc:
        raise HTTPException(
            409, "superseded result must be current and match the sample and analyte"
        ) from exc
    await lab_store.set_status(
        conn,
        tenant_id=str(user.tenant_id),
        sample_id=payload.sample_id,
        status="result_received",
    )
    await lab_store.add_custody_event(
        conn,
        tenant_id=str(user.tenant_id),
        sample_id=payload.sample_id,
        actor_id=str(user.user_id),
        event_type="lab_result_received",
    )
    values = payload.model_dump(
        exclude={
            "observed_at",
            "ec_extraction_method",
            "method_code",
            "detection_limit",
            "uncertainty",
            "supersedes_result_ids",
            "correction_reason",
        }
    )
    return _interpret_lab_values(values, payload.ec_extraction_method or payload.method_code)


def _interpret_lab_values(values: dict, method: str | None):
    measured_ec = values.get("ec_dsm")
    if method != "saturated_paste":
        values = {**values, "ec_dsm": None}
    analysis = analyze_soil_lab_result(SoilLabResult(**values))
    if measured_ec is not None:
        ec = analysis["classification"]["salinity_ec"]
        ec.update(value_dsm=measured_ec, extraction_method=method or "unspecified")
        if method != "saturated_paste":
            ec["note_ar"] = "تفسير عتبات ECe يحتاج مستخلص العجينة المشبعة."
    return analysis


@router.post("/api/v1/lab/water-results")
async def submit_water_lab_result(
    payload: WaterSample,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analysis = analyze_water_sample(payload)
    observed = (
        datetime.fromisoformat(payload.sampled_at) if payload.sampled_at else datetime.now(UTC)
    )
    async with tenant_connection(user) as conn:
        sample = await lab_store.get_sample(
            conn, tenant_id=str(user.tenant_id), sample_id=payload.sample_id
        )
        if not sample or sample["kind"] != "water":
            raise HTTPException(404, "water sample not found")
        await lab_store.insert_water_result(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            payload=payload.__dict__,
            analysis=analysis,
            observed_at=observed,
        )
        await lab_store.set_status(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            status="result_received",
        )
    return analysis


@router.post("/api/v1/lab/samples/{sample_id}/transition")
async def transition_lab_sample(
    sample_id: str,
    payload: LabTransitionIn,
    user: UserSchema = Depends(get_current_user),
):
    review_transition = payload.target_status in {"approved", "published", "rejected"}
    permission = Permission.INSPECTION_REVIEW if review_transition else Permission.FIELD_EDIT
    require_permission(permission)(user)
    publish_payload = None
    publish_rows = None
    async with tenant_connection(user) as conn:
        sample = await lab_store.get_sample(
            conn, tenant_id=str(user.tenant_id), sample_id=sample_id
        )
        if not sample:
            raise HTTPException(404, "sample not found")
        is_soil = sample["kind"] == "soil"
        # Publication reads its rows up front: a retry after a lost response (status already
        # published) answers from the stored links, or repairs links an older version left out.
        # Values and result ids come from the same rows: one current row per analyte.
        if is_soil and payload.target_status == "published":
            publish_rows = await lab_store.publishable_soil_results(
                conn, tenant_id=str(user.tenant_id), sample_id=sample_id
            )
            has_result = bool(publish_rows)
        else:
            # Approval needs a result of this review cycle that awaits a decision.
            has_result = is_soil and await lab_store.has_soil_result(
                conn, tenant_id=str(user.tenant_id), sample_id=sample_id
            )
        try:
            changed = validate_soil_transition(
                sample["status"], payload.target_status, has_result=has_result
            )
        except SoilWorkflowError as exc:
            raise HTTPException(exc.http_status, exc.message_ar) from exc
        if (
            is_soil
            and sample["status"] != payload.target_status
            and payload.target_status == "approved"
        ):
            authors = await lab_store.result_entry_actors(conn, str(user.tenant_id), sample_id)
            if not authors:
                raise HTTPException(409, "تعذّر تحديد مُدخل التحليل من سجل العينة.")
            if str(user.user_id) in authors:
                raise HTTPException(403, "يلزم مراجع آخر لاعتماد التحليل.")
        if payload.reviewed_result_ids is not None and (
            changed or payload.target_status != "rejected"
        ):
            results = await lab_store.review_results(conn, str(user.tenant_id), sample_id)
            if set(payload.reviewed_result_ids) != {r["result_id"] for r in results}:
                raise HTTPException(409, "تغيّرت التحاليل منذ عرضها. حدّث المراجعة.")
        row = sample
        if not changed:
            if not publish_rows:
                return row
            receipt = stored_lab_publication_receipt(publish_rows)
            if receipt is not None:
                return {**row, "soil_evidence_receipt": receipt}
            # A historical published sample can lack links. Repair the links below
            # without changing the sample timestamp or adding another custody event.
        else:
            row = await lab_store.set_status(
                conn,
                tenant_id=str(user.tenant_id),
                sample_id=sample_id,
                status=payload.target_status,
            )
            # الاعتماد المُصرَّح به هو نقطة ختم النتيجة الوحيدة: يَختِم صفوف النتيجة
            # (unreviewed→approved) بهويّة المُعتمِد المُصادَقة عبر البوّابة — فصل الواجبات.
            if is_soil and (payload.target_status == "rejected" or sample["status"] == "rejected"):
                # Also seal pending rows left by older versions before starting their retest.
                await lab_store.reject_soil_results(
                    conn, tenant_id=str(user.tenant_id), sample_id=sample_id
                )
            if payload.target_status == "approved" and is_soil:
                await lab_store.approve_soil_results(
                    conn,
                    tenant_id=str(user.tenant_id),
                    sample_id=sample_id,
                    approved_by=str(user.user_id),
                )
            await lab_store.add_custody_event(
                conn,
                tenant_id=str(user.tenant_id),
                sample_id=sample_id,
                actor_id=str(user.user_id),
                event_type=f"status:{payload.target_status}",
                location=payload.location,
                condition_notes=payload.condition_notes,
                seal_id=payload.seal_id,
            )
        if payload.target_status == "published" and is_soil:
            publish_payload = (sample, {r["analyte"]: r["value_json"] for r in publish_rows})
        if publish_payload:
            try:
                receipt = await publish_soil_lab_evidence(
                    tenant_id=str(user.tenant_id),
                    field_id=publish_payload[0]["field_id"],
                    sample=publish_payload[0],
                    results=publish_payload[1],
                    result_rows=publish_rows or [],
                    correction_reason=payload.condition_notes,
                )
            except Exception as exc:
                raise HTTPException(502, f"soil evidence publication failed: {exc}") from exc
            await lab_store.mark_soil_results_published(
                conn,
                tenant_id=str(user.tenant_id),
                observation_by_analyte=receipt["observation_by_analyte"],
                result_by_analyte=receipt["result_by_canonical"],
            )
            row["soil_evidence_receipt"] = receipt
    return row


@router.get("/api/v1/fields/{field_id}/lab-context")
async def field_lab_context(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        latest_soil = await lab_store.latest_soil_analysis(
            conn, tenant_id=str(user.tenant_id), field_id=field_id
        )
        latest_water = await lab_store.latest_water_analysis(
            conn, tenant_id=str(user.tenant_id), field_id=field_id
        )
    if latest_soil:
        ec_method = latest_soil.pop("ec_extraction_method", None)
        latest_soil = _interpret_lab_values(latest_soil, ec_method)
    return lab_decision_context(soil=latest_soil, water=latest_water)
