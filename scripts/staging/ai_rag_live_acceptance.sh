#!/usr/bin/env bash
# Live AI/RAG acceptance harness for a deployed docker-compose.v9 stack.
# Read-only against data; optional --restart-rag restarts only the retrieval process
# to prove sparse-index rehydration after process restart.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"

SUBJECT_SHA=""
TENANT_ID=""
FIELD_ID=""
CROP=""
OUT_DIR="artifacts/ai-rag-live-acceptance"
RESTART_RAG=0
REQUIRE_GENERATION=0
COMPOSE_FILE="docker-compose.v9.yml"

while (($#)); do
  case "$1" in
    --subject-sha) SUBJECT_SHA="$2"; shift 2 ;;
    --tenant-id) TENANT_ID="$2"; shift 2 ;;
    --field-id) FIELD_ID="$2"; shift 2 ;;
    --crop) CROP="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --compose-file) COMPOSE_FILE="$2"; shift 2 ;;
    --restart-rag) RESTART_RAG=1; shift ;;
    --require-generation) REQUIRE_GENERATION=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 4 ;;
  esac
done

[[ "$SUBJECT_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "--subject-sha must be 40 hex" >&2; exit 4; }
[[ -n "$TENANT_ID" ]] || { echo "--tenant-id required" >&2; exit 4; }
command -v docker >/dev/null || { echo "docker missing" >&2; exit 4; }
docker compose version >/dev/null 2>&1 || { echo "docker compose missing" >&2; exit 4; }

DC=(docker compose -f "$COMPOSE_FILE")
mkdir -p "$OUT_DIR"

# Structural compose validation before touching the running stack.
"${DC[@]}" config >/dev/null

OLLAMA_CID=$("${DC[@]}" ps -q sahool-ollama)
RAG_CID=$("${DC[@]}" ps -q sahool-rag-retrieval)
[[ -n "$OLLAMA_CID" && -n "$RAG_CID" ]] || { echo "required AI/RAG containers are not running" >&2; exit 4; }

EXPECTED_IMAGE='ollama/ollama:0.32.5@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131'
ACTUAL_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$OLLAMA_CID")
printf '{"expected_image":%s,"actual_image":%s}\n' \
  "$(python -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$EXPECTED_IMAGE")" \
  "$(python -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$ACTUAL_IMAGE")" \
  > "$OUT_DIR/ollama_container_image.json"
[[ "$ACTUAL_IMAGE" == "$EXPECTED_IMAGE" ]] || { echo "Ollama container image mismatch: $ACTUAL_IMAGE" >&2; exit 2; }

run_cert() {
  local out="$1"
  local args=(--tenant-id "$TENANT_ID" --out -)
  [[ -n "$FIELD_ID" ]] && args+=(--field-id "$FIELD_ID")
  [[ -n "$CROP" ]] && args+=(--crop "$CROP")
  (( REQUIRE_GENERATION )) && args+=(--require-generation)
  # Stream the exact probe from the tested checkout into a container that is already
  # on sahool-internal. No copy/rebuild and no host-port exposure are required.
  set +e
  "${DC[@]}" exec -T sahool-rag-retrieval python - "${args[@]}" \
    < scripts/ci/ai_rag_live_certification.py > "$out"
  local rc=$?
  set -e
  return "$rc"
}

set +e
run_cert "$OUT_DIR/pre_restart_ai_rag.json"
PRE_RC=$?
set -e
if (( PRE_RC == 2 || PRE_RC == 4 )); then
  cat "$OUT_DIR/pre_restart_ai_rag.json" >&2
  exit "$PRE_RC"
fi

if (( RESTART_RAG )); then
  "${DC[@]}" restart sahool-rag-retrieval >/dev/null
  ready=0
  for _ in $(seq 1 60); do
    if "${DC[@]}" exec -T sahool-ai-agronomist python -c \
      "import urllib.request; urllib.request.urlopen('http://sahool-rag-retrieval:8000/readyz', timeout=3).read()" \
      >/dev/null 2>&1; then
      ready=1; break
    fi
    sleep 2
  done
  (( ready == 1 )) || { echo "rag-retrieval did not become ready after restart" >&2; exit 2; }

  set +e
  run_cert "$OUT_DIR/post_restart_ai_rag.json"
  POST_RC=$?
  set -e
  if (( POST_RC == 2 || POST_RC == 4 )); then
    cat "$OUT_DIR/post_restart_ai_rag.json" >&2
    exit "$POST_RC"
  fi

  python - "$OUT_DIR/pre_restart_ai_rag.json" "$OUT_DIR/post_restart_ai_rag.json" <<'PY'
import json,sys
pre=json.load(open(sys.argv[1],encoding='utf-8'))
post=json.load(open(sys.argv[2],encoding='utf-8'))
def chk(doc,name):
    for c in doc.get('checks',[]):
        if c.get('name')==name: return c
    raise SystemExit(f'missing check {name}')
for doc,label in ((pre,'pre'),(post,'post')):
    r=chk(doc,'rag_ready')
    h=chk(doc,'rag_hybrid_query')
    if r.get('status')!='PASS' or int((r.get('evidence') or {}).get('sparse_index_count') or 0)<=0:
        raise SystemExit(f'{label}: sparse index not hydrated')
    if h.get('status')!='PASS' or int((h.get('evidence') or {}).get('hybrid_hit_count') or 0)<=0:
        raise SystemExit(f'{label}: hybrid query not proven')
print('rag_restart_hybrid_durability_ok')
PY
fi

# Produce canonical dense-vs-hybrid parity receipt from the same live network.
CONTRACT_SHA=$(python - <<'PY'
import hashlib
print(hashlib.sha256(open('docs/architecture/rag_embedding_contract.json','rb').read()).hexdigest())
PY
)
Q1=${RAG_QUERY_1:-"القمح GDD النضج المناخ اليمني"}
Q2=${RAG_QUERY_2:-"الري بالتنقيط مياه الري"}
Q3=${RAG_QUERY_3:-"صدأ القمح"}
Q4=${RAG_QUERY_4:-"NDVI غطاء نباتي"}
Q5=${RAG_QUERY_5:-"إنتاجية القمح اليمن"}

"${DC[@]}" exec -T sahool-rag-retrieval python - \
  --tenant-id "$TENANT_ID" --subject-sha "${SUBJECT_SHA,,}" \
  --contract-sha256 "$CONTRACT_SHA" \
  --query "$Q1" --query "$Q2" --query "$Q3" --query "$Q4" --query "$Q5" \
  --out - < scripts/architecture/rag_live_parity_probe.py \
  > "$OUT_DIR/rag_live_parity_receipt.json"

python scripts/architecture/rag_live_parity_receipt_guard.py \
  --receipt "$OUT_DIR/rag_live_parity_receipt.json" --subject-sha "${SUBJECT_SHA,,}" \
  | tee "$OUT_DIR/rag_live_parity_guard.txt"
python scripts/ci/c8_rag_production_certification.py \
  --receipt "$OUT_DIR/rag_live_parity_receipt.json" --subject-sha "${SUBJECT_SHA,,}" \
  | tee "$OUT_DIR/c8_result.json"

python - "$OUT_DIR" "$SUBJECT_SHA" "$PRE_RC" "${POST_RC:-$PRE_RC}" <<'PY'
import hashlib,json,os,sys
root,subject,pre_rc,post_rc=sys.argv[1:]
files=[]
for name in sorted(os.listdir(root)):
    p=os.path.join(root,name)
    if os.path.isfile(p):
        b=open(p,'rb').read(); files.append({'file':name,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
status='PASS' if int(pre_rc)==0 and int(post_rc)==0 else 'EVIDENCE_REQUIRED'
out={'schema':'sahool.ai-rag-live-acceptance-bundle/v1','subject_sha':subject.lower(),'status':status,'authority_promotion':False,'files':files}
open(os.path.join(root,'bundle_manifest.json'),'w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False))
PY

# Preserve EVIDENCE_REQUIRED when grounded generation was explicitly required but
# the deployed policy/field prerequisites are not enabled yet.
if (( PRE_RC == 3 || ${POST_RC:-0} == 3 )); then exit 3; fi
exit 0
