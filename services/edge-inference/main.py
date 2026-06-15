#!/usr/bin/env python3
"""
SAHOOL Edge Inference Service v9.1 (FIXED)
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from models.errors import ModelNotProvisioned
from models.pest_detector import EdgePestDetector
from models.yield_estimator import EdgeYieldEstimator
from pydantic import BaseModel, Field
from sync_service import CloudSyncService

logger = logging.getLogger(__name__)


# C3 FIX: عرّف lifespan قبل استخدامه في FastAPI(lifespan=...) — كان NameError
# عند الاستيراد (الخدمة لا تُقلع أصلاً). نقلناه أعلى تعريف app.
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not OFFLINE_MODE:
        # احتفظ بالمرجع لمنع GC المبكّر للمهمّة الخلفيّة
        app.state.sync_task = asyncio.create_task(_periodic_sync())
    yield


app = FastAPI(lifespan=lifespan, title="SAHOOL Edge Inference", version="2026.1")

DEVICE = os.getenv("EDGE_DEVICE", "rpi5")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "3600"))
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE", "/models")

_pest_detector: EdgePestDetector | None = None
_yield_estimator: EdgeYieldEstimator | None = None
_sync_service: CloudSyncService | None = None


def get_pest_detector() -> EdgePestDetector:
    global _pest_detector
    if _pest_detector is None:
        _pest_detector = EdgePestDetector(
            model_path=f"{MODEL_CACHE_DIR}/pest_detector_quantized.onnx", device=DEVICE
        )
    return _pest_detector


def get_yield_estimator() -> EdgeYieldEstimator:
    global _yield_estimator
    if _yield_estimator is None:
        _yield_estimator = EdgeYieldEstimator(
            model_path=f"{MODEL_CACHE_DIR}/yield_estimator_quantized.onnx", device=DEVICE
        )
    return _yield_estimator


def get_sync_service() -> CloudSyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = CloudSyncService(
            cloud_url=os.getenv("SAHOOL_CLOUD_URL", "https://api.sahool.local"),
            token=os.getenv("EDGE_SYNC_TOKEN", ""),
            sync_dir="/data/sync_queue",
        )
    return _sync_service


class PestDetectionRequest(BaseModel):
    field_id: str = Field(min_length=1, max_length=64)
    crop: str = Field(
        default="wheat", pattern="^(wheat|barley|maize|sorghum|millet|rice|potato|tomato|coffee)$"
    )
    confidence_threshold: float = Field(default=0.6, ge=0.1, le=1.0)
    return_image: bool = False


class YieldEstimationRequest(BaseModel):
    field_id: str = Field(min_length=1, max_length=64)
    crop: str
    image_count: int = Field(default=5, ge=1, le=20)
    growth_stage: str = Field(
        default="vegetative", pattern="^(seedling|vegetative|flowering|grain_filling|maturity)$"
    )


class EdgeHealthCheck(BaseModel):
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
    return EdgeHealthCheck(
        device=DEVICE,
        offline_mode=OFFLINE_MODE,
        models_loaded={
            "pest_detector": _pest_detector is not None,
            "yield_estimator": _yield_estimator is not None,
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
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


@app.post("/inference/pest-detect")
async def detect_pest(
    file: UploadFile = File(...),
    field_id: str = Form("unknown"),
    crop: str = Form("wheat"),
    confidence_threshold: float = Form(0.6),
    return_image: bool = Form(False),
    x_agent_token: str = Header(None),
):
    _require_service_token(x_agent_token)
    request = PestDetectionRequest(
        field_id=field_id,
        crop=crop,
        confidence_threshold=confidence_threshold,
        return_image=return_image,
    )
    detector = get_pest_detector()
    image_bytes = await file.read()
    # تحقّق من المدخل: حدّ الحجم (منع DoS) + نوع الملفّ
    MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB كافٍ لصور المحاصيل
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
    }
    sync = get_sync_service()
    if not OFFLINE_MODE:
        await sync.sync_result("pest_detection", result)
    else:
        sync.queue_result("pest_detection", result)
    alert = None
    high_conf = [d for d in detections if d["confidence"] > 0.8]
    if high_conf:
        top = high_conf[0]
        alert = f"🐛 **تنبيه آفة عالية الثقة!**\n\nالآفة المكتشفة: **{top['arabic_name']}**\nالثقة: {top['confidence']:.0%}\nالموقع في الصورة: {top['bbox']}\n\nالإجراء المقترح: {top['recommended_action']}"
    return {**result, "alert_ar": alert, "sync_status": "synced" if not OFFLINE_MODE else "queued"}


@app.post("/inference/yield-estimate")
async def estimate_yield(
    files: list[UploadFile] = File(...),
    field_id: str = Form("unknown"),
    crop: str = Form("wheat"),
    image_count: int = Form(5),
    growth_stage: str = Form("vegetative"),
    x_agent_token: str = Header(None),
):
    _require_service_token(x_agent_token)
    request = YieldEstimationRequest(
        field_id=field_id, crop=crop, image_count=image_count, growth_stage=growth_stage
    )
    estimator = get_yield_estimator()
    if len(files) < request.image_count:
        raise HTTPException(
            status_code=400, detail=f"Expected {request.image_count} images, got {len(files)}"
        )
    all_features = []
    MAX_IMAGE_BYTES = 10 * 1024 * 1024
    for file in files[: request.image_count]:
        image_bytes = await file.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "حجم إحدى الصور يتجاوز 10MB")
        try:
            features = estimator.extract_features(image_bytes)
        except Exception as e:
            raise HTTPException(400, "تعذّر معالجة إحدى الصور — تأكّد أنّها صور صالحة") from e
        all_features.append(features)
    start = time.time()
    try:
        yield_prediction = estimator.predict_yield(
            features=all_features, crop=request.crop, growth_stage=request.growth_stage
        )
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
        "estimated_yield_kg_ha": round(yield_prediction["yield_kg_ha"], 2),
        "confidence_interval": {
            "lower": round(yield_prediction["yield_kg_ha"] * 0.85, 2),
            "upper": round(yield_prediction["yield_kg_ha"] * 1.15, 2),
        },
        "biomass_proxy": round(yield_prediction.get("biomass_proxy", 0), 2),
        "plant_count_estimate": int(yield_prediction.get("plant_count", 0)),
        "inference_time_ms": round(inference_time_ms, 2),
        "device": DEVICE,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    sync = get_sync_service()
    if not OFFLINE_MODE:
        await sync.sync_result("yield_estimate", result)
    else:
        sync.queue_result("yield_estimate", result)
    return {**result, "sync_status": "synced" if not OFFLINE_MODE else "queued"}


@app.post("/sync/trigger")
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


@app.get("/readyz")
async def readyz():
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
