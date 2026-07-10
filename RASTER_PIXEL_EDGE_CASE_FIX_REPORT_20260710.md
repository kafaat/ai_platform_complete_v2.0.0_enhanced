# Raster Pixel Edge Case Fix Report — 2026-07-10

## Scope

This patch closes two low-risk but real edge cases in `services/raster-service/raster_pixel_processing.py`:

1. SAVI denominator consistency with the other index formulas.
2. CLP all-NaN cloud-probability arrays.

## Fixes

### SAVI safe division

Before:

```python
arr = 1.5 * (nir - red) / (nir + red + 0.5)
```

After:

```python
_denom = nir + red + 0.5
arr = 1.5 * (nir - red) / np.where(_denom == 0, 1e-10, _denom)
```

This makes SAVI consistent with NDVI, GNDVI, NDMI, VARI, GLI, and other guarded indicator formulas.

### CLP all-NaN handling

Before, `np.nanmax(clp_f)` could warn/fail for all-NaN CLP rasters.

After:

```python
clp_max = float(np.nanmax(clp_f)) if bool(np.any(np.isfinite(clp_f))) else 0.0
threshold = 0.40 if clp_max <= 1.0 else 40.0
clp_mask = np.where(np.isfinite(clp_f), clp_f >= threshold, False)
```

All-NaN CLP now degrades to an all-false CLP mask rather than producing an invalid threshold path.

## Tests added

`tests_v9/test_raster_pixel_processing_edge_cases.py`

Covers:

- SAVI formula uses guarded denominator.
- SAVI zero-denominator edge case remains finite.
- CLP all-NaN path checks finite values before `nanmax`.
- CLP all-NaN mask is all false.

## Verification

Passed:

```text
raster_pixel_qa_indicator_guard_ok
raster_validated_product_guard_ok
raster_topographic_qa_guard_ok
8 passed
```

The patch adds no dependencies and no routes.
