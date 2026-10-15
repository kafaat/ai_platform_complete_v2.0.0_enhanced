#!/usr/bin/env bash
# Resolve a digest-locked Docker Official Image for an ephemeral CI fixture.
#
# A GHCR mirror is trusted ONLY by the same original OCI index sha256, not by
# tag or by a name which merely resembles a trusted image.
# Usage: pull_verified_ci_image.sh <pinned ECR reference> <output file for image ID>
# Output contains Docker's local sha256 config ID, usable with --pull=never or FROM.
set -euo pipefail

source_image="${1:?Pinned ECR image required}"
id_file="${2:?Image ID receipt path required}"

if [[ "$source_image" =~ ^public\.ecr\.aws/docker/library/(postgres|redis|nginx)@sha256:([0-9a-f]{64})$ ]]; then
  kind="${BASH_REMATCH[1]}"
  digest="${BASH_REMATCH[2]}"
else
  echo "::error::Only digest-locked Docker Official Images in the CI allowlist are supported" >&2
  exit 2
fi

# Keep the source lock tied to independently reviewed workflow image pins.
case "$kind:$digest" in
  postgres:d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae|\
  postgres:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d|\
  postgres:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea|\
  redis:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499|\
  nginx:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10) ;;
  *) echo "::error::CI source image not in the reviewed digest allowlist" >&2; exit 2 ;;
esac

if [[ ! "${CI_MIRROR_PULL_TIMEOUT:-75}" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::Invalid CI_MIRROR_PULL_TIMEOUT" >&2
  exit 2
fi
mirror="ghcr.io/kafaat/sahool-ci-${kind}@sha256:${digest}"
resolved="$source_image"
temp_log="$(mktemp)"
temp_id="$(mktemp "${id_file}.XXXXXX")"
trap 'rm -f "$temp_log" "$temp_id"' EXIT

# The token is passed by stdin and never printed. A private mirror published
# by this repository's bootstrap workflow can be pulled with packages:read.
if [[ -n "${GHCR_TOKEN:-}" ]]; then
  if ! printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin >/dev/null 2>&1; then
    echo "::warning::GHCR authentication unavailable; trying the pinned source" >&2
  fi
fi

if timeout "${CI_MIRROR_PULL_TIMEOUT:-75}" docker pull "$mirror" >"$temp_log" 2>&1; then
  resolved="$mirror"
  echo "CI_IMAGE_SOURCE=GHCR_VERIFIED_INDEX image=$mirror" >&2
else
  echo "::warning::Immutable GHCR mirror not accessible; retaining ECR pinned fallback" >&2
  # Existing retry policy classifies ECR 429 as HARNESS_INVALID, never
  # silently proceeds to integration tests against missing PostgreSQL.
  scripts/ci/resilient_docker_pull.sh "$source_image" >&2
  echo "CI_IMAGE_SOURCE=ECR_PINNED image=$source_image" >&2
fi

local_id="$(docker image inspect --format '{{.Id}}' "$resolved")"
if [[ ! "$local_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "::error::Cannot prove local Docker image config digest" >&2
  exit 1
fi

printf '%s\n' "$local_id" >"$temp_id"
mv -f "$temp_id" "$id_file"
