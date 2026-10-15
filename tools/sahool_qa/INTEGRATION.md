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

## Local import verification

Original 0.4.2 suite: 126 tests, 120 passed, 6 PostgreSQL tests skipped because server binaries are absent in this workspace. No claim of 126 local passes or production readiness.
