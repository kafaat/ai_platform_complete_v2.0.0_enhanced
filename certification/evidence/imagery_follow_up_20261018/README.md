# Imagery follow-up evidence — 2026-10-18 Asia/Aden

Base: main `7f2d7fa0f8d4fb975337316475c019e769cd4447` (#1209).
Gap: `VEGETATION-POST-EXECUTION-BRIDGE-CALLS-AN-UNDECLARED-RASTER-ROUTE-01`.

- `local-tests.txt`: 21 passing behavioral bridge/router/worker tests.
- `raster-regression-tests.txt`: 43 passing existing raster regressions in a separate process.
- `mixed-service-import-collision.txt`: an attempted combined invocation produced six import errors because existing service suites share the top-level `routers` package. Both suites pass in separate processes; the failed mixed run is retained, not presented as a pass.
- `pg16-collection.txt`: collection only, not a PostgreSQL execution result.
- `dependency-audit.json`: pip-audit of the newly added PyJWT[crypto]==2.15.0 dependency
  closure; not an audit of the complete raster image.
- Real PG16 execution is required in `Imagery Follow-up PG16` CI before the durable
  queue claims are accepted. Local OS user switching failed (`runuser: cannot set
  groups: Operation not permitted`); no server/root guard was bypassed.
- No staging/production deployment or execution was performed for this change.
- No physical completion or agricultural outcome verification is claimed.

Method, activation requirements, limitations and primary sources:
`docs/runbooks/DURABLE_IMAGERY_FOLLOW_UP.md`.
The gap remains open pending the real PG16 witness; a passing unit suite is not
substituted for database semantics or live acceptance.
