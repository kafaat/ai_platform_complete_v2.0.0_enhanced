# SAHOOL e2912de — Hardening Fix Delta

## Follow-up hardening

- Internal tenant assertions now bind nonce, request id, HTTP method/path and
  current/previous key ids; Redis atomically rejects a repeated assertion.
- MinIO users and least-privilege policies are provisioned before workloads,
  with positive access and cross-bucket denial checks.
- `docker-compose.production.yml` is the fail-fast production overlay.
- A unified readiness gate now emits one archived JSON verdict and deliberately
  distinguishes `release_candidate` from `production_certified`.
- Production Compose images are rejected when they use `latest`, lack a tag, or
  use a non-versioned mutable tag; the guard runs locally and in CI.
- Qdrant now has API-driven per-collection snapshots, offline digest/size
  verification, and a non-destructive staging restore drill using reserved
  temporary collection names with archived evidence.
- Scene provenance is now consumed visibly in both Field Workspace and MapHub:
  scene id, acquisition time, cloud percentage, COG state, quality, and indices;
  missing lineage is labelled incomplete instead of silently hidden.
- SIM-GOLDEN-01 now validates real harvest evidence on a latest-season temporal
  holdout, rejects post-harvest leakage, computes MAE/RMSE/nRMSE/MAPE/bias/R²,
  requires farm/season diversity, and permits promotion only with signed evidence.

## Implemented

1. **Ingest DB credential fail-closed**
   - Removed the known `sahool_ingest_pw` fallback from Compose and both PostgreSQL bootstrap runners.
   - `INGEST_DB_PASSWORD` is now mandatory before role creation or migration startup.

2. **Per-service object-storage identities**
   - Scout ingest now requires `SCOUT_INGEST_S3_ACCESS_KEY/SECRET_KEY`.
   - Raster service and its workers require `RASTER_S3_ACCESS_KEY/SECRET_KEY`.
   - Workloads can no longer silently inherit the MinIO root/admin identity from `S3_ACCESS_KEY`.
   - Operators must provision prefix-scoped MinIO policies before deployment.

3. **Internal field-catalog caller boundary**
   - Production mode refuses an empty `FIELD_SERVICE_ALLOWED_CALLERS` allowlist.
   - The v9 deployment defaults the only current caller to `vegetation-analysis-service`.
   - This narrows shared-token exposure; signed tenant claims/workload identity remain a later infrastructure migration.

4. **Production certification truth**
   - Missing Redis live credentials now fail the evidence job instead of returning a green exit code.
   - `production_certification_blockers_status.py --require-certified` exits non-zero while blockers remain.
   - The workflow has an aggregate verdict job that cannot report success from partial evidence.

5. **Farm-memory backup truth**
   - Scalar JSON export defaults to `include_vectors=False` and declares `vector_export.included=false`.
   - Requesting vectors raises `VectorExportUnavailable` instead of serializing `vectors: []`.
   - Encrypted tarballs record `vectors_included=false`.

6. **Regression guards**
   - `production_honesty_guard.py` now blocks reintroduction of the ingest fallback, shared admin S3 credentials, fake empty-vector backups, or a non-enforcing certification verdict.
   - Added unit coverage for the vector failure mode and field-service production allowlist.

7. **Signed tenant binding for the internal field catalog**
   - Added a dependency-free, short-lived HMAC assertion binding `service + tenant + issued_at`.
   - Vegetation signs every field-catalog call; field-management verifies signature, caller,
     tenant match, expiry, future skew, and tampering before setting the RLS tenant context.
   - Production refuses a missing assertion key. A raw `X-Tenant-Id` is no longer sufficient.

8. **Single-truth boundary for seasonal yield simulation**
   - The lightweight RUE/FAO-56 result is explicitly `screening_only`.
   - It is never eligible for calibration and declares `pcse_wofost` as the canonical yield engine.
   - A static guard prevents the screening model from silently regaining official/calibration status.

9. **Generated inventory reconciled**
   - Regenerated service/route inventories and `SERVICE_REGISTRY.md`; drift check is green.

## Verification performed

