# Local irrigation certification

From the repository root, with Python 3.12, Bash 4+, Make, zip and Docker Compose v2 installed, run:

```bash
python3.12 -m venv .venv-irr && . .venv-irr/bin/activate && python -m pip install -r requirements-irr-f01-test.txt && make test-irr-f01-local
```

The default starts a dedicated PostGIS 15-3.4 container on an ephemeral loopback port. For a host installation of PostgreSQL 15 with PostGIS 3, contrib, and the server/client executables on PATH, run `IRR_F01_BACKEND=native make test-irr-f01-local` in the same virtual environment as a non-root user. Both modes build and remove their own cluster. Neither requires a pre-existing database or credentials.

The fresh database starts from PostgreSQL's empty template. The gate applies `migrations/MANIFEST.txt` with the CI migration runner and compares every applied filename with the manifest in order. A second database receives the manifest through v194, seeded legacy irrigation rows, then v195 and v196 twice. CI and the developer gate use `run_suite.sh` for both databases. Required JUnit cases cover reservation concurrency, replay, the outbox, tenant visibility and the upgrade. A missing, skipped or failing case invalidates the run.

Each invocation prints its evidence directory under `artifacts/irr-f01-local-test/`. It contains server and PostGIS versions, the observed migration order, logs, schema snapshot, JUnit files and a zipped report. `REPORT_DIR` changes the parent directory. The decision-service login has read-only access to the irrigation tables. The lab creates a separate decision database, applies the service migrations, then delivers the reservation event twice. Both deliveries resolve to one tenant-scoped inbox receipt. The loopback MQTT test issues a signed lab command for a committed reservation, publishes it twice, and records the simulated device’s single effect. The production path from a decision-service inbox receipt to an authorized execution request is outside that test.
