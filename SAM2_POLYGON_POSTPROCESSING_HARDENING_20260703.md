# SAM2 Polygon Post-processing Hardening — 2026-07-03

## Summary

SAM2 mask-to-polygon conversion now applies field-scale geometry cleanup:

- configurable simplify tolerance in meters: `SAM2_POLYGON_SIMPLIFY_TOLERANCE_M=3`
- configurable consecutive-vertex de-duplication: `SAM2_POLYGON_DEDUP_TOLERANCE_M=0.5`
- conservative validity repair via `make_valid`/`buffer(0)` fallback
- closed GeoJSON polygon output for frontend review and manual save

The goal is to reduce excessive edit handles and near-duplicate vertices without changing the SAM2 security path or automatic-save behavior.
