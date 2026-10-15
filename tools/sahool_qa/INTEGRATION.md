# SAHOOL QA repository integration

Source: owner-supplied `sahool-qa-0.4.2.zip`. SHA-256: `754fda2fbd170f712f147da895af0e3fca363a483bdc5d1f07b5c4f26ed7a754`.
Imported as an offline evaluation tool; no service, route, database migration, production deployment configuration or runtime irrigation consumer is added.

## Run from the repository root

```sh
cd tools/sahool_qa
python -m pip install -r requirements-test.txt
python tools/run_checks.py
```

CI uses `--require-postgres`: a skipped database test fails acceptance. Local runs report skipped tests explicitly. The tests create a disposable PostgreSQL cluster; no production credentials are used. The current PostgreSQL tests use GeoJSON text, not live PostGIS.

## Scope and constraints

- Synthetic questions validate deterministic computations, not field agronomic accuracy.
- No real tenant data or generated question sets are committed. Regenerate the demo locally.
- Database use requires explicit tenant selection, a read-only DB role, schema mapping and a complete dated well inventory. Use `--require-well-inventory`. Administrative `--all-tenants` must never be exposed as a tenant-facing endpoint.
- This tool's water model remains an evaluation fixture. It must not replace the platform's canonical root-zone/water models without a separate adapter and parity tests.
- Live schema mapping, PostGIS geometry path, production RLS, historical data vintages and field calibration remain unverified.
- README/CHANGELOG statements about past blind checks and PostgreSQL runs describe the original release. Archived verification files and previews remain in the supplied release archive; they are excluded from the source import.
- `run_checks.py` produces current test/demo evidence in an ignored verification directory. CI publishes that directory as an artifact.

- Schema: `migrations/init_v8.sql` names three columns differently from the tool defaults (`gov`/`lat`/`lon` on `field_boundaries`, `category` on `field_indicators`). Use `--schema-map examples/schema_map.init_v8.json`. `soil_readings` and `field_indicators` have no `geom` there; records attach to their field by `(tenant_id, field_id)`.
- The platform's `irrigation_*` tables are not a drop-in source for the water investigation. The differences are listed in README; a bridge must declare them rather than fill them:
  - per-measurement flow and runtime instead of totalizers;
  - `daily_used_m3` defaults to 0;
  - field bindings point at hydraulic nodes, not wells;
  - `live_state` has no history.

## Local import verification

Original 0.4.2 suite: 126 tests, 120 passed, 6 PostgreSQL tests skipped because server binaries are absent in this workspace. No claim of 126 local passes or production readiness.

## Review fixes (2026-10-15)

Behaviour and answers are unchanged: the train/val/test SHA-256 of the demo equal the release's.

Fixes:
- **Lint:** formatted with the pinned ruff 0.15.8 and the repository `ruff.toml`. There were 115 lint errors and 37 unformatted files.
- **Locale:** text I/O is UTF-8 regardless of locale.
  - Under `LC_ALL=C PYTHONUTF8=0` the `psql` driver failed 5 of the 8 PostgreSQL tests with `UnicodeDecodeError`.
  - Two test files failed the same way.
- **Workflow:** removed the uncapped `apt-get`, which `ci_unbounded_wait_guard` rejects and which broke *Unit Tests*. PostgreSQL 16 ships in the ubuntu-24.04 image.
- **Schema:** added the init_v8 schema map and two PostgreSQL tests for it.

Measured with PostgreSQL 16.15, Python 3.13:

| Check | Result |
|---|---|
| `run_checks.py --require-postgres` | 128 run, 0 failed, 0 skipped; two demo runs byte-identical, 538 items |
| Same suite under `LC_ALL=C PYTHONUTF8=0` | 128 OK |
| `check_patch_mutations_042.py` | 14/14 caught |
| `check_patch_mutations.py` | 6/6 caught |

This consolidates PR #1192, which imported the same release under the same path. #1192 is superseded by this PR.
