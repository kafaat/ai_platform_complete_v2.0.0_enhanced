#!/bin/sh
set -eu

: "${MINIO_ROOT_USER:?required}"
: "${MINIO_ROOT_PASSWORD:?required}"
: "${SCOUT_INGEST_S3_ACCESS_KEY:?required}"
: "${SCOUT_INGEST_S3_SECRET_KEY:?required}"
: "${RASTER_S3_ACCESS_KEY:?required}"
: "${RASTER_S3_SECRET_KEY:?required}"

mc alias set sahool "${MINIO_ENDPOINT:-http://sahool-minio:9000}" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing sahool/sahool-scout-ingest sahool/sahool-rasters

mc admin policy create sahool scout-ingest /policies/scout-ingest.json
mc admin policy create sahool raster-service /policies/raster-service.json

mc admin user add sahool "$SCOUT_INGEST_S3_ACCESS_KEY" "$SCOUT_INGEST_S3_SECRET_KEY"
mc admin user add sahool "$RASTER_S3_ACCESS_KEY" "$RASTER_S3_SECRET_KEY"
mc admin policy attach sahool scout-ingest --user "$SCOUT_INGEST_S3_ACCESS_KEY"
mc admin policy attach sahool raster-service --user "$RASTER_S3_ACCESS_KEY"

# Prove both positive access and cross-bucket denial before workloads start.
mc alias set scout "${MINIO_ENDPOINT:-http://sahool-minio:9000}" "$SCOUT_INGEST_S3_ACCESS_KEY" "$SCOUT_INGEST_S3_SECRET_KEY"
mc alias set raster "${MINIO_ENDPOINT:-http://sahool-minio:9000}" "$RASTER_S3_ACCESS_KEY" "$RASTER_S3_SECRET_KEY"
mc ls scout/sahool-scout-ingest >/dev/null
mc ls raster/sahool-rasters >/dev/null
if mc ls scout/sahool-rasters >/dev/null 2>&1; then echo "scout credential crossed into raster bucket" >&2; exit 1; fi
if mc ls raster/sahool-scout-ingest >/dev/null 2>&1; then echo "raster credential crossed into scout bucket" >&2; exit 1; fi
