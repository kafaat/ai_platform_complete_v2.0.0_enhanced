# SAHOOL Remote Sensing RS-6 / RS-7 Implementation Report

Date: 2026-07-15

## Scope

Implemented the next two increments on top of RS-1 through RS-5:

- RS-6: signal anomaly detection and lifecycle
- RS-7: ownership-safe ground verification bridge

## RS-6 Signal Anomaly Lifecycle

Added:

- `services/vegetation-analysis-service/anomaly_engine.py`
- `services/vegetation-analysis-service/anomaly_store.py`
- `services/vegetation-analysis-service/routers/anomalies.py`

Capabilities:

- Detects signal deviations only; does not emit agronomic diagnoses.
- Consumes canonical observation baselines from RS-5.
- Deterministic anomaly and detection-run references.
- Configurable material-deviation threshold.
- Severity classification: info/low/medium/high/critical.
- Confidence derived from baseline confidence, sample size, and severity.
- Deduplicates multiple baseline findings for one current observation by selecting the strongest signal.
- Explicit state machine with optimistic concurrency.
- Durable SQLite state owned by vegetation-analysis only.
- Persistent path configured as `/data/vegetation/anomalies.db`.

Routes:

- `POST /v1/fields/{field_id}/signal-anomalies/detect`
- `GET /v1/fields/{field_id}/signal-anomalies`
- `POST /v1/anomalies/{anomaly_ref}/transition`

State transitions:

`detected -> triaged|verification_requested -> confirmed|rejected|inconclusive -> diagnosis_proposed -> decision_referred -> resolved`

Invalid transitions and aggregate-version conflicts return conflict semantics.

## RS-7 Ground Verification Bridge

Added:

- `services/vegetation-analysis-service/ground_verification_bridge.py`

Capabilities:

- Creates scouting tasks through a configurable task-service API only.
- Does not write task tables or query another service database.
- Sends anomaly references and verification context, not diagnoses or prescriptions.
- Uses deterministic idempotency keys.
- Converts task IDs to opaque `urn:sahool:task:*` references.
- Fails closed when `TASK_SERVICE_URL` is not configured.
- Verification callbacks require `TASK_SERVICE_CALLBACK_TOKEN`.
- Task service reports completion; vegetation-analysis remains the only owner that changes anomaly disposition.

Routes:

- `POST /v1/anomalies/{anomaly_ref}/verification-requests`
- `POST /v1/anomalies/{anomaly_ref}/verification-results`

The result route accepts only `confirmed`, `rejected`, or `inconclusive`, validates task-reference parity, and applies optimistic concurrency.

## Deployment Configuration

Updated `docker-compose.v9.yml` and `docker-compose.fixed.yml` with:

- `TASK_SERVICE_URL`
- `TASK_SERVICE_CALLBACK_TOKEN`
- `VEGETATION_ANOMALY_DB_PATH=/data/vegetation/anomalies.db`
- persistent `vegetation-anomaly-data` volume

## Tests

Combined targeted regression gate:

```text
70 passed
0 failed
```

Coverage included:

- anomaly detection thresholds and signal-only semantics
- anomaly deduplication
- lifecycle state transitions
- optimistic concurrency
- invalid-transition rejection
- task bridge request contract
- RS-1 contract tests
- RS-2 raster persistence policy
- RS-3 indicators adapter
- RS-4 timeline
- RS-5 baselines
- all vegetation-analysis regression tests

`python -m compileall` also passed.

## Honest Remaining Boundary

The repository does not contain a standalone deployed service named `task-service` with `POST /v1/tasks/scouting`. Therefore RS-7 implements and certifies the anti-corruption bridge and callback boundary, but a live end-to-end task creation test requires the real task-domain deployment URL and callback secret. The bridge fails closed rather than writing into `sahool-platform` or inventing a new task database.

## Next Increments

- RS-8: diagnosis hypothesis and decision-service referral bridge
- RS-9: workspace BFF aggregation
