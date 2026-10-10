#!/usr/bin/env bash
set -euo pipefail

base_image="${1:?صورة PostgreSQL الأساس مطلوبة}"
pg_major="${2:?إصدار PostgreSQL مطلوب}"
image_tag="${3:?وسم صورة الاختبار المحلية مطلوب}"

if [[ ! "$base_image" =~ ^public\.ecr\.aws/docker/library/postgres@sha256:[0-9a-f]{64}$ ]]; then
  echo "::error::يجب تثبيت صورة PostgreSQL الأساس من ECR Public بالـdigest" >&2
  exit 2
fi
if [[ ! "$pg_major" =~ ^(15|16)$ ]]; then
  echo "::error::إصدار PostgreSQL غير مدعوم لصورة PostGIS الاختبارية" >&2
  exit 2
fi
if [[ ! "$image_tag" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]*$ ]]; then
  echo "::error::وسم صورة الاختبار المحلية غير صالح" >&2
  exit 2
fi

scripts/ci/resilient_docker_pull.sh "$base_image"

if ! docker build --pull=false --tag "$image_tag" - <<DOCKERFILE
FROM $base_image
USER root
RUN timeout -k 10 240 apt-get update \
    && DEBIAN_FRONTEND=noninteractive timeout -k 10 240 apt-get install --yes --no-install-recommends \
        postgresql-$pg_major-postgis-3 \
        postgresql-$pg_major-postgis-3-scripts \
    && dpkg-query --show --showformat='\${Package}=\${Version}\n' postgresql-$pg_major-postgis-3 \
    && dpkg-query --show --showformat='\${Package}=\${Version}\n' postgresql-$pg_major-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
USER postgres
DOCKERFILE
then
  if [[ -n "${HARNESS_PRIMARY_CAUSE_FILE:-}" ]]; then
    printf '%s\n' POSTGIS_PACKAGE_PROVISIONING_FAILED >"$HARNESS_PRIMARY_CAUSE_FILE"
  fi
  exit 1
fi
