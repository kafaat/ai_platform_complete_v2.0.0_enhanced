# ExG-assisted SAM2 Auto Boundary — 2026-07-03

Implemented the requested automatic field-boundary flow:

```text
Auto click
→ capture current map viewport when possible
→ send image_base64 + preprocessing=exg to field-segmentation
→ apply Excess Green Index (ExG) before SAM2
→ extract vegetation candidates as SAM2 boxes/positive points
→ call the real SAM2/GeoSAM inference backend
→ validate returned Polygon normally
→ expose preprocessing metadata to the UI/audit trail
```

## Backend

Files changed:

- `services/field-segmentation/main.py`
- `services/field-segmentation/exg_preprocess.py`
- `services/field-segmentation/requirements.txt`
- `services/field-segmentation/test_segmentation.py`
- `services/field-segmentation/test_exg_preprocess.py`

New request fields:

```json
{
  "image_base64": "...optional PNG/JPEG...",
  "preprocessing": "exg",
  "fallback_to_original_on_low_exg": true
}
```

ExG behavior:

- Uses `ExG = 2G - R - B`.
- Produces an RGB vegetation-enhanced image for SAM2 instead of a naked binary mask.
- Extracts vegetation candidates as:
  - `boxes`
  - `positive_points`
  - `multimask_output=true`
- Keeps the existing honesty contract: no polygon is fabricated locally. SAM2/GeoSAM still owns inference, and returned geometry is still validated through `normalize_polygon`.
- If ExG confidence is low and fallback is enabled, the original image is sent and metadata records `exg_low_confidence_fallback_original`.
- If the frontend cannot provide an image because a tile provider blocks CORS, metadata records `exg_skipped_no_image` and the service still calls SAM2 with the existing bbox/image_ref contract.

Returned metadata now includes:

```json
{
  "preprocessing": "exg",
  "vegetation_ratio": 0.25,
  "low_confidence": false,
  "candidate_count": 1,
  "candidates": [
    {
      "bbox": [28, 24, 76, 72],
      "centroid": [52, 48],
      "area_px": 2304,
      "circularity": 0.8,
      "rectangularity": 1.0,
      "confidence": 0.91
    }
  ]
}
```

## Frontend

Files changed:

- `frontend/src/components/AddFieldWithMap.tsx`
- `frontend/src/services/api.ts`

The Auto/Hybrid segmentation button now sends:

```ts
{
  mode: segReqMode,
  bbox,
  preprocessing: 'exg',
  fallback_to_original_on_low_exg: true,
  image_base64 // when current tile layer allows CORS capture
}
```

The map tile layer now requests `crossOrigin="anonymous"` so CORS-friendly providers such as Mapbox can be captured. Providers that do not allow canvas export, such as many Google tile configurations, fail safely without breaking the segmentation request.

Also fixed the frontend segmentation error classifier so FastAPI-style errors like:

```json
{"detail":{"error":"model_not_configured"}}
```

are correctly recognized as `model_not_configured` instead of generic unavailable errors.

## Verification

Executed:

```bash
cd services/field-segmentation
PYTHONPATH=. pytest -q
```

Result:

```text
27 passed in 2.45s
```

Frontend typecheck was not executed because `frontend/node_modules` is not present in this archive environment.
