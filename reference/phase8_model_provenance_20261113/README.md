# Phase 8 Model Provenance package (reference only, not for merge)

This is the owner's package `SAHOOL_v26_Phase8_Model_Provenance_PATCH_20261113.zip` (sha256 `da4dcd49cdea4540365923af7118f97f87953ed6556e88dcfeff1024e694d22e`), extracted as-is. No file here has been modified. The package is stored for the hospital session to port. **This branch must not be opened as a PR** and nothing here is wired in.

## Why it is not applied
- `PATCH_MANIFEST.json` says the baseline is `SAHOOL_v26_Phase7_Grant_Admin_Cumulative_20261113.zip` (sha256 `4995926520…37a7`). The patch applies exactly to that baseline only.
- `migrations/v261_scout_photo_detection_link_events.sql` ALTERs `scout_photo_field_access_grants` and `scout_photo_grant_audit_events` and references `scout_photo_evidence`, `detection_provenance` and `edge_results`. The grants and audit tables are not on main (as of f110d9a17) or on any branch.
- The `MANIFEST.txt` in the package registers v242–v261, but main lacks those numbers.
- The hospital branch `fix/scout-photo-evidence` (as of 95736e561) ports part of the same series with different numbering:
  - the package's v256 is the branch's `v260_scout_photo_evidence`;
  - the branch also has `v257_scouting_pin_location_photo` and `media_api.py`;
  - it has none of the grants or audit work, which is Phase 7.

## Recommended port order
1. Phase 7 (grant admin): the grants and audit tables, plus `scout_photo_grants.py` and its panel. These are on top of the hospital's scout-photo branch.
2. Phase 8 (this package): renumber v261 to the next free number after the hospital's series, and fix references in `MANIFEST.txt` / `schema_probe_contract.env`.
3. Keep the feature flag default `SCOUT_MEDIA_DETECTION_LINK_ENABLED=0`, as the manifest says.

## What the package declares about itself (from PATCH_MANIFEST.json)
- Python: 163 passed, 0 failed (in the package environment).
- Live PostgreSQL, MinIO and Flutter: **NOT_RUN**.
- Stage 8 catalog gate (`scripts/qa/scout_photo_stage8_catalog_gate.sql`): added but **NOT_RUN**.
- No GitHub push and no production deployment.
