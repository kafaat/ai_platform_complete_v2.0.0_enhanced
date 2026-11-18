#!/usr/bin/env python3
"""
SAHOOL Edge Inference Service v9.1 (FIXED)
"""

import asyncio
import importlib.util
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import model_artifact_gate as artifact_gate
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from models.errors import ImageTooLarge, ModelNotProvisioned, ModelOutputContractError
from models.model_bundle import ModelBundle, ModelBundleStore
from models.pest_detector import EdgePestDetector
from models.yield_estimator import EdgeYieldEstimator
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sync_service import CloudSyncService

# بلا try/except قصداً: غيابُ الوحدة عطلُ توصيلٍ يُرى لا يُبتلَع.
from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    verify_tenant_assertion,
)
from shared.security.trusted_tenant import service_token_ok

logger = logging.getLogger(__name__)


# C3 FIX: عرّف lifespan قبل استخدامه في FastAPI(lifespan=...) — كان NameError
# عند الاستيراد (الخدمة لا تُقلع أصلاً). نقلناه أعلى تعريف app.
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if not OFFLINE_MODE:
        # احتفظ بالمرجع لمنع GC المبكّر للمهمّة الخلفيّة
        task = app.state.sync_task = asyncio.create_task(_periodic_sync())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(lifespan=lifespan, title="SAHOOL Edge Inference", version="2026.1")

