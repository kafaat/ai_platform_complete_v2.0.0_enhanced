# SAHOOL Railway–GitHub Actions: staging-only connection proof

This is a read-only recovery route for checking Railway project-token access from GitHub Actions. It does not renew the ChatGPT–Railway OAuth session, reconnect Railway's installed GitHub App, deploy SAHOOL, run migrations, access database credentials or certify runtime.

## Frozen scope, from existing SAHOOL runbooks

- Repository: kafaat/ai_platform_complete_v2.0.0_enhanced.
- Project ID: 33c50993-1110-43eb-8e92-04c15edae51e, named sahool-staging.
- Staging environment ID: 70cc51f8-b11f-4506-87b2-4b6615e472be.
- Production environment ID: 79de27a7-dae8-4cae-b37e-e9f7fae66c1d. Never use it here.
- Source of record: docs/runbooks/REMAINING_RUNTIME_ACCEPTANCE_20261016.md and docs/runbooks/RAILWAY_DEPENDENCY_RECOVERY.md.

## Setup after Railway access is restored

1. In the Railway dashboard, create a fresh Project Token scoped to the existing SAHOOL staging environment. Do not reuse any revoked token. Do not create an account-wide token for this check.
2. In the GitHub repository, use Settings > Secrets and variables > Actions to add the repository secret SAHOOL_RAILWAY_STAGING_PROJECT_TOKEN. Never put its value in a GitHub PR, chat, logs, workflow inputs or the workflow YAML.
3. After this workflow is merged under normal tested-head SAHOOL policy, open Actions > SAHOOL Railway staging connection preflight > Run workflow. Select main and enter its exact 40-character current commit SHA as expected_sha.
4. Require a successful result and download the sanitized artifact sahool-railway-staging-connection-(sha). It must report CONNECTION_ONLY_PASS, exact project and staging IDs and deployment_performed=false. Raw CLI JSON and stderr are never uploaded.
5. A missing/expired token, wrong project/environment ID, stale commit, Railway outage or unreadable CLI response must fail closed. A failed status is not by itself evidence of a revoked token.

## Proof limits and next operation

This action uses pinned Railway CLI 5.63.1 with exactly one Railway read: railway status --json scoped to staging. Its project token is provided only to that step; npm installation has no token. The receipt contains only allowlisted fields and the verifier's SHA256. The PR runs parser contract tests offline, without secrets.

Success only means that a staging project token can read the staging context. It does not imply production readiness, database access, healthy containers, correct runtime identity, successful user flows, or reconnection of ChatGPT OAuth.

Before any Stage-2 staging rollout: verify the tested SHA, actual deployed source branch and build identity, relevant Postgres/NATS backup evidence and migration state, and obtain explicit coordinated approval. Do not switch the production platform branch, enable SAHOOL_MIGRATE_APPLY, probe through the migrator, or promote any gap to verified using this receipt.

Technical references: https://docs.railway.com/cli/status ; https://docs.railway.com/cli/deploying ; https://docs.railway.com/cli/login .

## Railway CLI JSON source contract (v5.63.1)

The command railway status --json --project ID --environment ID returns the
raw project object: the project ID is a top-level id, and the environment
is in environments.edges[].node. The CLI scopes the edge list to the
explicitly selected environment. It does not return a project/environment
wrapper. The verifier requires exactly one accessible staging edge and
refuses missing, extra, inaccessible or production environments.

Source: https://github.com/railwayapp/cli/blob/v5.63.1/src/commands/status.rs

This contract is validated offline; no Railway token or live deployment
was used while preparing this change. The final live proof still requires
an operator-provided staging token and an exact-main-SHA manual dispatch.
