# CDSE/Raster Runtime Hardening — 2026-06-26

## Scope
Applied additional hardening after the live `sahool-raster-service` logs showed repeated `400 Bad Request` from Sentinel Hub Catalog and `invalid UUID ''` during `raster_assets` persistence.

## Changes

### 1. CDSE Catalog request hardening
File: `services/raster-service/cdse_client.py`

- Added `_to_rfc3339()` to normalize bare dates such as `2026-06-26` to explicit UTC datetimes.
- Added `_clamp_cloud_pct()` to keep cloud filters within `[0, 100]`.
- Added `_safe_log_payload()` so provider error logs include a useful non-sensitive request summary.
- Hardened `search_scenes()`:
  - validates bbox before network calls;
  - normalizes Feature/FeatureCollection geometry;
  - sends CQL2 filter first;
  - falls back to a minimal STAC payload if the provider rejects optional filter syntax;
  - applies client-side cloud filtering after fallback;
  - logs response body and safe payload summary on both primary and fallback failure.

### 2. Raster persistence UUID hardening
File: `services/raster-service/db_persist.py`

- Added `_valid_uuid_text()`.
- `insert_raster_asset()` now rejects missing/invalid `field_id` and invalid non-empty `tenant_id` before opening a DB connection.
- This prevents `asyncpg` UUID binding errors like `invalid UUID '': length must be between 32..36 characters`.

### 3. Regression tests
Files:

- `tests_v9/test_cdse_catalog_hardening_20260626.py`
- `tests_v9/test_raster_db_persist_uuid_hardening_20260626.py`

Coverage added for:

- date normalization;
- cloud percentage clamping;
- Catalog fallback after provider 400;
- client-side cloud filtering;
- invalid bbox rejection;
- UUID validation before DB connect.

## Verification

Executed:

```bash
python3 -m py_compile \
  services/raster-service/cdse_client.py \
  services/raster-service/db_persist.py \
  tests_v9/test_cdse_catalog_hardening_20260626.py \
  tests_v9/test_raster_db_persist_uuid_hardening_20260626.py
```

Result: passed.

Manual unit verification for Catalog fallback and UUID guard: passed.

`pytest` collection is still blocked in this environment by missing `jose` from `tests_v9/conftest.py`, same pre-existing environment issue.

## Operational recommendation

After deploying this package, inspect logs for either:

- primary Catalog request success; or
- primary failure followed by fallback success.

If both fail, the logs now include the provider response body and the safe payload summary needed to identify the remaining provider-side rejection.
