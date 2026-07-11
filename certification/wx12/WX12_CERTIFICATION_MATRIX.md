# WX-12 Certification Matrix

| Gate | Required evidence | Status |
|---|---|---|
| DB-01 migrations 001–014 | migration runner post-check | PENDING_RUNTIME |
| DB-02 restricted role | rolsuper=false, rolbypassrls=false | PENDING_RUNTIME |
| DB-03 RLS/tenant isolation | real PostgreSQL tests | PENDING_RUNTIME |
| DB-04 concurrency/idempotency | parallel claim/receipt tests | PENDING_RUNTIME |
| REG-01 activation CAS | registry request + receipt + digest | PENDING_RUNTIME |
| REG-02 rollback CAS | restored digest + active-state proof | PENDING_RUNTIME |
| ROL-01 shadow/canary | traffic-controller evidence and metrics | PENDING_RUNTIME |
| MON-01 monitoring worker | snapshots, lag, DLQ evidence | PENDING_RUNTIME |
| RET-01 retraining dispatcher | immutable manifest and job receipt | PENDING_RUNTIME |
| UI-01 operations UI | E2E evidence and waiver removal | PENDING_RUNTIME |
| SOR-01 production flip | promotion gate evidence | PENDING_OPERATOR |
| CERT-01 backup/restore | successful drill | PENDING_RUNTIME |
| CERT-02 post-deploy | smoke, health, error budget | PENDING_RUNTIME |
