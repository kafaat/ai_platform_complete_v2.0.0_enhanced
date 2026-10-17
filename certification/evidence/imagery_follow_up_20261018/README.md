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
check was relaxed. General integration CI must pass on the updated head.
