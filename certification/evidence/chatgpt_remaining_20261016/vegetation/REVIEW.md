# Vegetation authority transport — revised after independent review

Gap remains **open**. Current receipt: `review-receipt.json`; original receipt and logs are preserved as historical measurements, not final source evidence.

Current witnesses: **13 failed / 3 passed on main-identical tree**, **16 passed / 0 skipped after repairs**. Targeted regression: **53 passed / 0 skipped**. Five new review witnesses failed on the initial patch before correcting the issues below.

The initial transport patch exposed a latent writer error: requested masking had been persisted as applied masking. The writer now uses actual validated mask execution and actual producer mask identity. Legacy reading/hydration/grid cannot surface requested-only mask IDs without recorded actual application.

The initial use of row `created_at` as availability was also unsafe after same-identity reprocessing replaces its COG. Availability now comes only from explicit `provenance.data_available_at`, stored atomically with the COG and refreshed from actual processing publication time. Historical rows lacking this field remain unknown, regardless of their row creation time.

Existing quality-score semantics remain unchanged. Historical COGs are not relabelled with the running band-math algorithm. Provider provenance stores only explicit request provider, never source-format inference.

No gate was weakened; no CDSE mask execution was invented. Server-side CDSE masking identity, raw-quality versus confidence policy, and canonical-observation scene/mask authority remain unresolved. Unit tests exercise real adapters and small raster files with recording database doubles; no live database acceptance is claimed.
