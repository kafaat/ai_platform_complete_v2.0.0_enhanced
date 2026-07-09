# Decision-service SoR Staging Probe Runbook

This runbook is for **staging only**. It prepares evidence for a later SoR promotion. It does not authorize production cutover.

## Operator sequence

1. Run dry-run first:

```bash
python services/decision-service/staging_probe.py
```

2. Prepare staging environment variables:

```bash
export SAHOOL_ENV=staging
export DECISION_SERVICE_STAGING_PROBE_APPROVED=true
export DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE=true
export DECISION_SERVICE_URL=https://decision-service.staging.example
export SAHOOL_PLATFORM_URL=https://platform.staging.example
export DATABASE_URL=postgresql://...
```

3. Run live non-mutating checks:

```bash
python services/decision-service/staging_probe.py --live
```

This executes:

- `migration_runner.py --check`
- `backfill.py --verify-counts`
- `GET /v1/cutover/readiness`

4. Optional staging noop write:

```bash
python services/decision-service/staging_probe.py --live --sample-write \
  --tenant-id <staging-tenant> \
  --field-id <staging-field> \
  --idempotency-key decision-sor-staging-probe-001
```

The sample write must run only against staging data and only while `SAHOOL_DECISION_WRITE_MODE=shadow`.

## Safety rules

- do not run in production
- do not set `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true` from this probe
- do not demote sahool-platform based on this probe alone
- do not run sample writes without a dedicated staging tenant and field
- rollback means returning to `SAHOOL_DECISION_WRITE_MODE=platform_sor` and `DECISION_SERVICE_SOR_ENABLED=false`
