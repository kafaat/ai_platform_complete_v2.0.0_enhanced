# S5 Live Authority Closure — Decision / Field / Knowledge Graph

This runbook executes the **remaining live evidence** for the S5 authority sequence. It does not
promote authority and it does not perform physical shrink. A green bundle means only:
`READY_FOR_AUTHORITY_ADJUDICATION`.

## Subject rule

Run from a **real Git checkout** at the exact CI-green commit that was built and deployed. Do not
run from a delivery ZIP and do not reuse the historical `71108f2e` base after applying later
continuations. The subject is the commit that contains the reviewed S5 continuation:

```bash
export SUBJECT_SHA="$(git rev-parse HEAD)"
test "$(git rev-parse HEAD)" = "$SUBJECT_SHA"
```

The Decision receipt binds both deployed runtime identities to this SHA. Field binds the checkout
SHA to the deployed Field source digests. KG binds the checkout SHA to the deployed KG source
digests; operator text alone is not accepted as provenance.

## Required live environment

Decision database evidence:

```bash
export DECISION_SOR_PLATFORM_URL='postgresql://...restricted platform role...'
export DECISION_SOR_SERVICE_URL='postgresql://...restricted decision-service role...'
export DECISION_SOR_ADMIN_DATABASE_URL='postgresql://...table owner/admin...'
export DECISION_SOR_PLATFORM_ROLE='sahool_app'
export DECISION_SERVICE_URL='https://decision.example'
export SAHOOL_PLATFORM_URL='https://platform.example'
# Optional bearer secret; keep in environment only.
export DECISION_SERVICE_AUTH_TOKEN='...'
```

Field RLS evidence:

```bash
export DATABASE_URL='postgresql://...NOBYPASSRLS application role...'
export SAHOOL_AGENT_TOKEN='...'
export FIELD_SERVICE_URL='https://field.example'
export TENANT_A='...owner tenant uuid...'
export TENANT_B='...different tenant uuid...'
export FIELD_A='...field owned by TENANT_A...'
```

The Field integration proof performs a synthetic live PostgreSQL isolation test under the
restricted application role; it is evidence execution, not a read-only probe.

Knowledge Graph parity evidence:

```bash
export KG_SERVICE_URL='https://knowledge-graph.example'
export KG_TENANT_ID='...tenant with governed parity cases...'
```

## 1. Preflight

```bash
python scripts/staging/s5_live_authority_closure.py preflight \
  --subject-sha "$SUBJECT_SHA" \
  --output artifacts/s5-live-authority/preflight.json
```

Exit 0 is required. Missing `psql`, missing environment, a non-Git delivery ZIP, or a checkout SHA
mismatch is a harness failure and must not be interpreted as authority evidence.

## 2. Decision cutover prerequisite

The collector does **not** run GRANT/REVOKE and does not flip application authority. Complete the
operator-controlled Decision cutover first using the existing Decision SoR runbook: deployed
Decision must report system-of-record mode, Platform must report effective `decision_service_sor`,
and the DB-level platform write revoke must already be in force. The collector measures these
postconditions with read-only checks.

## 3. Collect and verify all three receipts

```bash
python scripts/staging/s5_live_authority_closure.py collect \
  --subject-sha "$SUBJECT_SHA" \
  --decision-url "$DECISION_SERVICE_URL" \
  --platform-url "$SAHOOL_PLATFORM_URL" \
  --out-dir artifacts/s5-live-authority
```

Expected outputs:

- `decision-live-closure.json`
- `field-rls-live-evidence.json`
- `kg-runtime-parity.json`
- `s5-live-authority-bundle.json`

Each domain receipt is re-run through its canonical receipt guard. The bundle is `PASSED` only if
all three guards pass on the same subject. It always records `authority_promotion=false` and
`physical_shrink_authorized=false`.

## 4. Existing receipts — verify only

```bash
python scripts/staging/s5_live_authority_closure.py verify \
  --subject-sha "$SUBJECT_SHA" \
  --decision-receipt artifacts/s5-live-authority/decision-live-closure.json \
  --field-receipt artifacts/s5-live-authority/field-rls-live-evidence.json \
  --kg-receipt artifacts/s5-live-authority/kg-runtime-parity.json \
  --output artifacts/s5-live-authority/s5-live-authority-bundle.json
```

## 5. Adjudication boundary

A green bundle permits a **separate reviewed authority adjudication**. It does not itself edit
`docs/architecture/authority_cutovers.json`. Physical shrink remains blocked until the authority
states are explicitly updated and the end-state guards pass.

The first post-adjudication physical shrink batch is S5-EXEC-02: retire the six frozen Platform
runtime write edges recorded in `docs/architecture/s5_exec_01_edge_freeze.json` while preserving
compatibility/read facades. Do not delete those pre-cutover writers while Decision remains
`INTERIM`.
