# SAHOOL — Final ExG-assisted SAM2 Auto Boundary Improvements

## Scope
This patch finalizes the Auto Boundary flow so the **Auto** button performs vegetation-aware pre-processing before calling the external SAM2/GeoSAM inference service.

## Final additions

### 1. Safer ExG preprocessing for real map screenshots
- Added configurable image guards:
  - `EXG_MAX_SIDE` default: `1280`
  - `EXG_MAX_IMAGE_PIXELS` default: `12000000`
- Large Leaflet viewport screenshots are resized before Python connected-component analysis.
- The returned enhanced image, boxes, and positive points all stay in the same processed-image coordinate space.
- Metadata now includes:
  - `original_size`
  - `processed_size`
  - `scale`

### 2. Cleaner vegetation masks without OpenCV dependency
- Added Pillow-based binary opening + closing.
- Removes isolated noisy pixels.
- Seals small holes in vegetation regions.
- Keeps the service lightweight: no `torch`, no `opencv`, no `scipy` inside `field-segmentation`.

### 3. More reliable SAM2 prompts
- Candidate boxes are padded slightly so SAM2 receives context around green components.
- Low-confidence ExG now also triggers when no valid vegetation candidates are found.
- The service still never fabricates field geometry; SAM2/GeoSAM must return the polygon.

### 4. Cheaper request tracing
- `request_hash` no longer serializes the full base64 image directly.
- It hashes only image length + image digest inside the trace payload.
- This keeps request correlation deterministic without wasting CPU on large screenshots.

### 5. Compose wiring
Added ExG runtime limits to:
- `docker-compose.v9.yml`
- `docker-compose.v9.gpu.yml`

### 6. Tests
Field-segmentation test suite result:

```text
29 passed in 3.55s
```

New coverage includes:
- data URL image input
- processed/original image size metadata
- viewport downscaling
- prompt boxes staying inside processed image bounds

## Final runtime flow

```text
Auto click
→ Leaflet viewport capture when CORS allows
→ field-segmentation /segment
→ ExG = 2G - R - B
→ morphology cleanup
→ vegetation candidate extraction
→ padded boxes + positive points
→ enhanced RGB image to SAM2/GeoSAM
→ validate returned GeoJSON polygon
→ editable preview in frontend
```

## Honesty boundary
If `SEGMENTATION_BACKEND` or `SEGMENTATION_INFERENCE_URL` is not configured, the service still returns a truthful `503 model_not_configured`. No fake polygon or fallback geometry is generated.
