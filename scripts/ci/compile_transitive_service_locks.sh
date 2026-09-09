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

# ═══ القياسُ هنا، والأصلُ والحالةُ عند الباعث الواحد ═══════════════════════
#
# كانت هذه الكتلة تكتب ملفَّ الدليل كاملاً بيدها: تقرأ `GITHUB_*` بنفسها، وتضع
# `status: verified` بنفسها، وتهبط إلى `evidence_attached` بمقارنةِ سلسلةٍ حارسة
# (`local-untrusted`). أي **تعريفٌ ثانٍ لِما هو دليلٌ صالح** إلى جانب
# `emit_certification_evidence` — والاثنان يتّفقان اليوم ولا شيء يُلزِمهما بذلك غداً؛
# وهو الصنفُ الذي أسقط قائمتَي الحواجز في `production_certification_blockers_status`.
#
# والتعريفُ الثاني كان **أضعف**: لا يتحقّق من الحقول الدنيا التي يشترطها
# `production_evidence_pack_guard`، فينتج دليلاً يقبله الكاتبُ ويرفضه المُحكِّم بعد
# وظيفتين. فبقي هنا ما يخصّ هذا السكربت وحدَه — **قياسُ الأقفال** — وذهب الباقي.
python - <<'PY'
from pathlib import Path
import hashlib, json

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
fields = {
    "command": "bash scripts/ci/compile_transitive_service_locks.sh",
    "index_url_policy": "PIP_INDEX_URL/PYPI_MIRROR_URL through scripts/ci/pip_mirror_env.sh",
    "lock_files": locks,
}
out = root / "certification" / "evidence" / ".transitive_locks_fields.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"measured {len(locks)} transitive locks -> {out}")
PY

# `--skip-outside-ci`: تجميعُ الأقفال عملٌ مشروعٌ محليّاً، وانبعاثُ الدليل ثانويٌّ فيه.
# فالغيابُ يُعلَن بصوتٍ عالٍ ولا يُسقِط التجميع — ولا يُنتِج دليلاً أيضاً.
python scripts/ci/emit_certification_evidence.py \
  --blocker P-CERT-2 \
  --fields-file certification/evidence/.transitive_locks_fields.json \
  --skip-outside-ci
