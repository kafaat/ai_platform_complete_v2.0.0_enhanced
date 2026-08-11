#!/usr/bin/env bash
set -euo pipefail
VERSION="2.93.0"
ARCHIVE="gh_${VERSION}_linux_amd64.tar.gz"
EXPECTED="02d1290eba130e0b896f3709ffff22e1c75a51475ddb70476a85abc6b5807af0"
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
