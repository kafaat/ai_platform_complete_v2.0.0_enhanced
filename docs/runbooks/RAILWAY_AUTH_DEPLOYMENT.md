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
