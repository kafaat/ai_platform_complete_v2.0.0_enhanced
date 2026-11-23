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
| `psql`, `pg_isready` on the host | the host's own client (PostgreSQL 16 here) | `scripts/ci/provision_pg_client.sh` shims that run the container's client |
| Python deps | fresh venv from `tests_v9/requirements-test.txt` (+ `constraints-ci-tools.txt`) | same files |
| Certification switches | `HIL_`, `CLAIM_LEASE_`, `RECONCILIATION_RESUMPTION_`, `MIGRATOR_`, `FIELD_GEOMETRY_`, `FIELD_TIMELINE_`, `NOTIFICATION_DELIVERY_CERTIFICATION_REQUIRED=1` | same |
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
restricted role SQL, the DSNs, the `*_CERTIFICATION_REQUIRED` switches and the
raster step's mandatory JUnit adapter are the CI ones, not a copy. `pytest` on PATH
is a shim to the lab venv that adds
`--junitxml` and a log per call, so each pytest call is its own suite
(`certNN_<call>_<test file>`). A step the lab cannot run as written (an action,
a `${{ }}` expression, an `if`/`shell`/`working-directory` override) stops the run.
The job ends with Codecov reporting steps, from `Export live auth coverage with
Git-relative paths` on (export, path guard, pinned upload), followed by a pinned
`Preserve raster PostgreSQL certification evidence` artifact upload. Its exact name,
directory, always-run condition and retention contract are checked; arbitrary actions
or commands remain refused. The lab retains its JUnit and JSON locally and stops before
these remote reporting steps. A step's relative `COVERAGE_FILE` is written into the evidence directory, so
the live coverage every certification step appends does not dirty the checkout.

Steps run today (`tests_v9/test_lab_ci_certification_steps.py` fails CI when this
list, the runner's reading of `ci.yml` or the test files drift apart):

1. Create restricted application role for RLS certification
2. IRR-F01 fresh-schema certification (Gate A + Gate B1)
3. IRR-F01 upgrade certification (Gate U1 — v194→v195/v196)
4. Exercise raster leases and scene enqueue as the restricted application role
5. H5.1 field↔source binding certification (real-PG, restricted role)
6. RLS tenant isolation certification (real-PG, restricted role)
7. Imagery automation RLS certification (migrated policy, restricted role)
8. D1 raster invalidation queue RLS certification (migrated v96 policy, restricted role)
9. MFA end-to-end via the real auth app (restricted role)
10. Auth admin tenant scope (C-01, real auth app, restricted role)
11. Auth admin authz gates (#1427, concurrent invitation, Redis outage, stale membership)
12. Platform denial log tenant scope (#1427, real platform app, live Redis)
13. Platform denial log persistence (audit_log, restart, outage, restricted role)
14. soil-service functional H5 + guardrails L5 (restricted role)
15. Field recommendations 503 rolls back field_state (restricted role)
16. Soil-sampling plan copies (gap P6, real-PG, restricted role)
17. Water ledger ET0 elevation and rain provenance (W0-10, real-PG)
18. Model promotion waits for an external ack and leaves the queue (F-D04, real-PG)
19. Field task inspection and cost trace (v274-v277, restricted role)
20. Harvest custody integrity and market lot link (v278, restricted role)
21. Vegetation anomaly scouting tasks (W1-20, v282, restricted role)
22. Vegetation anomaly verification reservation (restricted role)
23. Water ledger partial irrigation write (W0-13, v280, restricted role)
24. NDVI seed purge (W1-21, v283, real-PG)
25. Farm water to the water ledger (W1-13, v284, restricted role)
26. Farm ledger season and currency governance (W1-14, W1-12, v281, restricted role)
27. Farm scope grants and policies (SC-1, v287, restricted role)
28. Soil hydraulic projection (W1-04, restricted role)
29. Yield estimate from server evidence (W1-08, restricted role)
30. Edge sync carries the verified tenant per request (W0-07, restricted role)
31. Internal routes require a tenant assertion (W0-05, restricted role)
32. Yield estimate is tenant-checked (W0-11, restricted role)
33. Actuator command delivery state and v2 device acks (v238, R-C2, restricted role)
34. Field and Water twins read the active season (restricted role)
35. Field-season state reads its platform sources (restricted role)
36. Historical weather ingest and replay over HTTP (two tenants, restricted role)
37. Canonical observations store (W1-11, v286, restricted role)
38. Install pinned nats-server for the W3-01 outbox proof
39. NATS outbox staging enablement on real PostgreSQL and JetStream (W3-01)
40. Work order creates its field task and records the close outcome (G3, real-PG)
41. Field task on an API-created field (G3, real-PG)
42. Governed learning proposals are reviewed under RLS (G14, real-PG)
43. Weather save refuses a point outside the field (G1, real-PG)
44. Farm ledger deducts a named inventory batch once (G6, real-PG)

The raster step loads `scripts.raster_pg.required_cases`, which requires all seven
live cases without skips, failures or duplicates. It validates the JUnit path
actually selected by pytest (including the lab shim's override), then delegates
database, schema and role evidence to `scripts.ci.live_pg_evidence_guard`. The integration job selects
the PostgreSQL 15 raster schema contract. The dedicated PostgreSQL 16 job runs the
same cases with `--raster-pg-major=16`, its own raster schema contract, application
role and evidence artifact.
Evidence records the selected contract's path and SHA256. A missing case or failed
check fails the pytest process; no optional environment switch is needed for this
adapter. Single-scene insertion and lease acquisition each run with two and eight
workers. The scene test synchronizes the real database reads before any contender
creates a run, proving the losing inserts and their cleanup are exercised.

Afterwards the runner reads `rolsuper`, `rolbypassrls`, `rolinherit` and
`rolcanlogin` of every restricted role those steps connect as (`sahool_app_test`)
from `pg_roles`; either of the first two true fails the run. Steps, exit codes,
switches, suites and role flags are recorded under `ci_certification_steps` in
`lab_evidence.json`, and the verdict is `PASS` only when all of them pass.

Step 35 downloads nats-server v2.15.0 from github.com into
`/tmp/sahool-nats-server-v2.15.0/` and checks the sha256 that
`notification-rollout.yml` pins. Without network to github.com, place the release
tarball there as `nats-server.tar.gz` first: it is used only if it matches that
digest, otherwise the step fails (and step 36 fails rather than skips).

## What it does not cover

- Load, timing or production behaviour: one small machine, DEV evidence,
  independence none.
