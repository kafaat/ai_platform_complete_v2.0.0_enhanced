# Imagery follow-up evidence — 2026-10-18 Asia/Aden

Base: main `45dfdc53752a2e6eb6ba2d2726567c2af3c4158c` (#1210), after #1209. Tested source head: `fc1f5ec3376c96999210c1177c9767d42d2658b7`.
Gap: `VEGETATION-POST-EXECUTION-BRIDGE-CALLS-AN-UNDECLARED-RASTER-ROUTE-01`.

- `local-tests.txt`: 23 passing behavioral bridge/router/worker tests.
- `raster-regression-tests.txt`: 43 passing existing raster regressions in a separate process.
- `mixed-service-import-collision.txt`: an attempted combined invocation produced six import errors because existing service suites share the top-level `routers` package. Both suites pass in separate processes; the failed mixed run is retained, not presented as a pass.
- `full-app-route.txt`: actual raster ASGI app OpenAPI contains both new routes (86 paths); no lifespan/database activation was claimed.
- `pg16-collection.txt`: collection only, not a PostgreSQL execution result.
- `dependency-audit.json`: pip-audit of the newly added PyJWT[crypto]==2.15.0 dependency
  closure; not an audit of the complete raster image.
- `pg16-ci.txt` is a lossless JSON-lines-array container of the original job log
  (`lines` joined without a separator reproduces the exact UTF-8 bytes). This
  escapes a bidirectional control character emitted upstream without deleting it.
  `pg16-ci-receipt.json` records both original-log and container SHA256 digests.
  All nine actual PG16 witnesses passed in
  [CI run 39077990697](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/39077990697),
  with zero skips. Checkout `c315c4af` has the exact tree of source head `fc1f5ec3`.
  Restricted-role/owner FORCE RLS, concurrent replay/claim, expired-lease fencing,
  partial progress, cancellation/budget and matching Decision receipts were measured.
  Local OS user switching remained blocked; no server/root guard was bypassed.
- No staging/production deployment or execution was performed for this change.
- No physical completion or agricultural outcome verification is claimed.

Method, activation requirements, limitations and primary sources:
`docs/runbooks/DURABLE_IMAGERY_FOLLOW_UP.md`.
The source/PG16 contract gap is fixed in PR #1211 on the tested source above.
This does not certify a PostgreSQL server crash/restart, full Decision promotion,
or staging/production acceptance; the gap is not promoted to verified.

Integration follow-up: the first general integration job (117529016730) failed
four read-only schema probes on the stale manifest contract (341 tables).
The existing contract witness reproduced the mismatch; the contract was regenerated
using its `_extracted` derivation to 342 tables and 187 columns. No probe/permission
check was relaxed. General integration CI passed on 7640288c in run 39079511074, job 117533577048.

Unit follow-up on 7640288c: 9841 passed and four failed (job 117533577114).
The corrections update the deliberately pinned catalog inventory to 1007 for the
three new routes, correct the Decision default port to 8160, and align the v208
runbook count with the 234-entry manifest. Both follow-up routes now call the
existing field-ownership guard before replay/read as well as first admission,
using a restricted tenant transaction and JWT-bound context. Missing/foreign
fields fail with 404; unavailable ownership fails with 503, with no cache fallback.
The auth-coverage guard is unchanged. Eight HTTP witnesses cover both methods
and ownership success/foreign/missing/unavailable outcomes, including context
restoration; missing/forged/expired tokens and conflicting headers are checked
on both methods. `ci-corrections-local.txt`: 58 passed. Updated full CI pending;
this local measurement is not staging/production acceptance.

Synchronization: main@503d7d7c (#1212 JWT revocation and #1218 ET0) is incorporated after 8c5c941c. The 23 generated conflicts are resolved through repository generators; Claude-owned source files are preserved verbatim from main. Acceptance of the new head remains pending, independent of earlier evidence.
