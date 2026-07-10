# Raster Cloud Strategy Execution + Production Certification Blockers — 2026-07-10

## Scope

This patch completes the internal refactor that was intentionally deferred after introducing `ValidatedRasterProduct` and `CloudMaskStrategy`.

It also adds a read-only Production Certification blocker status helper and a manual GitHub Actions workflow that maps directly to the four open blockers without claiming that any blocker is closed.

## Raster changes

### 1. Strategy execution is now wired into `raster_pixel_processing.py`

`services/raster-service/raster_pixel_processing.py` now imports and calls:

```python
raster_cloud_mask_strategies.strategy_for_source_format(...).apply(...)
```

The indicator path no longer owns source-native cloud mask decisions inline. Instead, it delegates source-specific behavior to:

- `Sentinel2SCLStrategy`
- `LandsatQAPixelStrategy`
- `NoOpCloudMaskStrategy`

### 2. Sentinel-2 strategy now covers SCL + CLM + CLP

`Sentinel2SCLStrategy` now combines:

- SCL: cloud/cirrus = 8/9/10
- SCL: cloud shadow = 3
- SCL: snow/ice = 11
- CLM: cloud mask supplement
- CLP: cloud probability supplement with 0..1 and 0..100 auto-thresholding

All-NaN CLP is handled as unavailable via `sentinel2_clp_all_nan_unavailable`, not as a failure path.

### 3. Landsat remains QA_PIXEL-based

`LandsatQAPixelStrategy` keeps Collection-2 style bit handling:

- bit 3: cloud
- bit 4: cloud shadow
- bit 5: snow

### 4. NoOp remains explicit

`NoOpCloudMaskStrategy` remains the explicit strategy for sources that do not provide a native cloud mask, such as drone orthomosaics. This keeps unmasked processing visible in the validated product contract.

### 5. Saturation proxy remains separate

Reflectance-range saturation remains in `raster_pixel_processing.py` as a sensor/value QA proxy, not as a cloud-mask strategy. This avoids incorrectly coupling radiometric sanity checks to source-native cloud semantics.

## Guard changes

`raster_validated_product_guard.py` now checks that:

- `raster_pixel_processing.py` imports `raster_cloud_mask_strategies`
- the indicator path calls `strategy_for_source_format`
- the indicator path calls `strategy.apply`
- inline source-native mask logic does not return via `b.clp is not None`, `b.clm is not None`, or `np.isin(scl`

## Tests added/updated

Added:

```text
services/raster-service/test_cloud_mask_strategies.py
```

Covers:

- strategy factory dispatch
- Sentinel-2 SCL + CLM + CLP combination
- Sentinel-2 CLP all-NaN handling
- Landsat QA_PIXEL bit handling
- explicit NoOp behavior

Updated:

```text
tests_v9/test_raster_pixel_processing_edge_cases.py
```

The CLP all-NaN static checks now point to `raster_cloud_mask_strategies.py`, because CLP logic has moved out of `raster_pixel_processing.py`.

## Production Certification blockers

Added read-only helper:

```text
scripts/ci/production_certification_blockers_status.py
```

Added manual workflow:

```text
.github/workflows/production-certification-blockers.yml
```

The workflow separates the four blocker tracks:

| Blocker | Workflow job | Status after this patch |
|---|---|---|
| P-CERT-1 Full branch CI | `full-branch-ci-evidence` | still pending |
| P-CERT-2 Transitive locks | `transitive-locks-evidence` | still pending |
| P-CERT-3 Redis live integration | `redis-live-evidence` | still pending / waivable only with reason |
| P-CERT-4 ONNX/SAM2 provisioning | `model-provisioning-evidence` | still pending |

No blocker was marked verified in this patch. The repository remains:

```text
release_candidate_not_production_certified
```

## Verification run

Executed locally in the sandbox:

```text
raster_validated_product_guard_ok
raster_pixel_qa_indicator_guard_ok
raster_topographic_qa_guard_ok
raw_data_processing_contract_ok
production_evidence_pack_check_ok
```

Targeted pytest:

```text
13 passed
```

Additional inventory/evidence guards:

```text
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
test_dependency_inventory_check_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
report_index_check_ok
```

## Remaining production evidence

The blocker helper currently reports:

```text
production_certified=false
P-CERT-1=pending
P-CERT-2=pending
P-CERT-3=pending
P-CERT-4=pending
```

These require external CI/deployment evidence, not local static proof.
