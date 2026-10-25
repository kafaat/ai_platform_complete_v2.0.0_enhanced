# Local integration lab

Runs the `pytest -m integration` suite against real PostgreSQL/PostGIS and Redis on
one machine, the way the CI **Integration Tests** job does, and writes evidence of
what it measured.

```bash
bash scripts/lab/up.sh     # Docker daemon if absent, images by digest, migrations x2, venv
bash scripts/lab/run.sh    # integration + OpenTelemetry suites + CI certification steps, evidence JSON
bash scripts/lab/down.sh   # removes only containers labelled sahool.lab=integration
bash scripts/lab/down.sh --purge   # also deletes $SAHOOL_LAB_DIR (venv, logs, evidence)
```

`SAHOOL_LAB_DIR` (default `${TMPDIR:-/tmp}/sahool-lab`) holds the venv, the logs and
`evidence/<UTC stamp>/lab_evidence.json`. Nothing there persists in an ephemeral
container: copy the evidence directory out before the container ends.

## What it pins, and where it differs from CI

| Input | Lab | CI Integration Tests |
|---|---|---|
| Redis | `library/redis@sha256:858f009f…` | same digest |
| PostgreSQL | `postgis/postgis@sha256:6f4773bf…` (15-3.6: PostgreSQL 15.19, PostGIS 3.6.4, Debian 13) | `postgres@sha256:d4a8e1f8…` (15.19, Debian 12) plus `postgresql-15-postgis-3` from apt |
| Ports, database, user | 5433 / 6380, `sahool_test` | same |
| Python deps | fresh venv from `tests_v9/requirements-test.txt` (+ `constraints-ci-tools.txt`) | same files |
| Certification switches | `HIL_`, `CLAIM_LEASE_`, `RECONCILIATION_RESUMPTION_`, `MIGRATOR_CERTIFICATION_REQUIRED=1` | same |
| Restricted-role certification steps | read from `ci.yml` at run time and run as written | the steps listed below |

The PostgreSQL difference exists because the CI image installs PostGIS from
`deb.debian.org`, which an egress-restricted sandbox may not reach. Images are
pinned by manifest digest; `up.sh` tries `public.ecr.aws/docker`, `mirror.gcr.io`
and `docker.io` in order and accepts an image only when its `RepoDigests` carry the
pinned digest.

## Restricted-role certification steps

After the shared suites, `run.sh` calls `run_certification.py`, which reads
`.github/workflows/ci.yml` and runs every step of the `integration-tests` job that
follows the shared `pytest -v -m integration --tb=short` step. Each step's `run`
text is executed with `bash -eo pipefail` and exactly that step's `env` (the
variables `run.sh` exported for the shared suite are removed first), so the
restricted role SQL, the DSNs and the `*_CERTIFICATION_REQUIRED` switches are the
CI ones, not a copy. `pytest` on PATH is a shim to the lab venv that adds
`--junitxml` and a log per call, so each pytest call is its own suite
(`certNN_<call>_<test file>`). A step the lab cannot run as written (an action,
a `${{ }}` expression, an `if`/`shell`/`working-directory` override) stops the run.

Steps run today (`tests_v9/test_lab_ci_certification_steps.py` fails CI when this
list, the runner's reading of `ci.yml` or the test files drift apart):

1. Create restricted application role for RLS certification
2. IRR-F01 fresh-schema certification (Gate A + Gate B1)
3. IRR-F01 upgrade certification (Gate U1 — v194→v195/v196)
4. H5.1 field↔source binding certification (real-PG, restricted role)
5. RLS tenant isolation certification (real-PG, restricted role)
6. Imagery automation RLS certification (migrated policy, restricted role)
7. D1 raster invalidation queue RLS certification (migrated v96 policy, restricted role)

Afterwards the runner reads `rolsuper`, `rolbypassrls`, `rolinherit` and
`rolcanlogin` of every restricted role those steps connect as (`sahool_app_test`)
from `pg_roles`; either of the first two true fails the run. Steps, exit codes,
switches, suites and role flags are recorded under `ci_certification_steps` in
`lab_evidence.json`, and the verdict is `PASS` only when all of them pass.

## What it does not cover

- Load, timing or production behaviour: one small machine, DEV evidence,
  independence none.
