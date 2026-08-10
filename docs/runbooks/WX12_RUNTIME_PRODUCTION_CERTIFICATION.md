# WX-12 Runtime & Production Certification

This runbook converts WX-10/WX-11 code closure into runtime evidence. It does not permit a production flip from static evidence alone.

0. **Certify DB role separation first (read-only, zero risk).** Run
   `services/decision-service/decision_sor_role_certify.py` with both connection URLs. A shared role
   yields `role_separation_confirmed=false` ⇒ **no REVOKE**; create `decision_service_app` and move
   the decision-service connection first. See
   [`DECISION_SOR_CUTOVER.md`](DECISION_SOR_CUTOVER.md).
1. Apply/check **all** decision-service migrations with `DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true`
   using a restricted non-superuser, non-BYPASSRLS role — via the single supported wrapper
   `scripts/deploy/decision_service_migrate.sh`, never a hand-picked subset. The set is `001…` and
   **grows**; measure it, never assume a ceiling:
   `ls services/decision-service/migrations/*.sql | wc -l` (31 at the time of writing).
2. Run `scripts/wx12/postgres_certification.py` and the real-Postgres decision-service test suite, including concurrency/idempotency tests.
3. Deploy the registry adapter with `MODEL_REGISTRY_BACKEND=http`, TLS endpoint, token from secret storage, unique `REGISTRY_ADAPTER_ID`, and dry-run disabled only after staging approval.
4. Run an activation/rollback drill in staging and validate evidence using `staging_activation_rollback_drill.py`.
5. Enable shadow, then canary, then full traffic through an external traffic controller. A rollout plan row alone is not execution evidence.
6. Run monitoring and retraining dispatchers. Retraining output must re-enter evaluation/promotion/activation governance; no automatic promotion.
7. Remove endpoint waivers only after operations UI E2E tests exist.
8. Execute SoR promotion using existing fail-closed promotion gates. Live promotion requires the explicit production approval flags already documented by the Decision-Service SoR runbook.
9. Archive CI logs, migration report, RLS proof, registry receipts, active-state projection, rollback evidence, canary metrics, backup/restore evidence, and operator approval.

Production is closed only when every matrix row is PASS with a durable evidence URI and reviewer.