DEVICE = os.getenv("EDGE_DEVICE", "rpi5")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "3600"))
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE", "/models")
EDGE_READINESS_MODE = (
    os.getenv("EDGE_READINESS_MODE", "partial").strip().lower()
)  # partial | strict
EDGE_PRODUCTION_REQUIRED = os.getenv("EDGE_PRODUCTION_REQUIRED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_bundles = ModelBundleStore()
_sync_service: CloudSyncService | None = None


def get_pest_detector(bundle: ModelBundle) -> EdgePestDetector:
    return EdgePestDetector(bundle.weight_path, device=DEVICE, bundle=bundle)


def get_yield_estimator(bundle: ModelBundle) -> EdgeYieldEstimator:
    return EdgeYieldEstimator(bundle.weight_path, device=DEVICE, bundle=bundle)


def get_sync_service() -> CloudSyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = CloudSyncService(
            cloud_url=os.getenv("SAHOOL_CLOUD_URL", "https://api.sahool.local"),
            token=os.getenv("EDGE_SYNC_TOKEN", ""),
            # W0-07: tenant-carrying envelopes are sent as a service (agent token + assertion).
            agent_token=os.getenv("SAHOOL_AGENT_TOKEN", ""),
            # Its own key for the edge -> platform hop, never the inbound EDGE_TENANT_ASSERTION_KEY.
            assertion_key=os.getenv("EDGE_SYNC_TENANT_ASSERTION_KEY", ""),
            assertion_key_id=os.getenv("EDGE_SYNC_TENANT_ASSERTION_KEY_ID", "current"),
            # قابل للضبط: الحاوية تستخدم /data (volume)؛ بيئات الاختبار/CI بلا صلاحيّة
            # كتابة على الجذر تمرّر EDGE_SYNC_DIR لمجلّد مؤقّت.
            sync_dir=os.getenv("EDGE_SYNC_DIR", "/data/sync_queue"),
        )
    return _sync_service


def _model_path(env_name: str, default_name: str) -> str:
    return os.getenv(env_name, f"{MODEL_CACHE_DIR}/{default_name}")


#: اسمُ الملفّ ⇐ (متغيّرُ المسار · متغيّرُ البصمة المعتمدة). المصدرُ الواحد للحكم.
_MODEL_ENV = {
    "pest_detector_int8.onnx": ("PEST_MODEL_PATH", "PEST_MODEL_SHA256"),
    "yield_estimator_int8.onnx": ("YIELD_MODEL_PATH", "YIELD_MODEL_SHA256"),
}


def _resolve_model(default_name: str) -> tuple[dict[str, object], ModelBundle | None]:
    path_env, sha_env = _MODEL_ENV[default_name]
    return _bundles.resolve(
        path=_model_path(path_env, default_name),
        sha_env=sha_env,
        runtime_available=importlib.util.find_spec("onnxruntime") is not None,
        device=DEVICE,
    )


def _model_capability(default_name: str) -> dict[str, object]:
    capability, _ = _resolve_model(default_name)
    return capability


def _require_approved_model(default_name: str) -> tuple[dict[str, object], ModelBundle]:
    capability, bundle = _resolve_model(default_name)
    if bundle is not None:
        return capability, bundle
    raise HTTPException(
        503,
        {
            "reason": capability["reason"],
            "model": default_name,
            "detail_ar": "حزمة النموذج غير جاهزة للاستدلال على هذه الحافة.",
        },
    )


def capabilities_payload() -> dict[str, object]:
    pest = _model_capability("pest_detector_int8.onnx")
    yld = _model_capability("yield_estimator_int8.onnx")
    sync = get_sync_service()
    capabilities = {
        "pest_detect": pest,
        "yield_estimate": yld,
    }
    active_count = sum(1 for cap in capabilities.values() if cap["active"])
    return {
        "service": "edge-inference",
        "schema_version": "2026-07-09.capabilities",
        "device": DEVICE,
        "offline_mode": OFFLINE_MODE,
        "readiness_mode": EDGE_READINESS_MODE,
        "production_required": EDGE_PRODUCTION_REQUIRED,
        "agent_token_configured": bool(AGENT_TOKEN),
        "sync_token_configured": bool(os.getenv("EDGE_SYNC_TOKEN")),
        "tenant_assertion_configured": len(os.getenv("EDGE_TENANT_ASSERTION_KEY", "")) >= 32,
        "sync_tenant_assertion_configured": (
            len(os.getenv("EDGE_SYNC_TENANT_ASSERTION_KEY", "")) >= 32
        ),
        "device_identity_configured": bool(os.getenv("EDGE_DEVICE_ID", "").strip()),
        "capabilities": capabilities,
        "active_capability_count": active_count,
        "required_capability_count": len(capabilities),
        "all_required_models_active": active_count == len(capabilities),
        "queue_size": sync.queue_size(),
    }


# مصدرٌ واحد لقيود المدخل: تُطبَّق على نماذج الطلب وعلى معامِلات Form() معاً، فلا يُشدَّد
# أحدهما وحده فيعود مسار 500 (قيدٌ في النموذج لا يراه Form يرفع ValidationError خاماً).
FIELD_ID_LIMITS = {"min_length": 1, "max_length": 50}
CROP_PATTERN = "^(wheat|barley|maize|sorghum|millet|rice|potato|tomato|coffee)$"
CONFIDENCE_LIMITS = {"ge": 0.1, "le": 1.0}
IMAGE_COUNT_LIMITS = {"ge": 1, "le": 20}
GROWTH_STAGE_PATTERN = "^(seedling|vegetative|flowering|grain_filling|maturity)$"


class PestDetectionRequest(BaseModel):
    # field_id/crop اختياريّان: إطارُ بثٍّ غير مربوط بحقل يُكشَف ولا يُزامَن (المنصّة
    # تردّ 404 على حقلٍ غير موجود)، ومحصولٌ مجهول يبقى None لا «wheat» مُفترَضاً.
    field_id: str | None = Field(default=None, **FIELD_ID_LIMITS)
    crop: str | None = Field(default=None, pattern=CROP_PATTERN)
    confidence_threshold: float = Field(default=0.6, **CONFIDENCE_LIMITS)
    return_image: bool = False


class YieldEstimationRequest(BaseModel):
    field_id: str = Field(**FIELD_ID_LIMITS)
    crop: str
    image_count: int = Field(default=5, **IMAGE_COUNT_LIMITS)
    growth_stage: str = Field(default="vegetative", pattern=GROWTH_STAGE_PATTERN)


class EdgeHealthCheck(BaseModel):
    status: str = "alive"
    service: str = "edge-inference"
    device: str
    offline_mode: bool
    models_loaded: dict[str, bool]
    last_sync: str | None
    queue_size: int
    uptime_seconds: float


_start_time = time.time()


@app.get("/healthz")
async def health_check() -> EdgeHealthCheck:
    sync = get_sync_service()
    capabilities = (await run_in_threadpool(capabilities_payload))["capabilities"]
    return EdgeHealthCheck(
        status="alive",
        service="edge-inference",
        device=DEVICE,
        offline_mode=OFFLINE_MODE,
        models_loaded={
            "pest_detector": bool(capabilities["pest_detect"]["active"]),
            "yield_estimator": bool(capabilities["yield_estimate"]["active"]),
        },
        last_sync=sync.last_sync.isoformat() if sync.last_sync else None,
        queue_size=sync.queue_size(),
        uptime_seconds=time.time() - _start_time,
    )


# FIXED: Use Form fields instead of Pydantic model with UploadFile

AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — معطّل بأمان")
    if not service_token_ok(x_agent_token, AGENT_TOKEN):
        raise HTTPException(401, "توكن خدمة غير صالح")


# W0-07 (scout-1): a field-bound result is synced under the tenant its caller signed for, not under
# the one tenant of a shared EDGE_SYNC_TOKEN. Callers: video-processor (the stream's verified
# tenant) and sahool-platform's BFF (the verified user's tenant).
_DEFAULT_TENANT_CALLERS = "video-processor,sahool-platform"


def _verified_caller_tenant(
    path: str,
    assertion: str | None,
    tenant_id: str | None,
    caller: str | None,
    request_id: str | None,
) -> str | None:
    """The tenant this request may sync for, or None when the caller sent no assertion.

    None ⇒ the detection is returned but never synced (``not_synced_no_tenant``). An assertion
    that is present but wrong is a refusal (403), and one that cannot be checked is 503: nothing
    is written for a tenant this edge did not verify. ``path`` is the route's own path, so an
    assertion minted for another route does not verify here.
    """
    if not assertion:
        return None
    key = os.getenv("EDGE_TENANT_ASSERTION_KEY", "")
    if len(key) < 32:
        raise HTTPException(503, "edge_tenant_assertion_unavailable")
    keys = {os.getenv("EDGE_TENANT_ASSERTION_KEY_ID", "current"): key}
    previous = os.getenv("EDGE_TENANT_ASSERTION_PREVIOUS_KEY", "")
    if len(previous) >= 32:
        keys[os.getenv("EDGE_TENANT_ASSERTION_PREVIOUS_KEY_ID", "previous")] = previous
    allowed = {
        s.strip()
        for s in os.getenv("EDGE_INFERENCE_ALLOWED_CALLERS", _DEFAULT_TENANT_CALLERS).split(",")
        if s.strip()
    }
    if (caller or "") not in allowed:
        raise HTTPException(403, "caller_not_allowed")
    try:
        verify_tenant_assertion(
            assertion,
            keys,
            caller or "",
            tenant_id or "",
            expected_method="POST",
            expected_path=path,
            expected_request_id=request_id or "",
        )
    except TenantAssertionError as exc:
        raise HTTPException(403, f"invalid_tenant_assertion:{exc}") from None
    return tenant_id


async def _sync_or_status(result_type: str, result: dict, tenant_id: str | None) -> str:
    """Queue/send a field-bound result and say what happened.

    W0-08 (scout-2): no device identity is not a reason to throw the detection away with a 503
    after inference; the result goes back with ``not_synced_identity`` and nothing is queued,
    because a queued observation without a device cannot be attributed later."""
    if tenant_id is None:
        return "not_synced_no_tenant"
    sync = get_sync_service()
    if not sync.device_id_for(result):
        return "not_synced_identity"
    try:
        if not OFFLINE_MODE:
            synced = await sync.sync_result(result_type, result, tenant_id=tenant_id)
            return "synced" if synced else "queued"
        sync.queue_result(result_type, result, tenant_id=tenant_id)
        return "queued"
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "edge_sync_queue_or_identity_unavailable") from exc


