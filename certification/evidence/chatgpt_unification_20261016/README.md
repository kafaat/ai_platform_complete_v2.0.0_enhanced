# SAHOOL integration evidence — 2026-10-16

Base: `239c01a47442df13d9cbb492017afae103b98dc8`. Integration sources: PR #1195/#1196/#1197 and reviewed local completion patches. The authoritative allocation has 28 distinct IDs in `allocation-roster.json`; GHCR belongs to the original thirteen.

Current registry allocation: **19 fixed / 9 open / 0 verified**. This comprises 11 transferred source fixes in this integration, two transferred fixes already merged in #1194, and six original fixes (GHCR, readiness, VRT grid/nodata/normalization claim, and backfill version identity). Seven original gaps and RAG01/RAG07 remain open. These are source/registry states, not 28 completed runtime acceptances.

| Scope | Baseline / corrected evidence |
|---|---|
| Platform/weather/notification/mobile | a/summary.json: 11 red /55 green; Flutter runtime witness not run |
| Recipe mass basis | b/RESULT.md: 3 red /45 green |
| Irrigation producer/UI/reload | b/IRRIGATION_COMPLETION_RESULT.md: producer red→green; 66 platform and19 frontend passes; typecheck passes |
| Irrigation Decision bindings | 60 red /8 controls on main;75 passes, **19 native PostgreSQL skips**;19 PGlite checks |
| STAC identity/NIR safety | c/results.json: 4 red /4 green +29 regression |
| Original raster repairs | c-original/results.json:27 red /48 controls→75 green;49 related regression; scale remains open |
| Raster CI compatibility | raster_ci/results.json:7 red on published 8c1085 with GDAL3.12.2;75 green on each rasterio1.5.2/GDAL3.12.2 and1.4.4/GDAL3.10.3; preserves numeric nodata and dataset mask together |
| Readiness | a/readiness-evidence.json:8 red /1 control→9 green; ASGI handler proof with substituted probes |
| RAG03/04/11 | d/verification.json:10 red /18 green +237 RAG +97 service/auth |
| U07 platform persistence | e/README.md:6 red /32 Python regression +32 PGlite checks |
| GHCR | ghcr-current/verification.json: four successful current-main jobs cover five locked digests; bounded fixed, not permanent verified |

Groups overlap and must not be summed. Root's combined applied-tree checks are `combined-readiness-irrigation.log` (84 passes) and `combined-imagery.log` (75 passes). Historical branch results retain their original source pins. No final full preflight or final remote CI result is asserted in this package.

Irrigation explicitly distinguishes declared equipment inputs from measured water. Canonical current water and dated weather bind the immutable reviewed source; separate review/plan/manual-record actions do not start hardware. Reload uses persisted tenant/field/season/lineage/digest bindings and transaction-local tenant context. Native PostgreSQL skips remain visible; WASM PostgreSQL is separate evidence. Existing operation guards still apply. Root's subsequent module-budget check passed twice after applying only final manifest paths; earlier transient obsolete-module failures in the handoff remain historical.

Raster grid/nodata/calibration-claim helpers are repaired; production Element84 containment remains unchanged. Actual STAC scale/offset semantics, historical incident cause, legacy inventory and vegetation acceptance remain open. Synthetic raster tests do not prove provider acceptance or historical correction. RAG Arabic evaluation is synthetic, so RAG01/RAG07 remain open. Decision034 staging, correlation propagation and TTS production skew still require their declared runtime/ownership evidence.

U07 authorization remains restricted to its reviewed byte pins, with no independent signature claim and global GATE-01 CLOSED. PGlite PostgreSQL18.6 is not native PG16 certification. Reserved frontend/nginx.conf and shared/security remain unchanged from pinned main. No main merge or Railway deployment is authorized here.

Final witness encoding refresh: `final-witness-encoding/receipt.json` pins the current U07/readiness tests and red/green runs. S5 scope review: `governance-final-review.json` and `c-governance-review/review.json`; the GATE evaluator and policy are unchanged. Raw GHCR logs are preserved as `.log.gz`; text views escape hidden marks, with both hashes in `ghcr-current/log-storage.json`. Frontend full attempt passed 211 suites; its sole WASM path-loading failure passed all 7 tests after copying dependencies locally (`frontend-verification.json`); no single full-command green claim.
