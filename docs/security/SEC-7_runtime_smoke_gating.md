# SEC-7 — Runtime smoke gating (mandatory live checks)

**Review finding (7):** *live/runtime tests are not a mandatory merge gate; the full E2E/chaos
runtime job runs only under `workflow_dispatch && vars.RUN_LIVE_RUNTIME_TESTS == 'true'`.*

## Verdict: partially already-satisfied, one residual needs infra

Verified against `.github/workflows/ci.yml`, `.github/workflows/sahool-production-gates.yml`,
`scripts/runtime_smoke.sh`, and the existing smoke tests.

### Already MANDATORY on every push (incl. `main`)

`ci.yml` is `on: [push, pull_request]`, so these run on every branch/PR and on `main`:

| Mandatory runtime check | Where | Evidence |
|---|---|---|
| Postgres+PostGIS+Redis brought up | Integration Tests job | `ci.yml:216` |
| **Migrations applied to a real DB** | Integration Tests job | `ci.yml:241` |
| **`pytest -m integration`** (RLS isolation, cross-tenant blocked, every v127–v140 migration verified on live Postgres) | Integration Tests job | `ci.yml:253` |
| **RLS write-policy gate (Phase 22)** | Security Scan job | `ci.yml:316` |
| Docker-compose files parse + no orphan `depends_on` | Validate Docker Compose job | — |

So the reviewer's "migrations / RLS runtime mandatory" is **already enforced** as a hard merge
gate. The append-only / lease / kill-switch / geometry-validity behaviours (v133–v140) are all
exercised on real Postgres here, by name.

### The genuine residual: live HTTP `/healthz` smoke against running services

`scripts/runtime_smoke.sh` curls `/healthz` on nginx → raster/rag/knowledge-graph/ai-agronomist/
guardrails. The existing `tests_v9/test_smoke_e2e.py` / `test_spatial_e2e_smoke.py` do the same but
**skip** when no live stack is present, and the live runtime/E2E/chaos job in
`sahool-production-gates.yml` is gated behind `workflow_dispatch && RUN_LIVE_RUNTIME_TESTS`.

Making this **mandatory** requires bringing the **full compose stack up in CI** (nginx + the app
services + datastores), which is heavy (40+ containers, image pulls, health waits) and a real
flakiness/runner-cost risk. It is deliberately **not** enabled here as an unvalidated blocking job,
because a flaky compose-up would red `main` on infra noise — worse than the gap it closes.

## Ready-to-enable job (operator decision)

Add to `sahool-production-gates.yml` (runs on push to `main` + `release/**`). Enable once a runner
with the compose budget + a resilient image-pull mirror is confirmed:

```yaml
  runtime-smoke:
    name: Runtime smoke (core services)
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Bring up core stack
        run: |
          docker compose -f docker-compose.v9.yml up -d \
            sahool-postgres sahool-redis sahool-nats \
            sahool-migrate sahool-auth sahool-nginx sahool-ai-agronomist
      - name: Wait for readiness
        run: |
          for i in $(seq 1 60); do
            curl -fsS http://localhost/healthz && break || sleep 5
          done
      - name: Runtime smoke
        run: BASE_URL=http://localhost bash scripts/runtime_smoke.sh
      - name: Dump logs on failure
        if: failure()
        run: docker compose -f docker-compose.v9.yml logs --tail 100
```

Scope it to the **core** subset first (auth + nginx + one app service + datastores) rather than the
full 40-service stack, to bound flakiness; expand once stable. Keep chaos/soak/load manual
(`workflow_dispatch`) — only `readyz`/health smoke belongs on the mandatory path.

## Status

- Migrations + RLS + schema runtime: **already a hard gate on `main`** (no change needed).
- Live HTTP `/healthz` smoke: **ready-to-enable** above; left operator-gated to avoid destabilising
  `main` with an unvalidated heavy compose-up job. This is a deliberate, documented decision — not
  an oversight.