# المصادقة تبعيّةٌ لا نداءٌ داخل المعالِج: FastAPI يحلّ التبعيّات قبل رفع أخطاء تحقّق
# Form، فالطالب بلا توكن يتلقّى 401 لا 422 يكشف مخطّط القيود (نمط المصادقة قبل التحقّق).
@app.post("/v1/inference/pest-detect", dependencies=[Depends(_require_service_token)])
async def detect_pest(
    file: UploadFile = File(...),
    field_id: str | None = Form(None, **FIELD_ID_LIMITS),
    crop: str | None = Form(None, pattern=CROP_PATTERN),
    confidence_threshold: float = Form(0.6, **CONFIDENCE_LIMITS),
    return_image: bool = Form(False),
    x_tenant_assertion: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
    x_service_name: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    request = PestDetectionRequest(
        field_id=field_id,
        crop=crop,
        confidence_threshold=confidence_threshold,
        return_image=return_image,
    )
    tenant_id = (
        _verified_caller_tenant(
            "/v1/inference/pest-detect",
            x_tenant_assertion,
            x_tenant_id,
            x_service_name,
            x_request_id,
        )
        if request.field_id is not None
        else None
    )
    pest_capability, bundle = await run_in_threadpool(
        _require_approved_model, "pest_detector_int8.onnx"
    )
    detector = get_pest_detector(bundle)
    # تحقّق من المدخل: حدّ الحجم (منع DoS) + نوع الملفّ. القراءة نفسها محدودة بالسقف+1
    # كي لا يُحمَّل رفعٌ ضخم كاملاً في الذاكرة قبل رفضه.
    MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB كافٍ لصور المحاصيل
    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "حجم الصورة يتجاوز 10MB")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "الملفّ يجب أن يكون صورة")
    start = time.time()
    try:
        detections = detector.predict(
            image_bytes, confidence_threshold=request.confidence_threshold
        )
    except ModelNotProvisioned as e:
        # لا نموذج ONNX حقيقيّ ⇒ 503 صريح بدل كشوف مُختلَقة (أمانةً مع المزارع)
        raise HTTPException(
            503,
            "نموذج كشف الآفات غير مُجهَّز على هذه الحافة — المسار معطّل بأمانة "
            "حتّى توفير نموذج ONNX (لا تُرجَع كشوف مُختلَقة).",
        ) from e
    except ModelOutputContractError as e:
        # W1-19 (scout-9): خرجُ النموذج لا يطابق manifest العلامات (أو الـmanifest تالف) ⇒
        # رقمُ الصنف لا يعني اسماً معروفاً. 503 مُسمًّى، لا قصٌّ إلى القائمة الأقصر ولا 400.
        raise HTTPException(
            503,
            {
                "reason": "pest_model_label_contract_violation",
                "model": "pest_detector_int8.onnx",
                "detail": str(e),
            },
        ) from e
    except ImageTooLarge as e:
        raise HTTPException(413, "أبعاد الصورة تتجاوز سقف البكسلات المسموح") from e
    except Exception as e:
        # صورة تالفة/غير صالحة → 400 واضح بدل 500
        raise HTTPException(400, "تعذّر معالجة الصورة — تأكّد أنّها صورة صالحة") from e
    inference_time_ms = (time.time() - start) * 1000
    result = {
        "field_id": request.field_id,
        "crop": request.crop,
        "detections": detections,
        "inference_time_ms": round(inference_time_ms, 2),
        "device": DEVICE,
        "timestamp": datetime.now(UTC).isoformat(),
        "model_version": detector.version,
        # نسبُ الكشف: المصنوعة (بصمة البوّابة) · بصمة الصورة · العتبة — تُزامَن مع النتيجة
        # فتكتبها المنصّة صفّاً لكلّ كشفٍ في detection_provenance (v239).
        "provenance": {
            **artifact_gate.detection_provenance(
                model_id="pest_detector_int8.onnx",
                model_version=detector.version,
                capability=pest_capability,
                image_bytes=image_bytes,
                threshold=request.confidence_threshold,
            ),
            "bundle_sha256": bundle.sha256,
        },
    }
    alert = artifact_gate.high_confidence_alert(detections)
    if request.field_id is None:
        # لا حقل ⇒ لا مزامنة: المنصّة لا تقبل نتيجةً بلا حقلٍ موجود، وإعادة محاولتها
        # بلا نهاية كانت تُنمّي طابور المزامنة. الكشف نفسه يُرجَع للمستدعي.
        return {**result, "alert_ar": alert, "sync_status": "not_synced_no_field"}
    status = await _sync_or_status("pest_detection", result, tenant_id)
    return {**result, "alert_ar": alert, "sync_status": status}


