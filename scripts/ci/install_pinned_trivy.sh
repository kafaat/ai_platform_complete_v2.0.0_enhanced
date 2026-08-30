#!/usr/bin/env bash
set -euo pipefail

VERSION="0.74.0"
ARCHIVE="trivy_${VERSION}_Linux-64bit.tar.gz"
EXPECTED="2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a"
URL="https://github.com/aquasecurity/trivy/releases/download/v${VERSION}/${ARCHIVE}"
DEST="${RUNNER_TEMP:-/tmp}/sahool-trivy-${VERSION}"

mkdir -p "$DEST"
curl --fail --silent --show-error --location --retry 3 --retry-all-errors \
  "$URL" -o "$DEST/$ARCHIVE"
echo "$EXPECTED  $DEST/$ARCHIVE" | sha256sum --check --strict -
tar -xzf "$DEST/$ARCHIVE" -C "$DEST" trivy
TRIVY_BIN="$DEST/trivy"
test -x "$TRIVY_BIN"
"$TRIVY_BIN" --version

if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$DEST" >> "$GITHUB_PATH"
else
  echo "$TRIVY_BIN"
fi
