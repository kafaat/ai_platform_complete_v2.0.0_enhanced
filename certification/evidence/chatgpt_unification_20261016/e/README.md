# U07 scoped reconstruction evidence

Scope: platform `persist_phase10_learning_outputs`, additive v234, and both migration registrations. The online-learning insert and its local tenant settings now share an actual `conn.transaction()`; the remote mirror runs after commit. Other phase-runtime branches retain their existing tenant-GUC baseline debt. Decision-service mirror review fields and reviewer authentication remain outside this repair.

- `u07-red-main.log`: 6 assertion failures against clean main. Copied final witness uses symlinked clean-main runtime/migration paths. `main-baseline-receipt.json` pins main source blobs/commit; clean main is unmodified.
- `u07-transaction-red.log`: before the scoped transaction fix, 5 new boundary/rollback cases failed and migration wiring passed. This found a real gap in the first SQL harness, which had injected transaction boundaries not present in the writer. That earlier proof is superseded.
- `u07-green.log`: 10 passes: 6 new writer-binding/transaction/rollback/wiring tests, 4 existing v151 tests. Recorder tests prove emitted calls and boundaries, not database enforcement.
- `u07-regression.log`: 32 Python tests passed across the new writer suite, v151, phase9/10 activation, source-lineage and recommendation-to-learning tests (includes the 10 above; do not add counts).
- `u07-pglite-result.json`: 32 checks against PostgreSQL18.6 WASM/PGlite0.5.10, with exact source/migration blob hashes. Executes actual v119/v151/v234 migrations (v234 twice), legacy defaults, captured real writer SQL and BEGIN/COMMIT, insert/upsert/downgrade, malformed approval rejection, and non-bypass-role tenant isolation. The SQL harness injects no writer transaction; it uses a separate readback transaction only after the writer has committed. Not native PG16 or asyncpg/network acceptance.
- `u07-main-sql-red.log`: captured exact-main statements fail with RLS SQLSTATE42501 even with v234 applied, exposing the missing transaction independently of missing columns.
- `u07-mutant-result.log`: removing `IS TRUE` accepts malformed approval5 (JSON verdict=null with valid reviewer/evidence) and fails acceptance. Mutant is evidence only.
- Authorization is `docs/architecture/gates/adjudications/GATE01-ADJ-2026-10-16-001.json`. Root reissues its final byte bindings after review; no independent owner signature is claimed. The pending draft outside the repository is preparation only. Supplemental hashes are review evidence; current guard enforces only policy frozen-path hashes.
- `u07-byte-receipt.json` pins final formatted sources. Byte changes require fresh binding/review and any affected tests.

Reproduce with PGlite0.5.10 and repository Python dependencies:

```bash
python capture_u07_writer.py /full/repo > u07-writer-calls.json
PGLITE_MODULE_PATH=/absolute/node_modules/@electric-sql/pglite/dist/index.js node u07_pglite_acceptance.mjs /full/repo u07-writer-calls.json
```

Capture mocks only the unrelated HTTP mirror and records actual writer calls/transactions. Node independently executes them. For NULL mutation additionally set `U07_MIGRATION_FILE=/absolute/u07-null-check-mutant.sql.txt`. For exact-main SQL failure, capture main then replay against repaired migrations.

This agent performed no staging, commits, generation, brain updates, remote writes, service migrations, or deployments.
