# Local integration lab

Runs the `pytest -m integration` suite against real PostgreSQL/PostGIS and Redis on
one machine, the way the CI **Integration Tests** job does, and writes evidence of
what it measured.

```bash
bash scripts/lab/up.sh     # Docker daemon if absent, images by digest, migrations x2, venv
bash scripts/lab/run.sh    # integration + pinned OpenTelemetry suites, evidence JSON
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

The PostgreSQL difference exists because the CI image installs PostGIS from
`deb.debian.org`, which an egress-restricted sandbox may not reach. Images are
pinned by manifest digest; `up.sh` tries `public.ecr.aws/docker`, `mirror.gcr.io`
and `docker.io` in order and accepts an image only when its `RepoDigests` carry the
pinned digest.

## What it does not cover

- The later CI steps of the same job (restricted-role RLS certifications, IRR-F01
  upgrade gate U1, H5.1). They need the restricted application role; add them here
  before claiming parity.
- Load, timing or production behaviour: one small machine, DEV evidence,
  independence none.
