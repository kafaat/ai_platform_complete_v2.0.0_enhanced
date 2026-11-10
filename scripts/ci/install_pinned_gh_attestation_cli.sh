#!/usr/bin/env bash
set -euo pipefail
VERSION="2.103.3"
ARCHIVE="gh_${VERSION}_linux_amd64.tar.gz"
EXPECTED="4c806978ffce1cec70853302a56d70ac6da4f19bae7adca4e1a8ab00633dd91d"
URL="https://github.com/cli/cli/releases/download/v${VERSION}/${ARCHIVE}"
DEST="${RUNNER_TEMP:-/tmp}/sahool-gh-${VERSION}"
mkdir -p "$DEST"
curl --fail --silent --show-error --location --retry 3 --retry-all-errors \
  "$URL" -o "$DEST/$ARCHIVE"
echo "$EXPECTED  $DEST/$ARCHIVE" | sha256sum --check --strict -
tar -xzf "$DEST/$ARCHIVE" -C "$DEST"
GH_BIN="$DEST/gh_${VERSION}_linux_amd64/bin/gh"
test -x "$GH_BIN"
"$GH_BIN" --version
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "$(dirname "$GH_BIN")" >> "$GITHUB_PATH"
else
  echo "$GH_BIN"
fi
