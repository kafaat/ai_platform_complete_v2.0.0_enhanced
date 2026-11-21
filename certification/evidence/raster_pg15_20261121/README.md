# Raster PostgreSQL 15 certification — 2026-11-21

## Source and scope

The local code candidate is `6122ed4c642390b32d6c36873e27a425c0d309af`, tree
`ef12ac7e31f2dec8328e8a311e69c9b6fb293bbf`, based on main
`9fdaefc9a0a8298a1d8cfc48bb120744ef3f78b0`. These are local Git identities;
this receipt does not assert that a later published commit has passed CI.
The wrapper records a clean, unchanged source before and after execution.

The actual run body was read from `.github/workflows/ci.yml`, step
`Exercise raster leases and scene enqueue as the restricted application role`.
Only `RUNNER_TEMP` and `COVERAGE_FILE` were relocated outside the checkout.
The six collected node IDs are in `catalog.json`.

## Observed results

- Native PostgreSQL **15.20**, PostGIS **3.7.0**, Python **3.12.14**; this is not
  a Docker-image parity claim. The optional `postgis_raster` extension was not
  installed; these cases exercise durable SQL state, not raster pixel operators.
- The canonical manifest contains **275** migrations. Preparation applied it
  from empty and reapplied it; this execution reapplied all 275 in exact order.
- All **six cases passed**, with **zero skips, failures or errors**. They cover
  the actual restricted connection, lease recovery/fencing, distinct claim ID
  conflicts, synchronized two/eight-worker claims, and concurrent scene enqueue.
- The application role has no dangerous direct attributes, no role memberships,
  and no table ownership. The test queries the actual application connection;
  the generic evidence guard independently checks schema and role attributes.
- The PostgreSQL 15 raster schema contract matched. The evidence records the
  selected contract path and SHA-256.
- Removing `RASTER_TEST_DATABASE_URL` produced six skipped cases and pytest
  exit **1**, without a successful evidence document. `negative_no_dsn.json`
  is the receipt of that expected rejection, not product acceptance.
- The owned database server was stopped. No deployed database was contacted.

The negative no-DSN receipt retains its earlier local `e823a1a` identity;
the mandatory adapter and schema contract are byte-identical in the later candidate.
The synchronized claim fixture now opens each real asyncpg connection explicitly,
so the fake-connection inventory can trace it without admitting any stand-in.

The first attempt's six cases passed but its overall gate failed because the
reused default schema contract correctly required PG16. The preserved
`initial_pg16_contract_failure.json` is **FAIL** evidence, not an accepted run.
The fix added explicit contract selection; the default PG16 contract remains
unchanged. The later accepted run is the one in `live_pg_evidence.json`.

## Evidence files and limits

`certification.xml` and `command.txt` are unedited outputs from the accepted
execution. The evidence JSON files retain identical decoded field values;
Unicode bidi formatting code points in inherited diagnostic text are JSON-escaped
to satisfy the repository text guard. `native_command_receipt.json` binds the
wrapper command, migration order, source identities and cleanup. Its paths
identify the original local workspace; `command.txt` contains the original
`command.log` bytes with the SHA-256 recorded in that receipt.

The focused guard/adapter/lab/coverage tests separately passed **113 cases**;
that count is not added to the six live cases as a single suite. Full preflight,
GitHub CI on the published head, merge, deployment, restored-production
upgrade and field acceptance are separate gates. This receipt certifies none
of those unobserved stages.