@app.post("/v1/inference/yield-estimate", dependencies=[Depends(_require_service_token)])
async def estimate_yield(
    files: list[UploadFile] = File(...),
    field_id: str = Form(..., **FIELD_ID_LIMITS),
    crop: str = Form("wheat"),
    image_count: int = Form(5, **IMAGE_COUNT_LIMITS),
    growth_stage: str = Form("vegetative", pattern=GROWTH_STAGE_PATTERN),
    x_tenant_assertion: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
    x_service_name: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    request = YieldEstimationRequest(
        field_id=field_id, crop=crop, image_count=image_count, growth_stage=growth_stage
    )
    tenant_id = _verified_caller_tenant(
        "/v1/inference/yield-estimate",
        x_tenant_assertion,
        x_tenant_id,
        x_service_name,
        x_request_id,
    )
    _, bundle = await run_in_threadpool(_require_approved_model, "yield_estimator_int8.onnx")
    estimator = get_yield_estimator(bundle)
    if len(files) < request.image_count:
        raise HTTPException(
            status_code=400, detail=f"Expected {request.image_count} images, got {len(files)}"
        )
    all_features = []
    MAX_IMAGE_BYTES = 10 * 1024 * 1024
    for file in files[: request.image_count]:
        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "حجم إحدى الصور يتجاوز 10MB")
        try:
            features = estimator.extract_features(image_bytes)
        except ImageTooLarge as e:
            raise HTTPException(413, "أبعاد إحدى الصور تتجاوز سقف البكسلات المسموح") from e
        except Exception as e:
            raise HTTPException(400, "تعذّر معالجة إحدى الصور — تأكّد أنّها صور صالحة") from e
        all_features.append(features)
    start = time.time()
    try:
        yield_prediction = estimator.predict_yield(
            features=all_features, crop=request.crop, growth_stage=request.growth_stage
        )
    except ValueError as e:
        # لا قياساتٌ بصريّة ⇒ مُدخَلٌ غيرُ صالح (422)، لا غلّةٌ صفر ولا 500 خام
        raise HTTPException(422, "yield_features_invalid_or_empty") from e
    except ModelNotProvisioned as e:
        # لا نموذج ONNX حقيقيّ ⇒ 503 صريح بدل رقم غلّة مُختلَق
        raise HTTPException(
            503,
            "نموذج تقدير الغلّة غير مُجهَّز على هذه الحافة — المسار معطّل بأمانة "
            "حتّى توفير نموذج ONNX (لا تُرجَع أرقام مُختلَقة).",
        ) from e
    inference_time_ms = (time.time() - start) * 1000
    result = {
        "field_id": request.field_id,
        "crop": request.crop,
        "growth_stage": request.growth_stage,
        "sample_images": len(all_features),
        "model_bundle_sha256": bundle.sha256,
        "model_artifact_sha256": bundle.weight_sha256,
        # لا ±15٪ مُصطنَعة — الفاصلُ يُنشَر إن أنتجه النموذج، وإلّا None بقيدٍ مسمًّى
        **artifact_gate.shape_yield_result(yield_prediction),
        "inference_time_ms": round(inference_time_ms, 2),
        "device": DEVICE,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    status = await _sync_or_status("yield_estimate", result, tenant_id)
    return {**result, "sync_status": status}


@app.post("/v1/sync/trigger")
async def trigger_sync(x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    if OFFLINE_MODE:
        return {
            "status": "offline",
            "message": "Cannot sync in offline mode. Results queued locally.",
        }
    sync = get_sync_service()
    synced_count = await sync.process_queue()
    return {
        "status": "success",
        "synced_items": synced_count,
        "remaining_queue": sync.queue_size(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


# FIXED: lifespan مُعرّف قبل app (أعلى الملفّ) — كان NameError هنا (C3)


async def _periodic_sync():
    while True:
        await asyncio.sleep(SYNC_INTERVAL)
        try:
            sync = get_sync_service()
            if sync.queue_size() > 0:
                await sync.process_queue()
        except Exception as e:
            logger.info(f"[Edge] Sync error: {e}")


@app.get("/capabilities")
def capabilities():
    return capabilities_payload()


@app.get("/metrics")
async def metrics():
    """مقاييس Prometheus. الهدفُ مُعلَنٌ في `prometheus/prometheus.yml` منذ البداية
    وكانت النقطةُ غائبة ⇒ ٤٠٤ ⇒ `up=0` دائماً، وقاعدةُ التنبيه على `up==0` تُطلِق
    أبداً فتُدرِّب المُشغِّل على تجاهلها. «مُعلَنٌ ليس يعمل»."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/readyz")
async def readyz(response: Response):
    payload = await run_in_threadpool(capabilities_payload)
    any_model_active = payload["active_capability_count"] > 0
    all_models_active = payload["all_required_models_active"] is True
    token_ready = payload["agent_token_configured"] is True

    effective_strict = EDGE_READINESS_MODE == "strict" or EDGE_PRODUCTION_REQUIRED
    if effective_strict:
        status = "ready" if token_ready and all_models_active else "degraded"
        if status != "ready":
            response.status_code = 503
        model_policy = "strict-readiness; all configured inference contracts require ONNX models before the service is ready"
        if EDGE_PRODUCTION_REQUIRED:
            model_policy += "; EDGE_PRODUCTION_REQUIRED forces strict readiness"
    else:
        status = "ready" if token_ready and any_model_active else "degraded"
        model_policy = "partial-readiness; inference endpoints fail closed with 503 when required ONNX models are absent"

    return {
        "status": status,
        "version": "9.1.0",
        "service": "edge-inference",
        "model_policy": model_policy,
        **payload,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
