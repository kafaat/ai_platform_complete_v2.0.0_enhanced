#!/usr/bin/env bash
# Compile true transitive lock files for every service with pip-tools.
# Requires network/package-index access. By default it uses Alibaba Cloud PyPI mirror
# (https://mirrors.aliyun.com/pypi/simple/) unless PIP_INDEX_URL/PYPI_MIRROR_URL is overridden.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source scripts/ci/pip_mirror_env.sh
python -m pip install --upgrade pip pip-tools pip-audit
while IFS= read -r req; do
  out="${req%.txt}.lock"
  echo "[pip-compile] $req -> $out via $PIP_INDEX_URL"
  python -m piptools compile     --resolver=backtracking     --strip-extras     --generate-hashes     --index-url "$PIP_INDEX_URL"     -o "$out" "$req"
done < <(find services -maxdepth 3 -name 'requirements.txt' -print | sort)

while IFS= read -r lock; do
  echo "[pip-audit] $lock"
  python -m pip_audit -r "$lock" --progress-spinner off
done < <(find services -maxdepth 3 -name 'requirements.lock' -print | sort)

python - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, os

root = Path.cwd()
locks = []
for path in sorted(root.glob("services/**/requirements.lock")):
    data = path.read_bytes()
    locks.append({
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    })
if not locks:
    raise SystemExit("no transitive locks generated")
payload = {
    "blocker_id": "P-CERT-2",
    "status": "verified",
    "command": "bash scripts/ci/compile_transitive_service_locks.sh",
    "index_url_policy": "PIP_INDEX_URL/PYPI_MIRROR_URL through scripts/ci/pip_mirror_env.sh",
    "lock_files": locks,
    "repository": os.environ.get("GITHUB_REPOSITORY", "local-untrusted"),
    "workflow": os.environ.get("GITHUB_WORKFLOW", "local-untrusted"),
    "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local-untrusted"),
    "commit": os.environ.get("GITHUB_SHA", "local-untrusted"),
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
}
if payload["repository"] == "local-untrusted":
    payload["status"] = "evidence_attached"
out = root / "certification/evidence/transitive_locks_summary.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out} ({payload['status']}, {len(locks)} locks)")
PY