- Historical first-pass compile: 2,635 Python files, **0 syntax errors**.
- `production_honesty_guard.py`: **PASS**.
- Certification status read-only mode: **PASS**, reports `production_certified=false` honestly.
- Certification enforcing mode: **expected exit 1** while evidence is pending.
- `docker-compose.v9.yml` and certification workflow: **valid YAML**.
- Both migration shell scripts: **valid shell syntax**.
- Direct scalar/vector export behavior probe: **PASS**.
- Signed-tenant adversarial probe (tamper/service/tenant/expiry/future): **PASS**.
- Historical continuation compile: **2,638 files / 0 syntax errors**; the latest
  independent sweep after continuation 15 compiled **2,653 files / 0 errors**.
- Direct FastAPI service import was not run because FastAPI is unavailable in the audit runtime;
  the repository unit tests cover it when normal test dependencies are installed.

## Operator actions still required

These cannot be manufactured inside a ZIP:

- Run the included MinIO provisioning and cross-bucket denial checks against the target
  deployment using secrets supplied by its secret manager.
- Supply real secrets through the deployment secret manager.
- Run PostgreSQL/RLS/concurrency tests, Redis/NATS/CDSE/GPU tests, staging E2E, backup/restore drills, and 7/14-day soak.
- Complete workload identity (mTLS/SPIFFE), SIM-GOLDEN calibration, terrain-RGB,
  ISOXML, and GeoParquet as separate bounded changes. Scene provenance UI consumption
  was completed by the later follow-up hardening above.

The archive is hardened but must still report **not production certified** until the live evidence gates pass on its final SHA.
# Continuation 7 — signed release provenance and SBOM attestation

- Added a tag/manual release workflow that binds the exact Git commit archive to
  both GitHub build provenance and the generated CycloneDX dependency SBOM.
- Restricted workflow permissions to repository read, OIDC token issuance, and
  attestation writes; no broad write permission or privileged pull-request event.
- Added a fail-closed verifier for the local SHA-256 checksum and the signed
  GitHub attestation, plus a static regression guard wired into unified readiness.

# Continuation 8 — full-history secret scanning

- Added a fail-closed Gitleaks workflow for pushes, pull requests, manual runs,
  and weekly rescans, using the complete Git history instead of only the checkout tip.
- Pinned the Gitleaks engine version and disabled PR comments/artifact uploads so
  the workflow operates with read-only repository permissions.
- Added a regression guard that rejects shallow checkout, soft failure,
  privileged pull-request events, or broad workflow permissions.

# Continuation 9 — immutable CI, release-archive scanning, and evidence provenance

- Pinned every external GitHub Action reference to a full 40-character commit SHA
  and added a repository-wide guard against mutable Actions and privileged workflows.
- Added a fail-closed ZIP scanner for sensitive filenames, private keys, unsafe paths,
  symlinks, and oversized archive content; release attestation now requires it.
- Added time-boxed security exception governance with owner, reason, scope, and expiry.
- Added a scheduled/manual transitive-lock compilation and pip-audit workflow that emits
  checksummed P-CERT-2 evidence only as verified inside an identifiable GitHub run.
- Tightened verified evidence to require repository/workflow/run/commit provenance and
  a valid, recent UTC timestamp.
- Enforced lockfile v3 and lifecycle-safe deterministic `npm ci` usage in frontend CI.

# Continuation 10 — CI contract compatibility after immutable pinning

- Updated the legacy CI validator to require the exact immutable checkout/setup-python
  commits instead of treating mutable major tags as the only acceptable pinning form.
- Added the complete CI contract validator to unified readiness so future workflow-policy
  changes cannot pass the new guard while silently breaking the older release contract.

# Continuation 11 — complete local quality-gate execution

- Executed the real raster test dependency set and completed the full local quality gate:
  270 raster tests passed (1 live-database test skipped) and all 29 targeted release,
  deployment, observability, security, architecture, and certification contracts passed.
- Added an explicit local test dependency preflight so missing pytest/geospatial runtime
  packages fail with one actionable installation command instead of 20+ import errors.
- This local result strengthens release-candidate confidence but is not substituted for
  the still-missing connected CI and target-environment production evidence.

# Continuation 12 — frontend toolchain recovery and replay scrubber correctness

- Rebuilt frontend dependencies deterministically from `package-lock.json`, removing the
  previous corrupted npm cache/install as a local validation blocker.
