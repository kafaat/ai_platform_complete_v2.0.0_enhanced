#!/usr/bin/env bash
# Regenerate every committed generated artifact after a structural change (routes / services /
# modules / dependencies), IN ORDER, so you don't chase CI drift one gate at a time.
#
# Rule (see sahool-brain/log.md): any change touching routes/services/deps ⇒ run this before push.
#
# Order matters: the inventories + route-mount inventory are inputs to the release bundle's
# checksums, so the bundle is rebuilt LAST. Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "==> service inventory + SERVICE_REGISTRY.md"
python scripts/ci/generate_service_inventory.py --write-registry

echo "==> route-mount inventory"
python scripts/ci/route_mount_contract_guard.py

echo "==> release bundle (SBOM + FILE_CHECKSUMS + manifest) — last, it checksums the tree"
python3 scripts/release/build_release_bundle.py --root .

echo "==> verify: everything is now self-consistent"
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/route_mount_contract_guard.py --check
python3 scripts/release/validate_release_package.py

echo "OK — all generated artifacts regenerated and consistent."
