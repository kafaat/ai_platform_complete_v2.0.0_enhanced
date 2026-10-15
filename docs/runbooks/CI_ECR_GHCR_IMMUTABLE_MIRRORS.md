# CI image supply: digest-identical GHCR mirrors for ECR 429

## Scope and immutable identity

The `public.ecr.aws` public quota caused `HARNESS_INVALID` failures before
PostgreSQL/PostGIS or nginx tests began. A green targeted retry did **not**
prove registry resilience. PR #1193 adds a separate GHCR image mirror, built
from **exactly the already-locked upstream OCI manifest SHA-256 indexes**.
It does not change the image version or runtime deployment Dockerfiles.

| Component | Pinned upstream OCI index SHA-256 |
|---|---|
| Postgres 15 | `d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae` |
| Postgres 16 | `ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d` |
| Postgres 16 Alpine | `721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| Redis 7 Alpine | `858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` |
| nginx 1.27.5 | `65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` |

The bootstrap uses `skopeo inspect --raw`, `sha256sum --check`,
`skopeo copy --all --preserve-digests`, and another raw SHA check. Only
GHCR packages that produce the original SHA are accepted. A Docker Hub
source is permitted only when it provides that *same digest*, never a tag
substitution.

The GHCR pull uses
`ghcr.io/kafaat/sahool-ci-<name>@sha256:<original index digest>`.
`scripts/ci/pull_verified_ci_image.sh` requires the source allowlist and
tries GHCR with `GITHUB_TOKEN` and `packages:read` first. For Docker
`run` it emits a **local config ID**; for Docker BuildKit `FROM` it emits
the **digest-qualified registry reference**. Treating the config ID as
a `FROM` image led BuildKit to `docker.io/library/sha256` and was
proven incorrect by first-head CI.

If GHCR is unavailable, the script may use the original ECR digest and the
existing bounded retry/429 classification. If both sources are unavailable,
it fails closed; `NOT_STARTED` / `HARNESS_INVALID` is not an integration
pass. Do not use `continue-on-error`, unpinned tags, credential echoes,
or a fake PostgreSQL service to turn a failed dependency into a green check.

## Activation and validation

1. Run `.github/workflows/ci-immutable-image-mirror.yml` with repository
   `packages:write` permission. Verify **five successful matrix jobs**,
   including the source and destination manifest digest evidence.
2. Run `.github/workflows/ci-immutable-image-mirror-verification.yml`.
   The live job **requires all five pulls from GHCR** and rejects a successful
   ECR fallback as insufficient evidence of mirror availability.
3. Review `tests_v9/test_ci_image_mirror.py`,
   `tests_v9/test_resilient_docker_pull.py`, and
   `tests/architecture/test_notification_rollout_postgres_image.py`.
   They verify GHCR first, ECR fallback, 429 fail-closed semantics, and
   real database health in the notification job.
4. Confirm final-head required GitHub CI gates, including Decision,
   Integration, Live PG, notification, nginx runtime and security, then
   re-check on `main` after merge. A bootstrap success on an *earlier*
   source head does not certify application tests on the latest head.

No Railway deployment, database migration, application secrets, or image
rebuild is part of this CI-only scope. Registry package visibility is
independent of GitHub source visibility and must be readable by the Actions
`GITHUB_TOKEN` in the destination repository. GHCR is a separate dependency
with its own quota, availability and permissions; this design removes ECR
as a *single* dependency for fixture startup, not every possible image
registry failure.

## Operational recovery

If a new job reports `CI_IMAGE_SOURCE=ECR_PINNED`, inspect whether GHCR
has been seeded and is accessible for that exact SHA. Re-run bootstrap
only after checking its immutable-index provenance; never re-tag a
different image into an existing pin name. If ECR 429 follows a GHCR
failure, the job must remain red with the original `HARNESS_INVALID`
diagnosis. Record the failed source and job ID separately from all
application test verdicts.

The historical ECR reliability gap remains **open** until final-head PR CI
and post-merge jobs prove mirror use over repeated runs; bootstrapping alone
is source-infrastructure evidence, not verified ongoing reliability.