- Passed the complete frontend suite: 188 test files / 1,277 tests, TypeScript checking,
  the production Vite build, and the no-demo assertion over 198 emitted JavaScript files.
- Normalized date-only and timezone-less replay timestamps to UTC so a season-boundary
  event is not silently excluded when the browser or server uses a non-UTC timezone.
- Extracted and tested the replay filter as a pure boundary function, added explicit
  real-time range input handling and keyboard Home/End support, and exposed accessible
  season-start/season-end controls for deterministic navigation.

# Continuation 13 — warning-free frontend regression suite

- Flushed the asynchronous imagery-date effect inside React's test boundary for every
  `FieldWorkspaceMapCard` render state, eliminating misleading unwrapped-update warnings.
- Enabled both React Router v7 compatibility flags in the affected test routers so the
  suite validates upcoming transition and relative-splat behavior without warning noise.
- Re-ran all 188 frontend test files / 1,277 tests with zero React `act(...)` warnings and
  zero React Router future-flag warnings; TypeScript, production build, and FE-08 passed.

# Continuation 14 — fail-closed frontend warning and dependency guards

- Audited the complete locked npm graph: 470 dependencies and zero known vulnerabilities
  across info, low, moderate, high, and critical severities at validation time.
- Added a focused global test guard that converts React updates outside `act(...)` and
  missing React Router compatibility flags into hard test failures while preserving all
  unrelated console diagnostics.
- Added self-tests proving both warning classes are rejected, then passed 189 test files /
  1,279 tests, TypeScript, the production build, and FE-08.

# Continuation 15 — frontend delivery performance and accessibility budgets

- Split stable React, UI, chart, Leaflet, MapLibre, Terra Draw, and Turf dependencies into
  cacheable vendor boundaries. The main entry fell from 1,095,123 to 341,351 bytes, while
  `HubMapGL` fell from 1,045,129 to 17,610 bytes by moving MapLibre into its lazy vendor.
- Added a fail-closed build budget: entry <= 400,000 bytes, MapHub <= 800,000 bytes,
  workers <= 900,000 bytes, and every JavaScript asset <= 1,050,000 bytes. The sole near-
  limit asset is lazy MapLibre at 1,027,608 raw / 272,930 gzip bytes.
- Wired the budget into the browser-test web server and Field Workspace CI closure job.
- Improved login accessibility with a semantic main landmark, explicit label bindings,
  an accessible password-visibility name, and a live alert for authentication errors.
- Added real-browser keyboard/accessibility and navigation/asset performance tests.
  Playwright discovers 24 Chromium tests (including the two new checks); execution remains
  delegated to CI because this audit container has no Chromium executable installed.
- Confirmed the npm `http-proxy` warning originates only from injected uppercase/lowercase
  proxy environment variables, not repository `.npmrc`; sanitized validation runs are clean.
- Re-passed 189 Vitest files / 1,279 tests, TypeScript, production build, bundle budget,
  and FE-08 after the changes.

# Continuation 16 — critical-review gap closure

- Upgraded the Local AI RAG integration boundary to compatible LangChain 1.x packages,
  including `langchain-text-splitters==1.1.2`, and removed the unused meta-package that
  forced the vulnerable pre-1.0 line. A clean pip dry-run resolved the full graph.
- Moved `local-ai-rag` from advisory-only scanning into the gating multi-service pip-audit
  command and extended the resolver guard to reject unsafe version drift or audit removal.
- Converted noisy BYPASSRLS warnings into a reviewed fail-closed path allowlist: any new
  unclassified reference now fails the security audit.
- Extended the frontend delivery budget to cap each DuckDB WASM asset and their aggregate
  size, rather than measuring JavaScript alone.
- Narrowed Kubernetes ingress from every namespace to same-namespace workloads plus an
  explicit trusted ingress-controller namespace list; public HTTPS egress is now an
  explicit opt-out setting for clusters using a controlled egress proxy.
- Clarified the unified readiness JSON as `static_source_contracts_only`, listed every
  excluded toolchain/live gate, and added release-package and dependency-resolution checks.
- Reconciled stale hardening-report counts and operator actions with later continuations.
