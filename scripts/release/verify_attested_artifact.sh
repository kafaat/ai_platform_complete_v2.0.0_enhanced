#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 --artifact PATH --checksum PATH --repo OWNER/REPO" >&2
}

artifact=""
checksum=""
repo=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact) artifact="${2:-}"; shift 2 ;;
    --checksum) checksum="${2:-}"; shift 2 ;;
    --repo) repo="${2:-}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

if [[ -z "$artifact" || -z "$checksum" || -z "$repo" ]]; then
  usage
  exit 2
fi
if [[ ! -f "$artifact" || ! -f "$checksum" ]]; then
  echo "Artifact or checksum file is missing" >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required to verify the signed attestation" >&2
  exit 1
fi

(
  cd "$(dirname "$artifact")"
  sha256sum -c "$(realpath --relative-to="$(dirname "$artifact")" "$checksum")"
)
gh attestation verify "$artifact" --repo "$repo"
echo "Checksum and GitHub artifact attestation verified"

