# V59.5 — FTW Field-Boundary Backend Scaffold

Replaces the v59 bbox-rectangle **placeholder** with a **pluggable, fail-safe backend
layer** so a real Sentinel-2 segmentation model (Fields of The World / FTW-style) can
be dropped in **without changing the agent tool schema**. Derived from the deep-research
pass (FTW = the strongest permissive, S2/EPSG:4326-compatible option for v59).

## What shipped (in-sandbox, deterministic, CI-green)
- `services/ai_agronomist/field_boundary_backends.py`
  - `pixel_to_lonlat` — tile-affine pixel → EPSG:4326 (row 0 = north).
  - `connected_components` — 4-connectivity BFS; **separates multiple fields** in one scene.
  - `mask_to_polygons` — segmentation mask → one closed EPSG:4326 Polygon per field
    (+ `min_area_px` speck filter). Deterministic; the half every raster model shares.
  - `ftw_available` / `ftw_weights_path` — inference gate (weights file + torch); **False offline**.
  - `ftw_propose` — FTW-backed proposal **or `None`** (signals fallback). `_run_ftw_inference`
    is the single stub to wire to a torch forward pass.
  - `select_backend_name` — env `SAHOOL_FIELD_BOUNDARY_BACKEND` (deterministic|ftw; unknown→deterministic).
- `field_boundary_ai.propose_boundaries` — unchanged signature/return. Adds an **opt-in**
  FTW branch that **falls back to the exact deterministic proposal** on any absence/failure.
- `tests_v9/test_field_boundary_backends_v59_5.py` — 10 deterministic tests (polygonization,
  gate, registry, and the fail-safe path through the tool contract). Existing v59 test stays green.

## Failure modes handled
- No weights / no torch (CI, offline) → `ftw_available` False → deterministic proposal.
- Model raises mid-inference → caught → deterministic proposal (tool contract never breaks).
- Unknown backend name → deterministic.
- Heavy deps (torch/numpy) are **never imported at module load** → safe in the fastapi-less
  unit job and the path-loading contract guards.

## What needs the operator's environment (not shippable in-sandbox)
1. **Weights + inference:** set `SAHOOL_FTW_WEIGHTS=/path/to/ftw.(pt|onnx)`, install torch,
   and implement `_run_ftw_inference` (fetch the S2 tile for the bbox/date, normalize FTW
   input bands, forward pass, threshold → binary field mask). The geometry half already works.
2. **Backend switch:** `SAHOOL_FIELD_BOUNDARY_BACKEND=ftw`.
3. **True contour tracing:** swap the per-component rectangle in `mask_to_polygons` for
   `rasterio.features.shapes` (or marching squares) when rasterio is available — one function.

## Licensing (audit before commercial ship — CONFIRM independently)
- **FTW code = MIT** → commercial-safe. **Some FTW weights/datasets = CC-BY-NC-SA (NON-commercial)**
  → verify the specific weight file's license before shipping.
- **Delineate Anything (YOLOv11) = AGPL-3.0** → SaaS blocker; deliberately **not** used.
- Research caveat: several primary sources returned HTTP 403 to automated fetch; the FTW
  license/accuracy specifics and smallholder (<5 ha) degradation should be re-verified.

## Verification
- 10 new + 4 existing v59 tests green; full unit gate 2127 passed; app constructs (14 routes);
  ruff + defect-signatures + compile clean. No tool-schema change; MapHub/TrueColor untouched.
