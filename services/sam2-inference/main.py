"""SAHOOL SAM2 inference service entrypoint.

P2 decomposition shell: heavy CUDA/SAM2/STAC/raster/post-processing runtime lives in
``sam2_runtime.py``. This file owns only FastAPI routes and service lifecycle.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, Header, HTTPException

import sam2_runtime as rt

app = FastAPI(title="SAHOOL SAM2 Inference", version=rt.VERSION)


@app.on_event("startup")
async def _startup() -> None:
    rt._load_model()


@app.post("/predict")
async def predict(req: rt.PredictRequest, x_agent_token: str = Header(None)):
    """يشغّل SAM2 لإنتاج مضلّع الحقل. يطابق عقد field-segmentation تماماً."""
    started = time.perf_counter()
    rt._require_service_token(x_agent_token)

    if rt._PREDICTOR is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "model_not_loaded",
                "note_ar": "نموذج SAM2 غير محمّل (أوزان ناقصة أو لا CUDA)",
                "load_error_present": bool(rt._MODEL_LOAD_ERROR),
            },
        )

    import numpy as np
    import torch

    image_url = rt._resolve_image_url(req.image_ref, req.field_bbox)
    rgb, transform, crs = rt._read_rgb(image_url, req.field_bbox)
    img_h, img_w = rgb.shape[0], rgb.shape[1]
    if img_h < 2 or img_w < 2:
        raise HTTPException(
            status_code=503,
            detail={"error": "image_too_small", "note_ar": "نافذة الصورة صغيرة جداً"},
        )

    point_coords, point_labels, box = rt._build_prompt(
        req.mode, req.user_polygon, transform, crs, img_h, img_w
    )

    try:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            rt._PREDICTOR.set_image(rgb)
            masks, scores, _ = rt._PREDICTOR.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                box=box,
                multimask_output=True,
            )
    except Exception as e:  # noqa: BLE001
        rt.logger.warning("فشل استدلال SAM2: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "inference_error", "detail": f"{type(e).__name__}: {e}"},
        ) from e

    if masks is None or len(masks) == 0:
        raise HTTPException(
            status_code=500,
            detail={"error": "no_mask", "note_ar": "SAM2 لم يُنتج قناعاً"},
        )

    best_idx = int(np.argmax(scores)) if scores is not None and len(scores) else 0
    best_mask = np.asarray(masks[best_idx]).astype(np.uint8)
    confidence = float(scores[best_idx]) if scores is not None and len(scores) else None
    geometry = rt._mask_to_polygon(best_mask, transform, crs)

    vertices_after = (
        len(geometry.get("coordinates", [[]])[0]) if isinstance(geometry, dict) else None
    )
    metadata = {
        "source": "sam2",
        "mode": req.mode,
        "model": "sam2",
        "model_version": rt.VERSION,
        "checkpoint": os.path.basename(rt.SAM2_CHECKPOINT),
        "model_cfg": rt.SAM2_MODEL_CFG,
        "post_processing": {
            "simplify_tolerance_m": rt.SIMPLIFY_TOLERANCE_M,
            "dedup_tolerance_m": rt.DEDUP_TOLERANCE_M,
            "preserve_topology": True,
        },
        "vertices_after": vertices_after,
        "mask_area_px": int(best_mask.sum()),
        "inference_ms": round((time.perf_counter() - started) * 1000.0, 2),
    }
    return {"geometry": geometry, "confidence": confidence, "metadata": metadata}


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "sam2-inference", "version": rt.VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def readyz():
    loaded = rt._PREDICTOR is not None
    return {
        "status": "ready" if loaded else "degraded",
        "service": "sam2-inference",
        "implemented_runtime": loaded,
        "model_loaded": loaded,
        "load_error_present": bool(rt._MODEL_LOAD_ERROR),
        "reason_code": rt._MODEL_LOAD_REASON_CODE,
        "reason": rt._MODEL_LOAD_ERROR,
        "checkpoint_expected": rt.SAM2_CHECKPOINT,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
