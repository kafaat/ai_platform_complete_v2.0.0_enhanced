# Railway auth deployment configuration

This repository contains separately deployed services. Do not put a service-specific
build override in a root `railway.json` or `railway.toml`: Railway configuration files
take precedence over dashboard settings and a root default can select the auth image
for another service using the same repository.

## Select the configuration for sahool-auth only

In the **sahool-auth** service settings, use:

| Setting | Value |
| --- | --- |
| Root Directory | `/` |
| Railway Config File | `/services/auth/railway.json` |
| Builder | `DOCKERFILE` |
| Dockerfile Path | `services/auth/Dockerfile` |

The custom configuration-file path must be selected explicitly; it is not inferred
from Root Directory. Keep the repository root as the build context because the
Dockerfile copies both `shared/` and `services/auth/`.

Do not select this config for platform, frontend, or migration services. They must
retain their own Dockerfile paths. This change adds no start-command, health-check,
variable, or deployment override.

## Activation and verification

Merging a pull request into main does not update a Railway service tracking a
different deployment branch. Apply the tested revision to the intended deployment
branch and verify its source SHA before starting a deployment. The per-service
dashboard builder/path settings also remain valid without a custom config file.

Preserve the existing build identity arguments `SAHOOL_GIT_SHA`, `SAHOOL_BUILD_ID`,
`SAHOOL_SOURCE_REPOSITORY`, and `SAHOOL_SOURCE_REF`. Confirm image build success and
the service health check separately; passing repository checks is not deployment
proof. The current Dockerfile listens on port 8000, so keep the service target port
consistent rather than assuming a PORT variable changes the Dockerfile command.

## Repository verification

```bash
git add -A
python scripts/ci/verify_all_generated.py --fix
python scripts/ci/capability_mapping_engine.py --check
python scripts/ci/verify_all_generated.py --check
python -m pytest -q tests/deploy/test_phase15_deployment_readiness_contracts.py
python scripts/release/validate_release_package.py
```

Generated outputs must be refreshed by their owning generators. Do not hand-edit
hashes, change maturity assertions, or relax drift gates to accommodate this file.

## MFA bootstrap enrollment (sensitive roles without MFA)

With `ENFORCE_SENSITIVE_MFA=true` (or `SAHOOL_ENV=production`), an account whose role is
in `REQUIRE_MFA_ROLES` (default `admin`) and has no MFA gets no session from
`/v1/auth/login` or `/v1/auth/refresh`. A freshly created admin (`_ensure_admin_user`)
would be locked out for good, so a verified password can buy a narrow enrollment
capability instead of a session:

1. `POST /v1/auth/login` (email + password) → **403**, header
   `X-MFA-Enrollment-Required: true`, body
   `{"detail", "enrollment_token", "expires_in": 300, "token_type": "Bearer"}`.
   Browser clients should key on the body: auth CORS exposes only `X-Tenant-ID`.
2. `POST /v1/auth/mfa/setup` with `Authorization: Bearer <enrollment_token>` → 200 with
   `secret`, `provisioning_uri` and a second `enrollment_token` (stage `activate`, 300 s).
3. `POST /v1/auth/mfa/activate` `{"code": "<TOTP>"}` with
   `Authorization: Bearer <activation enrollment_token>` → 200 with `recovery_codes`
   (shown once).
4. Log in again with password + `mfa_code` (use a code from the next 30 s step; the
   activation step is spent by anti-replay).

The proof's audience is `sahool-mfa-enrollment`; no other endpoint or service accepts it.
Each proof is single use and dies with any password, role, tenant or `active` change,
and the activation proof is bound to the exact encrypted secret written by setup. A
wrong activation code does not burn the proof (retry within the 300 s window), but a proof
allows at most 5 code checks: each attempt is reserved with an atomic `INCR` **before** the
code is checked, so parallel requests cannot exceed the cap; past it the proof is deleted
and the flow restarts at step 1. The account-level MFA lockout (`MFA_MAX_FAILED_ATTEMPTS`,
default 5) applies as well.

**Redis is required.** Proof digests live under `sahool:mfa:enrollment:*` (SETEX/GET/
GETDEL/INCR/EXPIRE/DEL; the `sahool-auth` ACL in `docker-compose.v9.yml` grants them).
Without Redis, or when Redis errors, the flow fails closed: login answers **503** and
issues no token, setup/activate answer 503. The rest of login is unaffected.

**Scope — `MFA_SELF_ENROLLMENT_SCOPE`** (read per request):

| Value | Who gets an `enrollment_token` |
| --- | --- |
| `bootstrap` (default) | an account that never enrolled (`mfa_enabled_at IS NULL`) **and** whose tenant has no other active MFA-required account with MFA enabled |
| `all` | every unenrolled MFA-required account (password-only trust on first use; use only for a supervised migration window) |
| `off` | nobody |

The "disable" spellings `false`, `0`, `no`, `none`, `disabled`, `disable` mean `off`.
Any other unknown value is treated as `bootstrap` (never widened to `all`) and logged as a
warning. The scope is
re-checked at setup and activate, so once one administrator of a tenant finishes
enrollment, proofs still in flight for that tenant stop working. Out of scope, login
keeps the pre-existing 403 (same header, `detail` only, no token); `mfa_audit_events`
records `mfa_enrollment_offered` / `mfa_enrollment_refused` with the hashed client IP.

For an out-of-scope account (a second admin, or one that disabled MFA), an enrolled
administrator either temporarily assigns a role outside `REQUIRE_MFA_ROLES`
(`PATCH /v1/auth/users/{id}/role`), lets the user log in and enroll through the normal
`/v1/auth/mfa/setup` → `/activate` flow with their access token, then restores the role
— or the operator sets `MFA_SELF_ENROLLMENT_SCOPE=all` for a short, supervised window.
"Never enrolled" reads `mfa_enabled_at`, which older rows may lack: an account that
enrolled before that column was written and later disabled MFA looks never-enrolled and,
if it is its tenant's only MFA-required account, gets the bootstrap offer. A tenant's sole
administrator who disables MFA is refused (previously enrolled) and must use the
role-swap or supervised `all` window above.
Note that every user created with the schema default gets its own random `tenant_id`,
so under `bootstrap` each such never-enrolled admin is its own tenant's bootstrap.

Live proof: `tests_v9/test_mfa_hardening_integration_v29_5.py::test_mfa_bootstrap_enrollment_on_real_postgres`
(Integration Tests → "MFA end-to-end via the real auth app (restricted role)").
